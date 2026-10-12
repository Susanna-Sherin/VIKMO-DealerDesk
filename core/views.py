
import json
from urllib.parse import urlencode

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Dealer, Inventory, Product
from .serializers import (
    DealerSerializer,
    ProductCreateSerializer,
    ProductSerializer,
    ProductUpdateSerializer,
)


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
        "VALIDATION_ERROR", "Invalid product data.", 400, details
    )


@csrf_exempt
def product_list(request):
    if request.method == "GET":
        products = Product.objects.all().order_by("sku")

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
            products = products.filter(
                vehicle_fitment__icontains=vehicle
            )

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
            next_url = request.build_absolute_uri(
                f"{request.path}?{urlencode(params)}"
            )

        if page > 1 and start < count:
            params = request.GET.copy()
            params["page"] = str(page - 1)
            previous_url = request.build_absolute_uri(
                f"{request.path}?{urlencode(params)}"
            )

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

        if Product.objects.filter(
            sku=serializer.validated_data["sku"]
        ).exists():
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

    response = error_response(
        "METHOD_NOT_ALLOWED", "Method not allowed.", 405
    )
    response["Allow"] = "GET, POST"
    return response


@csrf_exempt
def product_detail(request, sku):
    try:
        product = Product.objects.get(sku=sku)
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

        serializer = ProductUpdateSerializer(
            product, data=data, partial=True
        )
        if not serializer.is_valid():
            return validation_error(serializer)

        product = serializer.save()
        return JsonResponse(ProductSerializer(product).data)

    response = error_response(
        "METHOD_NOT_ALLOWED", "Method not allowed.", 405
    )
    response["Allow"] = "GET, PATCH"
    return response



@csrf_exempt
def inventory_update(request, sku):
    if request.method != "PUT":
        response = error_response(
            "METHOD_NOT_ALLOWED", "Method not allowed.", 405
        )
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
            "VALIDATION_ERROR",
            "Request body must contain valid JSON.",
            400,
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




@csrf_exempt
def dealer_list(request):
    if request.method == "GET":
        dealers = Dealer.objects.all().order_by("id")

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
                "Invalid pagination parameters.",
                400,
            )

        count = dealers.count()
        start = (page - 1) * page_size
        results = dealers[start:start + page_size]
        params = request.GET.copy()

        next_url = None
        previous_url = None

        if start + page_size < count:
            params["page"] = str(page + 1)
            next_url = request.build_absolute_uri(
                f"{request.path}?{urlencode(params)}"
            )

        if page > 1 and start < count:
            params = request.GET.copy()
            params["page"] = str(page - 1)
            previous_url = request.build_absolute_uri(
                f"{request.path}?{urlencode(params)}"
            )

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
                "VALIDATION_ERROR",
                "Request body must contain valid JSON.",
                400,
            )

        if not isinstance(data, dict):
            return error_response(
                "VALIDATION_ERROR",
                "Request body must be a JSON object.",
                400,
            )

        serializer = DealerSerializer(data=data)

        if not serializer.is_valid():
            details = [
                {"field": field, "message": str(message)}
                for field, messages in serializer.errors.items()
                for message in messages
            ]
            return error_response(
                "VALIDATION_ERROR",
                "Invalid dealer data.",
                400,
                details,
            )

        dealer_code = serializer.validated_data["dealer_code"]

        if Dealer.objects.filter(dealer_code=dealer_code).exists():
            return error_response(
                "DUPLICATE",
                "A dealer with this dealer_code already exists.",
                409,
            )

        try:
            with transaction.atomic():
                dealer = serializer.save()
        except IntegrityError:
            return error_response(
                "DUPLICATE",
                "A dealer with this dealer_code already exists.",
                409,
            )

        return JsonResponse(DealerSerializer(dealer).data, status=201)

    response = error_response(
        "METHOD_NOT_ALLOWED",
        "Method not allowed.",
        405,
    )
    response["Allow"] = "GET, POST"
    return response


@csrf_exempt
def dealer_detail(request, dealer_id):
    if request.method != "GET":
        response = error_response(
            "METHOD_NOT_ALLOWED",
            "Method not allowed.",
            405,
        )
        response["Allow"] = "GET"
        return response

    try:
        dealer = Dealer.objects.get(id=dealer_id)
    except Dealer.DoesNotExist:
        return error_response(
            "NOT_FOUND",
            "Dealer not found.",
            404,
        )

    return JsonResponse(DealerSerializer(dealer).data)
