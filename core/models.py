from decimal import Decimal, ROUND_HALF_UP
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

    @property
    def subtotal(self):
        total = sum((item.line_subtotal for item in self.items.all()), Decimal("0.00"))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def tax_total(self):
        total = sum((item.line_tax for item in self.items.all()), Decimal("0.00"))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def grand_total(self):
        return self.subtotal + self.tax_total


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

    @property
    def line_subtotal(self):
        # Uses the snapshotted unit_price saved at creation time
        sub = self.unit_price * self.quantity
        return sub.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def line_tax(self):
        tax = self.line_subtotal * Decimal("0.18")
        return tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def line_total(self):
        return self.line_subtotal + self.line_tax


class OrderSequence(models.Model):
    date_str = models.CharField(max_length=8, unique=True)
    last_seq = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.date_str}: {self.last_seq}"


class IdempotencyRecord(models.Model):
    key = models.CharField(max_length=255, unique=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    request_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.key} -> {self.order.order_number}"


class ConversationMessage(models.Model):
    session_id = models.CharField(max_length=100, db_index=True)
    dealer = models.ForeignKey(Dealer, on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=20)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.session_id} [{self.role}]: {self.content[:30]}"