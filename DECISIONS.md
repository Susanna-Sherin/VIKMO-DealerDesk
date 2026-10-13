# VIKMO DealerDesk — Technical Decisions

**Track:** AI / ML Intern
**Author:** Susanna Sherin C
**Project:** DealerDesk — Dealer Ordering, AI Assistance, and Demand Forecasting

## 1. Database Schema and Relationship Decisions

The relational schema is implemented in `core/models.py` using Django ORM models.

### Product and Inventory

- `Product` stores SKU, name, category, brand, vehicle fitment, price, and description.
- The SKU is unique to prevent duplicate catalogue identifiers.
- `Inventory` has a one-to-one relationship with `Product`, ensuring one inventory record per product.
- Inventory uses `CASCADE` because it depends on its product. However, products referenced by order items are protected from deletion.

### Dealers and Orders

- `Dealer` stores the dealer code, contact information, GSTIN, city, and credit limit. The dealer code is unique.
- `Order` references a dealer using `PROTECT`, preventing deletion of a dealer that has associated orders through normal Django deletion handling.
- Orders have a unique order number, timestamps, and lifecycle statuses: `DRAFT`, `CONFIRMED`, `DISPATCHED`, `DELIVERED`, and `CANCELLED`.
- `OrderItem` represents each product line in an order.
- Deleting an order cascades to its order items, while deleting a product referenced by an order item is prevented.

### Price Snapshots and Financial Calculations

Each order item stores its `unit_price` at creation time. This preserves the original price used for that order even if the catalogue price changes later.

Line subtotals are calculated using the saved unit price and quantity. Tax is calculated at 18%, and monetary values are rounded to two decimal places using Python's `Decimal` and `ROUND_HALF_UP`. Order totals are derived from the line-item calculations.

### Supporting Models

- `OrderSequence` maintains a daily sequence counter using a unique date string.
- `IdempotencyRecord` stores a unique request key, request hash, and associated order.
- `ConversationMessage` stores assistant conversation history, including session ID, role, content, optional dealer association, metadata, and timestamp.

These relationships separate dependent records from records that need protection to preserve order-history references.

## 2. Product Retrieval and Search

The assistant uses structured database queries to retrieve catalogue products.

The `search_parts` tool supports search by product SKU, name, brand, and description, with optional vehicle-fitment and category filters. The `check_stock` tool retrieves a specific product using its SKU.

Search results return catalogue attributes, current price, and available inventory from the database. If a product has no associated inventory record, the current implementation treats its stock quantity as zero.

This approach keeps product information connected to the application's data rather than relying on the LLM to invent catalogue details.

**Limitations:** The implementation uses database substring and case-insensitive matching rather than embedding-based semantic retrieval. Misspellings, synonyms, transliteration, and ambiguous descriptions may produce incomplete results. Semantic retrieval could be evaluated as a future improvement.

## 3. GenAI Assistant and Tool Execution

The assistant is implemented in `core/assistant.py` and uses the Gemini 2.5 Flash API when a Gemini API key is configured.

It declares three tools:

- `search_parts` — searches the parts catalogue.
- `check_stock` — retrieves current stock and catalogue price for a SKU.
- `create_draft_order` — requests draft-order creation for specified products and quantities.

The application executes these tools and returns their results to Gemini so it can generate a natural-language response. The current implementation supports one tool-execution round followed by a follow-up model request; it is not an unlimited agent loop.

### Separation of Responsibilities

The LLM interprets the user's request and selects a tool. Application functions query the database or call the order service to perform the requested operation.

Draft orders are created through the application's order service rather than by allowing the LLM to write directly to database tables. The service is responsible for enforcing the relevant order-creation rules.

The assistant also checks for dealer context before attempting draft-order creation. When no dealer is selected, it returns a message asking the user to select one.

## 4. Data Grounding, Order Safety, and Fallback Behaviour

### Database Grounding

The assistant's system instruction identifies PostgreSQL as the source of truth for products, prices, inventory, and orders. It instructs Gemini to use the relevant tools before providing price or stock information.

The tools retrieve catalogue and inventory values from the database. The order service handles draft-order creation, while saved order-item prices preserve the prices used at order creation.

**Important limitation:** System instructions encourage grounded responses but do not independently guarantee that every statement in the model's final response is supported by a tool result. Additional application-level validation would be needed to enforce that guarantee.

### Untrusted Catalogue Data

The system instruction tells the model to treat catalogue text as untrusted data rather than as instructions. The current search-tool response includes product identifiers and catalogue attributes but does not return the product description field itself.

These measures reduce exposure to instructions embedded in retrieved descriptions, but they should not be described as complete prompt-injection protection. Adversarial inputs and tool outputs require dedicated security tests.

### Draft-Order Restrictions

The assistant is instructed to create draft orders only and not to confirm, dispatch, cancel, or directly modify inventory. It also tells users that draft orders require manual confirmation.

These restrictions are partly expressed through system instructions and partly enforced by application logic. The implementation should not be described as completely secure solely because these instructions are present.

### Offline Fallback

When the Gemini API key is missing, an API request fails, or an exception occurs during processing, the assistant can use deterministic fallback logic.

The fallback supports selected SKU-based stock checks, basic part-keyword searches, and draft-order requests. It uses database-backed functions rather than generating catalogue values from the LLM.

This fallback is intentionally limited and does not provide the same language understanding as the Gemini-powered assistant.

## 8. Testing and Verification — Safety Qualification

