VIKMO DealerDesk — Technical Submission

Track: aiml (AI / ML Intern Track)
Author: Susanna Sherin C (Final-Year B.Tech AI & ML Candidate)
Submission Repository: https://github.com/Susanna-Sherin/VIKMO-DealerDesk


Video Walkthrough: https://drive.google.com/file/d/1xOQy34s_TJvTuPNcCkQOZvHqohWVqOMO/view?usp=sharing

1. System Overview & Architecture

VIKMO DealerDesk is a B2B distributor operations platform built using Django 5.2, Django REST Framework, PostgreSQL, Google Gemini 2.5 Flash, and statistical demand forecasting.

The system brings together the following modules:

Core Relational Commerce (Part A1): Product catalogue search, vehicle fitment lookup, inventory tracking, and dealer management.

Order Engine (Part A2): Sequential order numbering, immutable draft price snapshots, line-level 18% GST calculations rounded using ROUND_HALF_UP, stock deduction on confirmation, and idempotency-key support.

GenAI Dealer Assistant (Part C): A conversational assistant that uses Gemini tool calling to search products, check stock, and create draft orders. It includes conversation history, an offline fallback, and safeguards around order creation.

Demand Forecasting & Reorder Engine (Part D): Statistical forecasting for 40 SKUs over four weeks, with lead-time demand, safety-stock calculations, and inventory-based reorder recommendations.

Supplier Synchronization (Part B — Optional Bonus): Supplier catalogue synchronization with pagination, retry handling, transaction management, and duplicate-record handling.

The project also includes a browser-based operations portal for viewing and managing the main business workflows.

2. LLM Provider, Model & Tools

Provider: Google Gemini

Model: gemini-2.5-flash

Configuration: The API key is read from the GEMINI_API_KEY environment variable.

Function-calling tools:

search_parts(query, vehicle, category): Searches the catalogue using product, category, brand, and vehicle-fitment information.

check_stock(sku): Retrieves current inventory information for a SKU.

create_draft_order(dealer_id, items): Creates a draft order through the application's order validation logic.

Offline fallback: When the Gemini API key is unavailable, the assistant uses a deterministic fallback handler for supported requests. This allows basic assistant functionality without a live Gemini API call.

Order safety: The assistant creates draft orders rather than confirming orders. Draft creation does not deduct physical inventory.

3. Setup & Run Instructions

3.1 Prerequisites

Python 3.11 or later

PostgreSQL

Git

3.2 Environment Setup

Create and activate a virtual environment.

Windows PowerShell

python -m venv .venv
.\.venv\Scripts\Activate.ps1

Linux/macOS

python -m venv .venv
source .venv/bin/activate

Install dependencies:

pip install -r requirements.txt

Copy .env.example to .env and configure the database connection and required credentials. For example:

DATABASE_URL=postgresql://postgres:YOUR_DATABASE_PASSWORD@localhost:5432/dealerdesk
GEMINI_API_KEY=your_gemini_api_key_here

Replace the example values with your actual local configuration. Keep .env private and never commit API keys or database passwords.

Ensure that the PostgreSQL server is running and that the dealerdesk database exists before proceeding.

3.3 Database Migration and Seeding

Apply database migrations:

python manage.py migrate --noinput

Seed the sample dealers, catalogue, and inventory:

python manage.py seed_data

The seed command is designed to be repeatable. Running it again should update existing records rather than create duplicates.

python manage.py seed_data

3.4 Start the Application

python manage.py runserver 0.0.0.0:8000 --noreload

Open the operations portal at:

http://127.0.0.1:8000/

4. Tests & Verification

4.1 Automated Test Suite

Run the backend tests:

python manage.py test core -v 2

The current test suite contains 19 tests, covering:

Product and dealer API operations

Order validation and response formats

GST rounding and price snapshots

Draft-order stock neutrality

Order confirmation and cancellation

Idempotency-key behavior

Sequential order-number generation

Assistant tool handling and offline fallback

Forecast and reorder endpoints

Forecast output coverage

Frontend portal delivery

Repeatable data seeding

Latest verified result: 19 tests passed.

4.2 Django System Check

python manage.py check

Latest verified result: No system-check issues reported.

4.3 Smoke Test

If smoke_test.py is included in the repository, run the supplied smoke-test contract against the running application:

pip install requests
python smoke_test.py --base-url http://localhost:8000 --track aiml

Review the command output to confirm the results for the current environment.

5. Operations Portal (Part E — Frontend)

The project includes a responsive B2B operations portal served by Django templates, without a separate frontend build process.

5.1 Frontend Architecture

Templates: core/templates/core/base.html and core/templates/core/portal.html

Styling: core/static/core/css/portal.css

JavaScript: core/static/core/js/portal.js

Routing: The root route (/) serves the portal, while API routes remain under /api/.

The frontend uses JavaScript fetch() calls to retrieve and update application data through the backend API.

5.2 Operational Modules

Operations Overview

Catalogue and dealer metrics

Order pipeline summary

Reorder recommendations

Recent orders

Product Catalogue & Inventory

Search and filter catalogue products

View product and vehicle-fitment information

Display stock status

Update inventory through the inventory API

Dealer Directory

View and search registered dealers

Display dealer details and credit limits

Register dealers through the API

Initiate an order with a selected dealer

Order Management

Create draft orders containing multiple items

View order details and line-item totals

Display saved unit-price snapshots and GST calculations

Confirm, dispatch, deliver, or cancel orders through the supported lifecycle endpoints

AI Operations Assistant

Conversational interface

Optional dealer context

Gemini-powered responses when configured

Deterministic offline fallback for supported requests

Draft-order creation through the backend order workflow

Forecasting & Replenishment

Four-week SKU forecasts

Forecast drilldown by SKU

