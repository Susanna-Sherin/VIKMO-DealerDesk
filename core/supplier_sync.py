import logging
import re
import time
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.db import transaction
import requests

from .models import Inventory, Product

logger = logging.getLogger(__name__)

DECIMAL_REGEX = re.compile(r"^\d+(\.\d{1,2})?$")


def is_valid_price(price_raw):
    if price_raw is None:
        return False, "missing price"
    price_str = str(price_raw).strip()
    if not DECIMAL_REGEX.match(price_str):
        return False, "invalid price format (must have at most 2 decimals)"
    try:
        val = Decimal(price_str)
        if val <= 0:
            return False, "price must be greater than zero"
        return True, val
    except InvalidOperation:
        return False, "invalid decimal price"


def sync_supplier_catalogue():
    supplier_url = getattr(settings, "SUPPLIER_API_URL", "http://127.0.0.1:8099").rstrip("/")
    api_key = getattr(settings, "SUPPLIER_API_KEY", "")

    headers = {"X-Api-Key": api_key}
    cursor = None
    pages_fetched = 0
    requests_made = 0

    all_raw_items = []

    # 1. Fetch all pages with retry logic
    while True:
        url = f"{supplier_url}/v1/products?limit=20"
        if cursor:
            url += f"&cursor={cursor}"

        success = False
        last_error = None

        for attempt in range(1, 6):
            requests_made += 1
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    cursor = data.get("next_cursor")
                    all_raw_items.extend(items)
                    pages_fetched += 1
                    success = True
                    break
                elif resp.status_code == 401:
                    logger.error("Supplier rejected API key (401)")
                    return None, "SUPPLIER_UNAVAILABLE", "Supplier rejected API key.", 502
                elif resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        wait_sec = float(retry_after) if retry_after else 1.0
                    except ValueError:
                        wait_sec = 1.0
                    logger.warning("Supplier 429 rate limit. Waiting %s seconds (attempt %s/5)...", wait_sec, attempt)
                    time.sleep(wait_sec)
                elif resp.status_code in (500, 502, 503, 504):
                    logger.warning("Supplier %s error on attempt %s/5. Retrying...", resp.status_code, attempt)
                    time.sleep(0.5 * attempt)
                else:
                    logger.error("Unexpected supplier status %s: %s", resp.status_code, resp.text)
                    time.sleep(0.5 * attempt)
            except (requests.RequestException, Exception) as exc:
                last_error = exc
                logger.warning("Network error on supplier request (attempt %s/5): %s", attempt, exc)
                time.sleep(0.5 * attempt)

        if not success:
            logger.error("Failed to fetch supplier page after 5 attempts.")
            return None, "SUPPLIER_UNAVAILABLE", f"Supplier unavailable after retries: {last_error}", 502

        if not cursor:
            break

    # 2. Filter invalid items and collect rejected
    rejected = []
    valid_items = []

    for item in all_raw_items:
        sku = item.get("sku")
        supplier_sku = item.get("supplier_sku", "UNKNOWN")

        if not sku or not isinstance(sku, str) or not sku.strip():
            rejected.append({"supplier_sku": supplier_sku, "reason": "missing or empty sku"})
            continue

        valid_p, p_res = is_valid_price(item.get("price"))
        if not valid_p:
            rejected.append({"supplier_sku": supplier_sku, "reason": p_res})
            continue

        valid_items.append((item, p_res))

    # 3. Resolve duplicate SKUs using latest updated_at
    latest_by_sku = {}
    for item, parsed_price in valid_items:
        sku = item["sku"].strip()
        updated_at = item.get("updated_at", "")
        if sku not in latest_by_sku or updated_at > latest_by_sku[sku][0].get("updated_at", ""):
            latest_by_sku[sku] = (item, parsed_price)

    # 4. Apply to database atomically
    created_count = 0
    updated_count = 0
    unchanged_count = 0

    with transaction.atomic():
        existing_products = {p.sku: p for p in Product.objects.filter(sku__in=latest_by_sku.keys())}

        for sku, (item, parsed_price) in latest_by_sku.items():
            name = item.get("name", "").strip()
            category = item.get("category", "").strip()
            brand = item.get("brand", "").strip()
            vehicle_fitment = item.get("vehicle_fitment", "").strip()
            description = item.get("description", "").strip()
            price = parsed_price

            if sku not in existing_products:
                new_prod = Product.objects.create(
                    sku=sku,
                    name=name,
                    category=category,
                    brand=brand,
                    vehicle_fitment=vehicle_fitment,
                    price=price,
                    description=description,
                )
                Inventory.objects.create(product=new_prod, quantity=0)
                created_count += 1
            else:
                prod = existing_products[sku]
                has_diff = (
                    prod.name != name
                    or prod.category != category
                    or prod.brand != brand
                    or prod.vehicle_fitment != vehicle_fitment
                    or prod.description != description
                    or prod.price != price
                )

                if has_diff:
                    prod.name = name
                    prod.category = category
                    prod.brand = brand
                    prod.vehicle_fitment = vehicle_fitment
                    prod.description = description
                    prod.price = price
                    prod.save(update_fields=[
                        "name", "category", "brand", "vehicle_fitment", "description", "price"
                    ])
                    updated_count += 1
                else:
                    unchanged_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "rejected": rejected,
        "pages_fetched": pages_fetched,
        "requests_made": requests_made,
    }, None, None, 200
