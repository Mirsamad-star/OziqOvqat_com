from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=10, default="🍽️", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Unit(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Color(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.IntegerField()
    about = models.TextField()
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    rating = models.IntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    sale = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    is_active = models.BooleanField(default=True)
    shopping_cost = models.IntegerField(default=0)
    min_count = models.IntegerField(default=1)
    men_olgan_narx = models.IntegerField(default=0)
    unit = models.CharField(max_length=50, default="dona")
    color = models.CharField(max_length=50, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    likes_count = models.PositiveIntegerField(default=0)
    cover_url = models.URLField(max_length=500, blank=True, default="")
    gallery_urls = models.TextField(
        blank=True,
        default="",
        help_text="Qo‘shimcha rasm URL lari (har qatorda bitta)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="products",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def final_price(self):
        if self.sale > 0:
            return int(self.price * (100 - self.sale) / 100)
        return self.price

    def get_gallery(self):
        """Yuklangan rasmlar + URL lar (3–4 ta)."""
        urls = []
        for img in self.images.all()[:6]:
            try:
                urls.append(img.image.url)
            except Exception:
                pass
        if self.cover_url and self.cover_url not in urls:
            urls.insert(0, self.cover_url)
        for line in (self.gallery_urls or "").splitlines():
            u = line.strip()
            if u and u not in urls:
                urls.append(u)
        return urls[:6]

    def get_cover(self):
        g = self.get_gallery()
        if g:
            return g[0]
        # Nom bilan placeholder (rasm bo‘lmasa ham)
        from urllib.parse import quote
        label = quote((self.name or "Product")[:20])
        return f"https://placehold.co/800x800/16a34a/ffffff/png?text={label}"


class ProductImage(models.Model):
    image = models.ImageField(upload_to="products/")
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )

    def __str__(self):
        return self.product.name


class ProductReview(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    name = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} — {self.name} — {self.rating}/5"


class ProductLike(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="likes",
    )
    session_key = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="product_likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["product", "session_key"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Like {self.product.name}"


class CartItem(models.Model):
    session_key = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart_items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["session_key", "product"]]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    @property
    def subtotal(self):
        return self.product.final_price * self.quantity


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Kutilmoqda"),
        ("confirmed", "Tasdiqlandi"),
        ("delivering", "Yetkazilmoqda"),
        ("done", "Yakunlandi"),
        ("cancelled", "Bekor qilindi"),
    ]
    session_key = models.CharField(max_length=64, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    address = models.TextField()
    note = models.TextField(blank=True)
    total = models.IntegerField(default=0)
    discount_percent = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Buyurtma #{self.pk} — {self.full_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
    )
    product_name = models.CharField(max_length=200)
    price = models.IntegerField()
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity


class GameDiscount(models.Model):
    """O'yinda yutganda beriladigan chegirma kodi."""
    session_key = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    discount_percent = models.PositiveIntegerField(default=10)
    code = models.CharField(max_length=20, unique=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} — {self.discount_percent}%"
