from django.contrib import admin
from django.db import transaction

from .models import (
    CartItem, Category, Color, GameDiscount, Order, OrderItem,
    Product, ProductImage, ProductLike, ProductReview, Size, Unit,
)
from .email_utils import send_order_status_email


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "price", "quantity")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "price", "category", "rating", "sale", "likes_count", "is_active", "created_at")
    list_filter = ("is_active", "category")
    search_fields = ("name", "about")


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "name", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("product__name", "name", "comment")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "phone", "total", "discount_percent", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("full_name", "phone")
    list_editable = ("status",)
    inlines = [OrderItemInline]
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        old_status = None
        if change and obj.pk:
            try:
                old_status = Order.objects.get(pk=obj.pk).status
            except Order.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)
        if change and old_status and old_status != obj.status:
            order_id = obj.pk
            status_now = obj.status

            def _notify():
                try:
                    o = Order.objects.filter(pk=order_id).first()
                    if o:
                        send_order_status_email(o, old_status=old_status)
                except Exception:
                    pass

            transaction.on_commit(_notify)


admin.site.register(ProductImage)
admin.site.register(Category)
admin.site.register(Unit)
admin.site.register(Size)
admin.site.register(Color)
admin.site.register(ProductLike)
admin.site.register(CartItem)
admin.site.register(OrderItem)
admin.site.register(GameDiscount)