The automated tests cover selected assistant behaviours, including operation without an API key and fallback handling when the provider returns an error. The broader test suite also covers draft-order behaviour, inventory neutrality, order calculations, and other backend rules.

Passing these tests establishes that the tested scenarios behave as expected. It does not establish complete protection against prompt injection, guarantee that every model-generated statement is grounded, or prove that every possible API failure and malformed tool call is handled safely. These behaviours require additional targeted tests.

## 5. Forecasting Approach

The forecasting component is implemented in `ml/forecast.py`. It is a **statistical, rule-based forecasting approach**, not a trained machine-learning model.

The implementation uses different calculations according to the amount and pattern of available sales history.

### Intermittent Demand

For products with a high proportion of zero-sales periods, the implementation uses a simplified zero-inflated mean:

- Estimate the proportion of periods with nonzero demand.
- Calculate the average demand during nonzero periods.
- Combine these quantities to estimate expected demand.
- Apply a promotional adjustment when relevant.

This is a simplified intermittent-demand heuristic, not a full implementation of the Croston forecasting method.

### Short Sales Histories

For products with limited history, the implementation uses exponentially weighted historical demand, giving more recent observations greater influence.

This allows the system to produce estimates without requiring a long history for every product.

### Regular Demand

For products with sufficient history, the implementation blends recent moving averages and a year-ago seasonal reference. The recent average receives more weight than the longer average, and the resulting estimate is blended with the seasonal reference.

Promotional adjustments are applied when relevant to the forecast period.

Products without sales history receive a zero forecast under the current implementation. This avoids inventing historical demand, although it may underpredict genuinely new products with expected demand.

### Forecast Output

The implementation generates a forecast CSV covering the configured forecast weeks and catalogue SKUs. The automated tests verify the expected output size of **160 rows, representing 40 SKUs across four weeks**.

Forecast values are estimates, not guaranteed sales quantities. The approach is designed to provide a transparent baseline for the assignment rather than claim production-grade predictive accuracy.

## 6. Reorder Suggestions

The reorder logic in `ml/forecast.py` combines forecast demand and recent demand variability.

The implementation:

1. Sums forecast demand across the product's lead-time horizon.
2. Estimates demand variability using the recent sales history.
3. Calculates safety stock using the implemented formula:

   `Safety stock = ceil(1.65 × standard deviation × sqrt(lead time))`

4. Calculates the reorder point as lead-time demand plus safety stock.
5. Compares the reorder point with current inventory.
6. Calculates a nonnegative suggested reorder quantity.

The reorder suggestion is a planning aid. Its reliability depends on the quality of sales history, lead-time data, forecast estimates, and current stock information.

## 7. Promotional Demand Adjustments

The forecasting implementation estimates promotional uplift from historical promotional and non-promotional sales where sufficient data exists. It uses a fallback multiplier when the historical comparison is unavailable and constrains the calculated uplift within configured bounds.

These adjustments are heuristics. Their effectiveness should be evaluated against held-out historical periods before being presented as proven improvements.

The implementation uses a generic promotional calendar. It should not be described as explicitly modelling a particular festival or event unless that behaviour is separately implemented and verified.

## 8. Testing and Verification

The backend's automated test suite covers important business rules and integration behaviour.

Verified checks include:

- Django system checks.
- Dealer and product API behaviour.
- Repeatable seed-data execution.
- Draft-order creation without changing stock.
- Saved order-price snapshots.
- Idempotency behaviour.
- Tax rounding and order totals.
- Order confirmation and cancellation workflows.
- Input validation and response formats.
- Forecast and reorder endpoints.
- Forecast CSV output size.
- Assistant fallback behaviour when the AI provider returns an error.
- Assistant behaviour when an API key is unavailable.

The test suite completed successfully with **19 passing tests** during the reviewed run. The Django system check also passed.

These results establish that the tested scenarios work; they do not prove that every production failure mode, security risk, or prompt-injection attempt is handled correctly.

## 9. Known Limitations

- Structured keyword retrieval may miss semantically related products or misspellings.
- The assistant depends on the configured AI provider when live model responses are enabled.
- Statistical forecasts may be unreliable when sales history is sparse, irregular, or affected by unusual events.
- New products without sales history currently receive zero forecast.
- Forecast accuracy metrics should only be reported after running a reproducible evaluation against a defined holdout period.
- The application requires further security, concurrency, deployment, and operational review before production use.
- The prototype does not implement authentication or authorization for its write APIs, and several views are CSRF-exempt. The supplier-sync endpoint can update catalogue data, so the application must not be exposed as a public service without appropriate access controls and security review.

## 10. Future Improvements

Possible future work, subject to evaluation and time constraints, includes:

- Adding a product synonym dictionary or semantic retrieval after measuring search failures.
- Comparing forecasting heuristics against naive, moving-average, and seasonal baselines using a time-based holdout.
- Evaluating more advanced models when sufficient historical data is available.
- Adding uncertainty intervals to demand forecasts.
- Improving monitoring, access control, and operational observability.
- Expanding automated tests for malformed inputs, concurrent order requests, and adversarial assistant inputs.

These are potential improvements, not claims about functionality already implemented.

## Conclusion

DealerDesk combines relational data modelling, validated order workflows, database-grounded AI assistance, and transparent statistical forecasting. The design prioritizes preserving order history, maintaining price consistency, separating model interpretation from business logic, and making the limits of AI and forecasting explicit.