Lead-time demand and safety-stock calculations

Live inventory-based reorder recommendations

Supplier synchronization interface

6. Demand Forecasting & Reorder Engine

6.1 Forecast Output

The committed forecast file is ml/forecast.csv.

It contains 160 forecast rows, representing 40 SKUs across four forecast weeks:

2026-09-28

2026-10-05

2026-10-12

2026-10-19

The forecast dates are generated by the current implementation. Regenerate or update them when a new forecasting period is required.

6.2 Forecasting Approach

The implementation uses statistical, rule-based forecasting based on available sales history.

Intermittent demand: Estimates demand using the frequency of nonzero sales and the average quantity sold when demand occurs.

Short sales history: Uses exponentially weighted averages, giving greater weight to recent observations.

Regular products: Combines recent four-week and eight-week averages with a year-ago value when available.

Promotional demand: Estimates promotional uplift from historical promotional and non-promotional sales when sufficient observations are available. The estimated multiplier is bounded by configured limits.

Missing sales history: Produces zero forecasts when a SKU has no available sales history.

This is a heuristic statistical forecasting approach, not a trained machine-learning model. Comparative accuracy claims are not made without verified evaluation results.

6.3 Reorder Calculations

The reorder engine combines forecast demand with current inventory.

Lead-time demand

Lead-time demand is calculated by summing forecast values over the applicable lead-time horizon:

lead_time_demand = sum(forecast demand over lead-time weeks)

Safety stock

The implementation uses the sample standard deviation of recent weekly sales:

[
\sigma = \sqrt{\frac{1}{n-1}\sum_{i=1}^{n}(x_i-\bar{x})^2}
]

Safety stock is calculated as:

[
\text{safety stock} =
\left\lceil 1.65 \times \sigma \times \sqrt{L} \right\rceil
]

where (L) is the lead time in weeks.

Reorder point

[
\text{reorder point} =
\left\lceil \text{lead-time demand}+\text{safety stock}\right\rceil
]

Reorder quantity

[
\text{reorder quantity} =
\max(0,\text{reorder point}-\text{current stock})
]

The reorder recommendations use the current inventory values returned by the application.

7. API Reference

Endpoint

Method

Description

/

GET

Operations portal

/api/health/

GET

Application health status

/api/products/

GET, POST

Catalogue listing and product creation

/api/products/{sku}/

GET, PATCH

Product details and supported updates

/api/inventory/{sku}/

PUT

Inventory adjustment

/api/dealers/

GET, POST

Dealer listing and registration

/api/dealers/{id}/

GET

Dealer details

/api/orders/

GET, POST

List orders and create draft orders

/api/orders/{order_number}/

GET, PUT

Order details and supported updates

/api/orders/{order_number}/confirm/

POST

Confirm an order and deduct stock

/api/orders/{order_number}/dispatch/

POST

Dispatch an order

/api/orders/{order_number}/deliver/

POST

Mark an order as delivered

/api/orders/{order_number}/cancel/

POST

Cancel an order according to its lifecycle rules

/api/assistant/chat/

POST

Conversational assistant

/api/forecast/{sku}/

GET

Four-week forecast for a SKU

/api/reorder-suggestions/

GET

Inventory-based reorder recommendations

/api/sync/supplier/

POST

Supplier catalogue synchronization

Refer to the corresponding Django views and serializers for the exact request and response schemas.

8. Assumptions & Engineering Decisions

Price Snapshots

Order items store the unit price used when the draft is created. Subsequent catalogue price changes do not retroactively change the saved order-item prices.

Draft-Order Stock Neutrality

Creating or editing a draft order does not change physical inventory. Stock is deducted when an order is confirmed.

Order Number Generation

The order engine uses a database-backed sequence mechanism to generate daily order numbers in the format ORD-YYYYMMDD-NNNN.

Idempotency

Order creation supports an Idempotency-Key header. Repeating a request with the same key and matching payload returns the existing result. Reusing a key with a different payload returns an idempotency conflict.

Forecasting Limitations

The forecasting implementation is rule-based and depends on the quality and availability of historical sales data. Forecasts and reorder recommendations should be evaluated against observed demand before being used for operational purchasing decisions.

9. Five-Minute Walkthrough Video Outline — AI / ML Track

The walkthrough will cover the following topics:

0:00–0:45 — Architecture and setup: Explain the system structure, technology stack, database, and test commands.

0:45–2:00 — Dealer assistant: Walk through the assistant implementation, available tools, database grounding, conversation history, offline fallback, and draft-only order creation.

2:00–3:15 — Forecasting pipeline: Explain the SKU forecasting logic, intermittent demand estimation, short-history handling, recent averages, year-ago values, and promotional uplift.

3:15–4:15 — Replenishment: Explain lead-time demand, sample standard deviation, safety stock, reorder points, and current-stock integration.

4:15–5:00 — Relational design and engineering decisions: Review key models, order lifecycle rules, price snapshots, idempotency, and testing.

The video link at the top should be replaced with the actual walkthrough link before final submission.

10. Project Structure

VIKMO DealerDesk/
├── core/
│   ├── management/
│   │   └── commands/
│   │       └── seed_data.py
│   ├── migrations/
│   ├── static/
│   │   └── core/
│   │       ├── css/
│   │       └── js/
│   ├── templates/
│   │   └── core/
│   ├── assistant.py
│   ├── models.py
│   ├── order_service.py
│   ├── serializers.py
│   ├── supplier_sync.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── data/
├── dealerdesk/
├── ml/
│   ├── forecast.csv
│   └── forecast.py
├── .env.example
├── .gitignore
├── DECISIONS.md
├── manage.py
├── requirements.txt
└── README.md

The structure above summarizes the main application files; the repository may contain additional supporting files.