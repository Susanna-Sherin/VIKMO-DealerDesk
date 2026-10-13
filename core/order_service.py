import hashlib
import json
import logging
from decimal import Decimal
from zoneinfo import ZoneInfo
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Dealer, IdempotencyRecord, Inventory, Order, OrderItem, OrderSequence, Product

logger = logging.getLogger(__name__)


def hash_request_body(body_bytes_or_str):
    if isinstance(body_bytes_or_str, str):
        body_bytes = body_bytes_or_str.encode("utf-8")
    else:
        body_bytes = body_bytes_or_str or b""
    return hashlib.sha256(body_bytes).hexdigest()


def generate_order_number():
    """
    Generates unique order number: ORD-YYYYMMDD-NNNN using Asia/Kolkata date.
    Concurrency-safe even when multiple threads/processes start on a new day concurrently.
    """
    kolkata_tz = ZoneInfo("Asia/Kolkata")
    now_ist = timezone.now().astimezone(kolkata_tz)
    date_str = now_ist.strftime("%Y%m%d")

    # Retry loop with savepoints to handle race conditions on initial row insertion
    for attempt in range(20):
        try:
            with transaction.atomic():
                seq_obj = (
                    OrderSequence.objects.select_for_update()
                    .filter(date_str=date_str)
                    .first()
                )
                if not seq_obj:
                    try:
                        with transaction.atomic():
                            seq_obj = OrderSequence.objects.create(
                                date_str=date_str,
                                last_seq=1,
                            )
                            return f"ORD-{date_str}-{seq_obj.last_seq:04d}"
                    except IntegrityError:
                        # Another transaction won the race to insert the initial row;
                        # the nested atomic savepoint rolled back cleanly.
                        seq_obj = (
                            OrderSequence.objects.select_for_update()
                            .filter(date_str=date_str)
                            .first()
                        )
                        if not seq_obj:
                            continue

                seq_obj.last_seq += 1
                seq_obj.save(update_fields=["last_seq"])
                return f"ORD-{date_str}-{seq_obj.last_seq:04d}"
        except IntegrityError:
            continue

    # Fallback safety in extreme contention
    raise RuntimeError(f"Could not generate unique order number sequence for date {date_str}.")


def validate_order_items(items_data):
    """
    Validates items list:
    - At least one item
    - Each item has sku and quantity
    - quantity is positive integer >= 1
    - no duplicate SKUs
    - every SKU exists
    Returns: (is_valid, error_code, error_message, details, product_map)
    """
    if not isinstance(items_data, list) or len(items_data) == 0:
        return (
            False,
            "VALIDATION_ERROR",
            "Order must contain at least one item.",
            [{"field": "items", "message": "At least one item is required."}],
            {},
        )

    seen_skus = set()
    skus_to_fetch = []
    parsed_items = []

    for idx, item in enumerate(items_data):
        if not isinstance(item, dict):
            return (
                False,
                "VALIDATION_ERROR",
                f"Item at index {idx} must be a JSON object.",
                [{"field": f"items[{idx}]", "message": "Expected an object."}],
                {},
            )

        sku = item.get("sku")
        quantity = item.get("quantity")

        if not sku or not isinstance(sku, str):
            return (
                False,
                "VALIDATION_ERROR",
                f"Item at index {idx} requires a valid SKU string.",
                [{"field": f"items[{idx}].sku", "message": "SKU is required."}],
                {},
            )
        sku = sku.strip()

        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            return (
                False,
                "VALIDATION_ERROR",
                f"Item '{sku}' must have an integer quantity of at least 1.",
                [{"field": f"items[{idx}].quantity", "message": "Quantity must be an integer >= 1."}],
                {},
            )

        if sku in seen_skus:
            return (
                False,
                "VALIDATION_ERROR",
                f"Duplicate SKU '{sku}' in order. The same SKU must not appear twice.",
                [{"field": "items", "message": f"Duplicate SKU '{sku}' in order."}],
                {},
            )

        seen_skus.add(sku)
        skus_to_fetch.append(sku)
        parsed_items.append((sku, quantity))

    products = {p.sku: p for p in Product.objects.filter(sku__in=skus_to_fetch)}
    missing_skus = [sku for sku in skus_to_fetch if sku not in products]
    if missing_skus:
        return (
            False,
            "VALIDATION_ERROR",
            f"The following SKUs do not exist: {', '.join(missing_skus)}",
            [{"field": "items", "message": f"Unknown SKU: {sku}"} for sku in missing_skus],
            {},
        )

    return (True, None, None, [], [(products[sku], qty) for sku, qty in parsed_items])


