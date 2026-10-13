import csv
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Dealer, Inventory, Product


class Command(BaseCommand):
    help = "Load data from CSV files in data/ into PostgreSQL. Safe and idempotent to run multiple times."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            type=str,
            default=str(settings.DATA_DIR),
            help="Path to directory containing CSV data files",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["data_dir"])
        if not data_dir.exists():
            self.stderr.write(self.style.ERROR(f"Data directory not found: {data_dir}"))
            return

        self.stdout.write(f"Seeding data from {data_dir}...")

        self.seed_dealers(data_dir / "dealers.csv")
        self.seed_catalogue(data_dir / "catalogue.csv")

        self.stdout.write(self.style.SUCCESS("Data seeding completed successfully."))

    def seed_dealers(self, csv_path):
        if not csv_path.exists():
            self.stderr.write(self.style.WARNING(f"File not found: {csv_path}"))
            return

        dealers_created = 0
        dealers_updated = 0

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            with transaction.atomic():
                for row in reader:
                    dealer_code = row["dealer_code"].strip()
                    name = row["name"].strip()
                    city = row.get("city", "").strip()
                    phone = row.get("phone", "").strip()
                    email = row.get("email", "").strip()
                    gstin = row.get("gstin", "").strip()
                    credit_limit_raw = row.get("credit_limit", "0").strip()
                    credit_limit = Decimal(credit_limit_raw) if credit_limit_raw else Decimal("0.00")

                    dealer, created = Dealer.objects.update_or_create(
                        dealer_code=dealer_code,
                        defaults={
                            "name": name,
                            "city": city,
                            "phone": phone,
                            "email": email,
                            "gstin": gstin,
                            "credit_limit": credit_limit,
                        },
                    )
                    if created:
                        dealers_created += 1
                    else:
                        dealers_updated += 1

        total = Dealer.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Dealers: {dealers_created} created, {dealers_updated} updated (Total in DB: {total})"
            )
        )

    def seed_catalogue(self, csv_path):
        if not csv_path.exists():
            self.stderr.write(self.style.WARNING(f"File not found: {csv_path}"))
            return

        products_created = 0
        products_updated = 0

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            with transaction.atomic():
                for row in reader:
                    sku = row["sku"].strip()
                    name = row["name"].strip()
                    category = row.get("category", "").strip()
                    brand = row.get("brand", "").strip()
                    vehicle_fitment = row.get("vehicle_fitment", "").strip()
                    price = Decimal(row["price"].strip())
                    stock = int(row.get("stock", 0))
                    description = row.get("description", "").strip()

                    product, created = Product.objects.update_or_create(
                        sku=sku,
                        defaults={
                            "name": name,
                            "category": category,
                            "brand": brand,
                            "vehicle_fitment": vehicle_fitment,
                            "price": price,
                            "description": description,
                        },
                    )

                    Inventory.objects.update_or_create(
                        product=product,
                        defaults={"quantity": stock},
                    )

                    if created:
                        products_created += 1
                    else:
                        products_updated += 1

        total_prod = Product.objects.count()
        total_inv = Inventory.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Catalogue: {products_created} created, {products_updated} updated "
                f"(Total Products: {total_prod}, Total Inventory: {total_inv})"
            )
        )
