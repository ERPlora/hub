"""Django admin of the inventory app: full CRUD on every table for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations'
rules (the SKU, the unit's step, the ledger that the screens never edit), so it warns rather than
prevents. What the database fills in (ids and timestamps) is shown, not edited.
"""

from django.contrib import admin

from apps.inventory.models import Category, Product, ProductCategory, SaleStock, Settings, StockMovement


AUTOMATIC = ("id", "created_at", "updated_at")


class ProductCategoryInline(admin.TabularInline):
    model = ProductCategory
    extra = 0
    fields = ("category",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "price", "stock", "unit", "tax_category", "is_active", "is_deleted")
    list_filter = ("is_active", "is_deleted", "product_type", "unit")
    search_fields = ("name", "sku", "ean13")
    fields = (
        "id",
        "name",
        "sku",
        "ean13",
        "description",
        "product_type",
        "price",
        "cost",
        "stock",
        "low_stock_threshold",
        "unit",
        "price_quantity",
        "pricing_unit",
        "tax_category",
        "track_stock",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )
    readonly_fields = AUTOMATIC
    inlines = [ProductCategoryInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "tax_category", "is_deleted")
    readonly_fields = AUTOMATIC
    list_filter = ("is_deleted",)
    search_fields = ("name", "slug")
    fields = (
        "id",
        "name",
        "slug",
        "description",
        "icon",
        "color",
        "order",
        "tax_category",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "product", "movement_type", "qty", "stock_after", "reference", "actor")
    list_filter = ("movement_type",)
    search_fields = ("product__name", "product__sku", "reference")
    list_select_related = ("product",)
    readonly_fields = ("id",)
    fields = ("id", "product", "movement_type", "qty", "stock_after", "reason", "reference", "unit_cost", "actor", "created_at")


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ("allow_sell_without_stock", "low_stock_threshold", "track_stock", "updated_at", "updated_by")
    readonly_fields = ("id", "updated_at")
    fields = ("id", "allow_sell_without_stock", "low_stock_threshold", "track_stock", "updated_at", "updated_by")


@admin.register(SaleStock)
class SaleStockAdmin(admin.ModelAdmin):
    list_display = ("sale_id", "state", "created_at", "updated_at")
    readonly_fields = AUTOMATIC
    list_filter = ("state",)
    search_fields = ("sale_id",)
    fields = ("id", "sale_id", "state", "created_at", "updated_at")
