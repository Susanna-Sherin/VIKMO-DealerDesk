import json
from decimal import Decimal
from urllib.parse import urlencode

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .assistant import chat_assistant
from .models import Dealer, Inventory, Order, Product
from .order_service import (
    cancel_order,
    confirm_order,
    create_draft_order,
    deliver_order,
    dispatch_order,
    update_draft_order_items,
)
from .serializers import (
    DealerSerializer,
    OrderSerializer,
    ProductCreateSerializer,
    ProductSerializer,
    ProductUpdateSerializer,
)
from .supplier_sync import sync_supplier_catalogue
from ml.forecast import calculate_reorder_suggestions, load_cached_forecast_map, load_forecast_skus


def health(request):
    return JsonResponse({"status": "ok"})


def error_response(code, message, status, details=None):
    return JsonResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
            }
        },
        status=status,
    )


def validation_error(serializer):
    details = [
        {"field": field, "message": str(message)}
        for field, messages in serializer.errors.items()
        for message in messages
    ]
    return error_response(
        "VALIDATION_ERROR", "Validation error.", 400, details
    )


# ---- Product APIs -----------------------------------------------------------

@csrf_exempt
def product_list(request):
    if request.method == "GET":
        products = Product.objects.all().select_related("inventory").order_by("sku")

        search = request.GET.get("search", "").strip()
        category = request.GET.get("category", "").strip()
        vehicle = request.GET.get("vehicle", "").strip()

        if search:
            products = products.filter(
                Q(sku__icontains=search)
                | Q(name__icontains=search)
                | Q(brand__icontains=search)
            )

        if category:
            products = products.filter(category=category)

        if vehicle:
            products = products.filter(vehicle_fitment__icontains=vehicle)

        try:
            page = int(request.GET.get("page", "1"))
            page_size = int(request.GET.get("page_size", "20"))
        except ValueError:
            return error_response(
                "VALIDATION_ERROR",
                "page and page_size must be integers.",
                400,
            )

        if page < 1 or not 1 <= page_size <= 100:
            return error_response(
                "VALIDATION_ERROR",
                "page must be at least 1 and page_size must be between 1 and 100.",
                400,
            )

        count = products.count()
        start = (page - 1) * page_size
        results = products[start:start + page_size]
        params = request.GET.copy()

        next_url = None
        previous_url = None

        if start + page_size < count:
            params["page"] = str(page + 1)
            next_url = request.build_absolute_uri(f"{request.path}?{urlencode(params)}")

        if page > 1 and start < count:
            params["page"] = str(page - 1)
            previous_url = request.build_absolute_uri(f"{request.path}?{urlencode(params)}")

        return JsonResponse({
            "count": count,
            "next": next_url,
            "previous": previous_url,
            "results": ProductSerializer(results, many=True).data,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error_response(
                "VALIDATION_ERROR", "Request body must contain valid JSON.", 400
            )

        serializer = ProductCreateSerializer(data=data)
        if not serializer.is_valid():
            return validation_error(serializer)

        if Product.objects.filter(sku=serializer.validated_data["sku"]).exists():
            return error_response(
                "DUPLICATE", "A product with this SKU already exists.", 409
            )

        try:
            with transaction.atomic():
                product = serializer.save()
                Inventory.objects.create(product=product, quantity=0)
        except IntegrityError:
            return error_response(
                "DUPLICATE", "A product with this SKU already exists.", 409
            )

        return JsonResponse(ProductSerializer(product).data, status=201)

    response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
    response["Allow"] = "GET, POST"
    return response


@csrf_exempt
def product_detail(request, sku):
    try:
        product = Product.objects.select_related("inventory").get(sku=sku)
    except Product.DoesNotExist:
        return error_response("NOT_FOUND", "Product not found.", 404)

    if request.method == "GET":
        return JsonResponse(ProductSerializer(product).data)

    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error_response(
                "VALIDATION_ERROR", "Request body must contain valid JSON.", 400
            )

        # SKU cannot change
        if "sku" in data and data["sku"] != product.sku:
            return error_response(
                "VALIDATION_ERROR", "Product SKU cannot be changed.", 400
            )

        serializer = ProductUpdateSerializer(product, data=data, partial=True)
        if not serializer.is_valid():
            return validation_error(serializer)

        product = serializer.save()
        return JsonResponse(ProductSerializer(product).data)

    response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
    response["Allow"] = "GET, PATCH"
    return response


# ---- Inventory APIs ---------------------------------------------------------

@csrf_exempt
def inventory_update(request, sku):
    if request.method != "PUT":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "PUT"
        return response

    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        return error_response("NOT_FOUND", "Product not found.", 404)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error_response(
            "VALIDATION_ERROR", "Request body must contain valid JSON.", 400
        )

    if not isinstance(data, dict):
        return error_response(
            "VALIDATION_ERROR", "Request body must be a JSON object.", 400
        )

    quantity = data.get("quantity")

    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
        return error_response(
            "VALIDATION_ERROR",
            "Quantity must be a non-negative integer.",
            400,
            [{"field": "quantity", "message": "Enter an integer greater than or equal to zero."}],
        )

    inventory, created = Inventory.objects.get_or_create(
        product=product,
        defaults={"quantity": quantity},
    )

    if not created:
        inventory.quantity = quantity
        inventory.save(update_fields=["quantity"])

    return JsonResponse({
        "sku": product.sku,
        "quantity": inventory.quantity,
    })


# ---- Dealer APIs ------------------------------------------------------------

@csrf_exempt
def dealer_list(request):
    if request.method == "GET":
        dealers = Dealer.objects.all().order_by("id")

        try:
            page = int(request.GET.get("page", "1"))
            page_size = int(request.GET.get("page_size", "20"))
        except ValueError:
            return error_response(
                "VALIDATION_ERROR", "page and page_size must be integers.", 400
            )

        if page < 1 or not 1 <= page_size <= 100:
            return error_response(
                "VALIDATION_ERROR", "Invalid pagination parameters.", 400
            )

        count = dealers.count()
        start = (page - 1) * page_size
        results = dealers[start:start + page_size]
        params = request.GET.copy()

        next_url = None
        previous_url = None

        if start + page_size < count:
            params["page"] = str(page + 1)
            next_url = request.build_absolute_uri(f"{request.path}?{urlencode(params)}")

        if page > 1 and start < count:
            params["page"] = str(page - 1)
            previous_url = request.build_absolute_uri(f"{request.path}?{urlencode(params)}")

        return JsonResponse({
            "count": count,
            "next": next_url,
            "previous": previous_url,
            "results": DealerSerializer(results, many=True).data,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error_response(
                "VALIDATION_ERROR", "Request body must contain valid JSON.", 400
            )

        if not isinstance(data, dict):
            return error_response(
                "VALIDATION_ERROR", "Request body must be a JSON object.", 400
            )

        serializer = DealerSerializer(data=data)
        if not serializer.is_valid():
            return validation_error(serializer)

        dealer_code = serializer.validated_data["dealer_code"]
        if Dealer.objects.filter(dealer_code=dealer_code).exists():
            return error_response(
                "DUPLICATE", "A dealer with this dealer_code already exists.", 409
            )

        try:
            with transaction.atomic():
                dealer = serializer.save()
        except IntegrityError:
            return error_response(
                "DUPLICATE", "A dealer with this dealer_code already exists.", 409
            )

        return JsonResponse(DealerSerializer(dealer).data, status=201)

    response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
    response["Allow"] = "GET, POST"
    return response


@csrf_exempt
def dealer_detail(request, dealer_id):
    if request.method != "GET":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "GET"
        return response

    try:
        dealer = Dealer.objects.get(id=dealer_id)
    except Dealer.DoesNotExist:
        return error_response("NOT_FOUND", "Dealer not found.", 404)

    return JsonResponse(DealerSerializer(dealer).data)


# ---- Order APIs -------------------------------------------------------------

@csrf_exempt
def order_list(request):
    if request.method == "GET":
        orders = Order.objects.all().select_related("dealer").prefetch_related("items__product").order_by("-created_at", "-id")

        dealer_id = request.GET.get("dealer_id")
        status_param = request.GET.get("status")

        if dealer_id:
            try:
                orders = orders.filter(dealer_id=int(dealer_id))
            except ValueError:
                return error_response("VALIDATION_ERROR", "dealer_id must be an integer.", 400)

        if status_param:
            orders = orders.filter(status=status_param.strip().upper())

        try:
            page = int(request.GET.get("page", "1"))
            page_size = int(request.GET.get("page_size", "20"))
        except ValueError:
            return error_response("VALIDATION_ERROR", "page and page_size must be integers.", 400)

        if page < 1 or not 1 <= page_size <= 100:
            return error_response("VALIDATION_ERROR", "page must be at least 1 and page_size between 1 and 100.", 400)

        count = orders.count()
        start = (page - 1) * page_size
        results = orders[start:start + page_size]
        params = request.GET.copy()

        next_url = None
        previous_url = None

        if start + page_size < count:
            params["page"] = str(page + 1)
            next_url = request.build_absolute_uri(f"{request.path}?{urlencode(params)}")

        if page > 1 and start < count:
            params["page"] = str(page - 1)
            previous_url = request.build_absolute_uri(f"{request.path}?{urlencode(params)}")

        return JsonResponse({
            "count": count,
            "next": next_url,
            "previous": previous_url,
            "results": OrderSerializer(results, many=True).data,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error_response("VALIDATION_ERROR", "Request body must contain valid JSON.", 400)

        if not isinstance(data, dict):
            return error_response("VALIDATION_ERROR", "Request body must be a JSON object.", 400)

        idempotency_key = request.headers.get("Idempotency-Key") or request.META.get("HTTP_IDEMPOTENCY_KEY")

        order, created, err_code, err_msg, details, status_code = create_draft_order(
            dealer_id=data.get("dealer_id"),
            items_data=data.get("items"),
            idempotency_key=idempotency_key,
            raw_body=request.body,
        )

        if err_code:
            return error_response(err_code, err_msg, status_code, details)

        return JsonResponse(OrderSerializer(order).data, status=status_code)

    response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
    response["Allow"] = "GET, POST"
    return response


@csrf_exempt
def order_detail(request, order_number):
    try:
        order = Order.objects.select_related("dealer").prefetch_related("items__product").get(order_number=order_number)
    except Order.DoesNotExist:
        return error_response("NOT_FOUND", "Order not found.", 404)

    if request.method == "GET":
        return JsonResponse(OrderSerializer(order).data)

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error_response("VALIDATION_ERROR", "Request body must contain valid JSON.", 400)

        if not isinstance(data, dict):
            return error_response("VALIDATION_ERROR", "Request body must be a JSON object.", 400)

        items_data = data.get("items")
        order, err_code, err_msg, details, status_code = update_draft_order_items(order, items_data)
        if err_code:
            return error_response(err_code, err_msg, status_code, details)

        return JsonResponse(OrderSerializer(order).data)

    response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
    response["Allow"] = "GET, PUT"
    return response


@csrf_exempt
def order_confirm(request, order_number):
    if request.method != "POST":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "POST"
        return response

    try:
        order = Order.objects.select_related("dealer").prefetch_related("items__product").get(order_number=order_number)
    except Order.DoesNotExist:
        return error_response("NOT_FOUND", "Order not found.", 404)

    order, err_code, err_msg, details, status_code = confirm_order(order)
    if err_code:
        return error_response(err_code, err_msg, status_code, details)

    return JsonResponse(OrderSerializer(order).data)


@csrf_exempt
def order_dispatch(request, order_number):
    if request.method != "POST":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "POST"
        return response

    try:
        order = Order.objects.select_related("dealer").prefetch_related("items__product").get(order_number=order_number)
    except Order.DoesNotExist:
        return error_response("NOT_FOUND", "Order not found.", 404)

    order, err_code, err_msg, details, status_code = dispatch_order(order)
    if err_code:
        return error_response(err_code, err_msg, status_code, details)

    return JsonResponse(OrderSerializer(order).data)


@csrf_exempt
def order_deliver(request, order_number):
    if request.method != "POST":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "POST"
        return response

    try:
        order = Order.objects.select_related("dealer").prefetch_related("items__product").get(order_number=order_number)
    except Order.DoesNotExist:
        return error_response("NOT_FOUND", "Order not found.", 404)

    order, err_code, err_msg, details, status_code = deliver_order(order)
    if err_code:
        return error_response(err_code, err_msg, status_code, details)

    return JsonResponse(OrderSerializer(order).data)


@csrf_exempt
def order_cancel(request, order_number):
    if request.method != "POST":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "POST"
        return response

    try:
        order = Order.objects.select_related("dealer").prefetch_related("items__product").get(order_number=order_number)
    except Order.DoesNotExist:
        return error_response("NOT_FOUND", "Order not found.", 404)

    order, err_code, err_msg, details, status_code = cancel_order(order)
    if err_code:
        return error_response(err_code, err_msg, status_code, details)

    return JsonResponse(OrderSerializer(order).data)


# ---- Dealer Assistant API ---------------------------------------------------

@csrf_exempt
def assistant_chat(request):
    if request.method != "POST":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "POST"
        return response

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error_response("VALIDATION_ERROR", "Request body must contain valid JSON.", 400)

    if not isinstance(data, dict):
        return error_response("VALIDATION_ERROR", "Request body must be a JSON object.", 400)

    session_id = data.get("session_id")
    dealer_id = data.get("dealer_id")
    message = data.get("message")

    if not session_id or not isinstance(session_id, str) or not session_id.strip():
        return error_response("VALIDATION_ERROR", "session_id is required.", 400)

    if not message or not isinstance(message, str) or not message.strip():
        return error_response("VALIDATION_ERROR", "message is required.", 400)

    if dealer_id is not None:
        if isinstance(dealer_id, bool) or not isinstance(dealer_id, int):
            return error_response("VALIDATION_ERROR", "dealer_id must be an integer.", 400)
        if not Dealer.objects.filter(id=dealer_id).exists():
            return error_response("VALIDATION_ERROR", f"Dealer {dealer_id} does not exist.", 400)

    result = chat_assistant(
        session_id=session_id.strip(),
        dealer_id=dealer_id,
        message=message.strip(),
    )

    return JsonResponse(result, status=200)


# ---- Forecasting & Reorder APIs ---------------------------------------------

@csrf_exempt
def forecast_detail(request, sku):
    if request.method != "GET":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "GET"
        return response

    lead_skus = load_forecast_skus()
    if sku not in lead_skus:
        return error_response("NOT_FOUND", f"SKU '{sku}' is not a forecast SKU.", 404)

    forecast_map = load_cached_forecast_map()
    sku_forecast = forecast_map.get(sku, [])
    if not sku_forecast:
        return error_response("NOT_FOUND", f"No forecast available for SKU '{sku}'.", 404)

    return JsonResponse({
        "sku": sku,
        "forecast": sku_forecast,
    })


@csrf_exempt
def reorder_suggestions(request):
    if request.method != "GET":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "GET"
        return response

    def get_live_stock(sku):
        try:
            return Inventory.objects.get(product__sku=sku).quantity
        except Inventory.DoesNotExist:
            return 0

    results = calculate_reorder_suggestions(inventory_lookup_fn=get_live_stock)
    return JsonResponse({"results": results})


# ---- Supplier Sync API ------------------------------------------------------

@csrf_exempt
def supplier_sync_view(request):
    if request.method != "POST":
        response = error_response("METHOD_NOT_ALLOWED", "Method not allowed.", 405)
        response["Allow"] = "POST"
        return response

    result, err_code, err_msg, status_code = sync_supplier_catalogue()
    if err_code:
        return error_response(err_code, err_msg, status_code)

    return JsonResponse(result, status=200)


# ---- Operations Portal (Frontend) -------------------------------------------

def portal_view(request):
    """
    Renders the VIKMO DealerDesk Operations Portal for distributors and dealers.
    """
    return render(request, "core/portal.html")
