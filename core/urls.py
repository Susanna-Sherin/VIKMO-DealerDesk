from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("products/", views.product_list),
    path("products/<str:sku>/", views.product_detail),
    path("inventory/<str:sku>/", views.inventory_update),
]
