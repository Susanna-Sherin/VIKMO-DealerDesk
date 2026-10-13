import csv
import math
from collections import defaultdict
from pathlib import Path

from django.conf import settings

# Path helpers
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
FORECAST_CSV = REPO_ROOT / "ml" / "forecast.csv"
FORECAST_WEEKS = ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]


def load_forecast_skus(data_dir=DATA_DIR):
    lead_times = {}
    lead_file = data_dir / "lead_times.csv"
    with open(lead_file, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            lead_times[row["sku"].strip()] = int(row["lead_time_weeks"])
    return lead_times


def load_promo_calendar(data_dir=DATA_DIR):
    promos = defaultdict(dict)
    promo_file = data_dir / "promo_calendar.csv"
    with open(promo_file, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            promos[row["sku"].strip()][row["week_start"].strip()] = int(row["promo_flag"])
    return promos


def load_sales_history(data_dir=DATA_DIR):
    history = defaultdict(list)
    sales_file = data_dir / "sales_history.csv"
    with open(sales_file, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            history[row["sku"].strip()].append({
                "week_start": row["week_start"].strip(),
                "units_sold": float(row["units_sold"]),
                "promo_flag": int(row["promo_flag"]),
            })
    for sku in history:
        history[sku].sort(key=lambda x: x["week_start"])
    return history


def generate_forecasts(data_dir=DATA_DIR, output_csv=FORECAST_CSV):
    lead_times = load_forecast_skus(data_dir)
    future_promos = load_promo_calendar(data_dir)
    sales_history = load_sales_history(data_dir)

    forecast_rows = []

    for sku in sorted(lead_times.keys()):
        series = sales_history.get(sku, [])
        if not series:
            # Fallback if no history
            for w in FORECAST_WEEKS:
                forecast_rows.append({"sku": sku, "week_start": w, "forecast_units": 0.0})
            continue

        n_weeks = len(series)
        zero_ratio = sum(1 for x in series if x["units_sold"] == 0) / n_weeks
        is_intermittent = zero_ratio > 0.35
        is_short = n_weeks < 12

        # Empirical promo lift
        promo_sales = [x["units_sold"] for x in series if x["promo_flag"] == 1]
        non_promo_sales = [x["units_sold"] for x in series if x["promo_flag"] == 0]
        mean_non_promo = (sum(non_promo_sales) / len(non_promo_sales)) if non_promo_sales else 1.0
        if promo_sales and mean_non_promo > 0:
            raw_lift = (sum(promo_sales) / len(promo_sales)) / mean_non_promo
            promo_lift = max(1.1, min(2.5, raw_lift))
        else:
            promo_lift = 1.35

        for step, week in enumerate(FORECAST_WEEKS):
            p_flag = future_promos.get(sku, {}).get(week, 0)

            if is_intermittent:
                # Intermittent / slow-moving SKUs: Croston / zero-inflated mean
                non_zero = [x["units_sold"] for x in series if x["units_sold"] > 0]
                prob = len(non_zero) / n_weeks
                intensity = sum(non_zero) / len(non_zero) if non_zero else 0.0
                base = prob * intensity
                val = base * (promo_lift if p_flag else 1.0)
            elif is_short:
                # Recently launched products with few weeks
                weights = [math.exp(0.3 * i) for i in range(n_weeks)]
                base = sum(w * x["units_sold"] for w, x in zip(weights, series)) / sum(weights)
                val = base * (promo_lift if p_flag else 1.0)
            else:
                # Regular SKUs with full 104 weeks of history
                recent_4 = sum(x["units_sold"] for x in series[-4:]) / 4.0
                recent_8 = sum(x["units_sold"] for x in series[-8:]) / 8.0
                recent_trend = 0.7 * recent_4 + 0.3 * recent_8

                # Year-ago seasonal baseline (week corresponding to Diwali/seasonal cycle)
                # Look back 52 weeks
                idx_52 = n_weeks - 52 + step
                if 0 <= idx_52 < n_weeks:
                    prior_year_val = series[idx_52]["units_sold"]
                else:
                    prior_year_val = recent_trend

                # Combine trend and seasonality
                base = 0.6 * recent_trend + 0.4 * prior_year_val
                val = base * (promo_lift if p_flag else 1.0)

            # Round to 1 decimal place and ensure non-negative
            forecast_val = max(0.0, round(val, 1))
            forecast_rows.append({
                "sku": sku,
                "week_start": week,
                "forecast_units": forecast_val,
            })

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sku", "week_start", "forecast_units"])
        writer.writeheader()
        writer.writerows(forecast_rows)

    return forecast_rows


def load_cached_forecast_map(forecast_csv=FORECAST_CSV):
    if not forecast_csv.exists():
        generate_forecasts(output_csv=forecast_csv)

    forecast_map = defaultdict(list)
    with open(forecast_csv, mode="r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            forecast_map[row["sku"].strip()].append({
                "week_start": row["week_start"].strip(),
                "forecast_units": float(row["forecast_units"]),
            })
    return forecast_map


def compute_sample_std(values):
    n = len(values)
    if n <= 1:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(variance)


def calculate_reorder_suggestions(inventory_lookup_fn, data_dir=DATA_DIR, forecast_csv=FORECAST_CSV):
    lead_times = load_forecast_skus(data_dir)
    forecast_map = load_cached_forecast_map(forecast_csv)
    sales_history = load_sales_history(data_dir)

    results = []
    for sku in sorted(lead_times.keys()):
        lead_time_weeks = lead_times[sku]
        sku_forecasts = forecast_map.get(sku, [])

        # lead_time_demand = sum of forecast_units for the first L forecast weeks
        lead_time_demand = sum(
            item["forecast_units"] for item in sku_forecasts[:lead_time_weeks]
        )
        lead_time_demand = round(lead_time_demand, 1)

        # sigma = sample standard deviation (n - 1) of units_sold over most recent 12 weeks
        history = sales_history.get(sku, [])
        recent_12 = [x["units_sold"] for x in history[-12:]]
        sigma = compute_sample_std(recent_12)

        # safety_stock = ceil(1.65 * sigma * sqrt(L))
        safety_stock = math.ceil(1.65 * sigma * math.sqrt(lead_time_weeks))

        # reorder_point = lead_time_demand + safety_stock
        reorder_point = round(lead_time_demand + safety_stock, 1)

        # current_stock = live available stock
        current_stock = inventory_lookup_fn(sku)

        # reorder_qty = max(0, ceil(reorder_point - current_stock))
        reorder_qty = max(0, math.ceil(reorder_point - current_stock))

        results.append({
            "sku": sku,
            "current_stock": current_stock,
            "lead_time_weeks": lead_time_weeks,
            "lead_time_demand": lead_time_demand,
            "safety_stock": safety_stock,
            "reorder_point": reorder_point,
            "reorder_qty": reorder_qty,
        })

    return results


if __name__ == "__main__":
    rows = generate_forecasts()
    print(f"Generated {len(rows)} forecast rows in {FORECAST_CSV}")
    assert len(rows) == 160, f"Expected 160 rows, got {len(rows)}"
