from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("products/", views.product_list),
    path("products/<str:sku>/", views.product_detail),
    path("inventory/<str:sku>/", views.inventory_update),
    path("dealers/", views.dealer_list),
    path("dealers/<int:dealer_id>/", views.dealer_detail),
    path("orders/", views.order_list),
    path("orders/<str:order_number>/", views.order_detail),
    path("orders/<str:order_number>/confirm/", views.order_confirm),
    path("orders/<str:order_number>/dispatch/", views.order_dispatch),
    path("orders/<str:order_number>/deliver/", views.order_deliver),
    path("orders/<str:order_number>/cancel/", views.order_cancel),
    path("assistant/chat/", views.assistant_chat),
    path("forecast/<str:sku>/", views.forecast_detail),
    path("reorder-suggestions/", views.reorder_suggestions),
    path("sync/supplier/", views.supplier_sync_view),
]
