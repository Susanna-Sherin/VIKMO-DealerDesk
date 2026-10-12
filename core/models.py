from django.db import models


class Product(models.Model):
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    brand = models.CharField(max_length=100)
    vehicle_fitment = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.sku} - {self.name}"


class Inventory(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="inventory",
    )
    quantity = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.sku}: {self.quantity}"


class Dealer(models.Model):
    dealer_code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    gstin = models.CharField(max_length=20, blank=True, default="")
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    def __str__(self):
        return f"{self.dealer_code} - {self.name}"


class Order(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        DISPATCHED = "DISPATCHED", "Dispatched"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    order_number = models.CharField(max_length=30, unique=True)
    dealer = models.ForeignKey(
        Dealer,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.order.order_number} - {self.product.sku}"