from decimal import Decimal
from rest_framework import serializers

from .models import Dealer, Order, OrderItem, Product


class ProductSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)

    class Meta:
        model = Product
        fields = [
            "sku",
            "name",
            "category",
            "brand",
            "vehicle_fitment",
            "price",
            "stock",
            "description",
        ]
        read_only_fields = ["sku", "stock"]
        extra_kwargs = {
            "sku": {"validators": []},
        }

    def get_stock(self, obj):
        try:
            return obj.inventory.quantity
        except (Product.inventory.RelatedObjectDoesNotExist, AttributeError):
            return 0

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        if value.as_tuple().exponent < -2:
            raise serializers.ValidationError("Price must have at most 2 decimal places.")
        return value


class ProductCreateSerializer(ProductSerializer):
    class Meta(ProductSerializer.Meta):
        read_only_fields = ["stock"]


class ProductUpdateSerializer(ProductSerializer):
    pass


class DealerSerializer(serializers.ModelSerializer):
    credit_limit = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        coerce_to_string=True,
        required=False,
        default=Decimal("0.00"),
    )

    class Meta:
        model = Dealer
        fields = [
            "id",
            "dealer_code",
            "name",
            "city",
            "phone",
            "email",
            "gstin",
            "credit_limit",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "dealer_code": {"validators": []},
        }


class OrderItemSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    unit_price = serializers.SerializerMethodField()
    line_subtotal = serializers.SerializerMethodField()
    line_tax = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "sku",
            "name",
            "quantity",
            "unit_price",
            "line_subtotal",
            "line_tax",
            "line_total",
        ]

    def get_unit_price(self, obj):
        return f"{obj.unit_price:.2f}"

    def get_line_subtotal(self, obj):
        return f"{obj.line_subtotal:.2f}"

    def get_line_tax(self, obj):
        return f"{obj.line_tax:.2f}"

    def get_line_total(self, obj):
        return f"{obj.line_total:.2f}"


class OrderSerializer(serializers.ModelSerializer):
    dealer_id = serializers.IntegerField(source="dealer.id", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    tax_total = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "order_number",
            "dealer_id",
            "status",
            "items",
            "subtotal",
            "tax_total",
            "grand_total",
            "created_at",
            "updated_at",
        ]

    def get_subtotal(self, obj):
        return f"{obj.subtotal:.2f}"

    def get_tax_total(self, obj):
        return f"{obj.tax_total:.2f}"

    def get_grand_total(self, obj):
        return f"{obj.grand_total:.2f}"