def create_draft_order(dealer_id, items_data, idempotency_key=None, raw_body=None):
    """
    Creates a new DRAFT order with transactional safety and idempotency support.
    STOCK-NEUTRAL: Creates the order without modifying warehouse inventory.
    PRICING SNAPSHOT: Snapshots Product.price to OrderItem.unit_price at creation time.
    """
    if dealer_id is None:
        return (
            None,
            False,
            "VALIDATION_ERROR",
            "dealer_id is required.",
            [{"field": "dealer_id", "message": "dealer_id is required."}],
            400,
        )

    try:
        dealer = Dealer.objects.get(id=dealer_id)
    except (Dealer.DoesNotExist, ValueError):
        return (
            None,
            False,
            "VALIDATION_ERROR",
            f"Dealer with ID {dealer_id} does not exist.",
            [{"field": "dealer_id", "message": "Dealer does not exist."}],
            400,
        )

    valid, err_code, err_msg, details, validated_items = validate_order_items(items_data)
    if not valid:
        return None, False, err_code, err_msg, details, 400

    body_hash = hash_request_body(raw_body) if raw_body is not None else ""

    # Check for existing idempotency key before starting creation
    if idempotency_key:
        existing_record = IdempotencyRecord.objects.filter(key=idempotency_key).first()
        if existing_record:
            if existing_record.request_hash == body_hash:
                return existing_record.order, False, None, None, None, 200
            else:
                return (
                    None,
                    False,
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key has already been used with a different request body.",
                    [],
                    409,
                )

    try:
        with transaction.atomic():
            if idempotency_key:
                existing_record = (
                    IdempotencyRecord.objects.select_for_update()
                    .filter(key=idempotency_key)
                    .first()
                )
                if existing_record:
                    if existing_record.request_hash == body_hash:
                        return existing_record.order, False, None, None, None, 200
                    else:
                        return (
                            None,
                            False,
                            "IDEMPOTENCY_CONFLICT",
                            "Idempotency key has already been used with a different request body.",
                            [],
                            409,
                        )

            order_number = generate_order_number()
            order = Order.objects.create(
                order_number=order_number,
                dealer=dealer,
                status=Order.Status.DRAFT,
            )

            # Snapshot current catalogue price onto each OrderItem
            order_items = [
                OrderItem(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=product.price,
                )
                for product, quantity in validated_items
            ]
            OrderItem.objects.bulk_create(order_items)

            if idempotency_key:
                IdempotencyRecord.objects.create(
                    key=idempotency_key,
                    order=order,
                    request_hash=body_hash,
                )

        return order, True, None, None, None, 201

    except IntegrityError as exc:
        # Handle concurrent race condition on IdempotencyRecord uniqueness
        if idempotency_key:
            existing_record = IdempotencyRecord.objects.filter(key=idempotency_key).first()
            if existing_record:
                if existing_record.request_hash == body_hash:
                    return existing_record.order, False, None, None, None, 200
                else:
                    return (
                        None,
                        False,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency key has already been used with a different request body.",
                        [],
                        409,
                    )
        logger.exception("Unexpected IntegrityError during draft order creation: %s", exc)
        raise


