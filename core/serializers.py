from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()

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
        except Product.inventory.RelatedObjectDoesNotExist:
            return 0

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Price must be greater than zero."
            )
        return value


class ProductCreateSerializer(ProductSerializer):
    class Meta(ProductSerializer.Meta):
        read_only_fields = ["stock"]


class ProductUpdateSerializer(ProductSerializer):
    pass
