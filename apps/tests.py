from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from .models import Category, Product, Order, OrderItem, CartItem
from .email_utils import send_welcome_email, send_order_confirmation


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SITE_URL="http://testserver",
)
class EmailSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="secret123",
        )
        self.cat = Category.objects.create(name="Meva", slug="meva")
        self.product = Product.objects.create(
            name="Olma",
            price=10000,
            about="Yangi olma",
            category=self.cat,
            is_active=True,
        )

    def test_welcome_email_on_register(self):
        mail.outbox.clear()
        resp = self.client.post(
            reverse("register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "secret123",
                "password2": "secret123",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="newuser").exists())
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("Xush kelibsiz", mail.outbox[0].subject)

    def test_order_confirmation_email(self):
        mail.outbox.clear()
        session = self.client.session
        session.save()
        sk = self.client.session.session_key
        CartItem.objects.create(
            session_key=sk,
            user=self.user,
            product=self.product,
            quantity=2,
        )
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                reverse("order_create"),
                {
                    "full_name": "Test User",
                    "phone": "+998901234567",
                    "address": "Toshkent",
                    "note": "",
                },
            )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Order.objects.exists())
        self.assertGreaterEqual(len(mail.outbox), 1)
        subjects = " ".join(m.subject for m in mail.outbox)
        self.assertTrue("Buyurtma" in subjects or "Yangi buyurtma" in subjects)

    def test_send_welcome_helper(self):
        mail.outbox.clear()
        ok = send_welcome_email(self.user)
        self.assertTrue(ok)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("test@example.com", mail.outbox[0].to)

    def test_password_reset_page(self):
        resp = self.client.get(reverse("password_reset"))
        self.assertEqual(resp.status_code, 200)
        mail.outbox.clear()
        resp = self.client.post(reverse("password_reset"), {"email": "test@example.com"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_order_status_email(self):
        order = Order.objects.create(
            user=self.user,
            full_name="Test",
            phone="123",
            address="Addr",
            total=10000,
            status="pending",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name="Olma",
            price=10000,
            quantity=1,
        )
        admin = User.objects.create_user(
            username="Mirsamad", email="admin@test.com", password="123456",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(admin)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                reverse("order_update_status", args=[order.pk]),
                {"status": "confirmed", "next": "/adminpanel/"},
            )
        self.assertEqual(resp.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")
        self.assertGreaterEqual(len(mail.outbox), 1)