def update_draft_order_items(order, items_data):
    if order.status != Order.Status.DRAFT:
        return (
            None,
            "ORDER_LOCKED",
            f"Cannot edit order {order.order_number} in {order.status} status. Only DRAFT orders can be edited.",
            [],
            409,
        )

    valid, err_code, err_msg, details, validated_items = validate_order_items(items_data)
    if not valid:
        return None, err_code, err_msg, details, 400

    with transaction.atomic():
        order.items.all().delete()
        new_items = [
            OrderItem(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.price,
            )
            for product, quantity in validated_items
        ]
        OrderItem.objects.bulk_create(new_items)
        order.save(update_fields=["updated_at"])

    return order, None, None, [], 200


def confirm_order(order):
    """
    Optional enhancement: Confirm DRAFT order with all-or-nothing stock deduction.
    """
    if order.status != Order.Status.DRAFT:
        return (
            None,
            "INVALID_TRANSITION",
            f"Cannot confirm order {order.order_number} from status {order.status}. Only DRAFT orders can be confirmed.",
            [],
            409,
        )

    items = list(order.items.select_related("product").all())
    if not items:
        return (
            None,
            "VALIDATION_ERROR",
            "Cannot confirm an order with no items.",
            [],
            400,
        )

    # Sort items by product SKU to guarantee deadlock-free locking order
    items.sort(key=lambda x: x.product.sku)

    with transaction.atomic():
        product_ids = [item.product_id for item in items]
        inventories = {
            inv.product_id: inv
            for inv in Inventory.objects.select_for_update().filter(product_id__in=product_ids)
        }

        short_lines = []
        messages = []

        for item in items:
            inv = inventories.get(item.product_id)
            available = inv.quantity if inv else 0
            if available < item.quantity:
                short_lines.append({
                    "sku": item.product.sku,
                    "requested": item.quantity,
                    "available": available,
                })
                messages.append(
                    f"Insufficient stock for {item.product.name}. Available: {available}, Requested: {item.quantity}"
                )

        if short_lines:
            return (
                None,
                "INSUFFICIENT_STOCK",
                ". ".join(messages),
                short_lines,
                409,
            )

        # Deduct stock while preserving each OrderItem.unit_price snapshot
        for item in items:
            inv = inventories[item.product_id]
            inv.quantity -= item.quantity
            inv.save(update_fields=["quantity"])

        order.status = Order.Status.CONFIRMED
        order.save(update_fields=["status", "updated_at"])

    return order, None, None, [], 200


def dispatch_order(order):
    if order.status != Order.Status.CONFIRMED:
        return (
            None,
            "INVALID_TRANSITION",
            f"Cannot dispatch order {order.order_number} from status {order.status}. Only CONFIRMED orders can be dispatched.",
            [],
            409,
        )

    order.status = Order.Status.DISPATCHED
    order.save(update_fields=["status", "updated_at"])
    return order, None, None, [], 200


def deliver_order(order):
    if order.status != Order.Status.DISPATCHED:
        return (
            None,
            "INVALID_TRANSITION",
            f"Cannot deliver order {order.order_number} from status {order.status}. Only DISPATCHED orders can be delivered.",
            [],
            409,
        )

    order.status = Order.Status.DELIVERED
    order.save(update_fields=["status", "updated_at"])
    return order, None, None, [], 200


def cancel_order(order):
    if order.status not in (Order.Status.DRAFT, Order.Status.CONFIRMED):
        return (
            None,
            "INVALID_TRANSITION",
            f"Cannot cancel order {order.order_number} from status {order.status}. Only DRAFT or CONFIRMED orders can be cancelled.",
            [],
            409,
        )

    with transaction.atomic():
        if order.status == Order.Status.CONFIRMED:
            items = list(order.items.select_related("product").all())
            items.sort(key=lambda x: x.product.sku)
            for item in items:
                inv = Inventory.objects.select_for_update().get(product=item.product)
                inv.quantity += item.quantity
                inv.save(update_fields=["quantity"])

        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])

    return order, None, None, [], 200
