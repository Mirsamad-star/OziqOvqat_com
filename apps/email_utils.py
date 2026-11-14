"""
Oziq Ovqat — professional email helpers.
SMTP xatolari asosiy tranzaksiyani buzmaydi; logga yoziladi.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _site_url() -> str:
    return getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")


def _from_email() -> str:
    return getattr(settings, "DEFAULT_FROM_EMAIL", "Oziq Ovqat <noreply@oziqovqat.uz>")


def send_templated_email(
    subject: str,
    template_name: str,
    context: dict[str, Any],
    to: list[str] | str,
    *,
    fail_silently: bool = True,
) -> bool:
    """
    HTML + plain-text email yuboradi.
    template_name: 'emails/welcome' → emails/welcome.html va .txt
    """
    if isinstance(to, str):
        to = [to]
    to = [addr.strip() for addr in to if addr and addr.strip()]
    if not to:
        logger.warning("Email yuborilmadi: qabul qiluvchi yo‘q (subject=%s)", subject)
        return False

    ctx = {**context, "site_url": _site_url()}
    try:
        html_body = render_to_string(f"{template_name}.html", ctx)
        try:
            text_body = render_to_string(f"{template_name}.txt", ctx)
        except Exception:
            text_body = strip_tags(html_body)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=_from_email(),
            to=to,
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        logger.info("Email yuborildi: to=%s subject=%s", to, subject)
        return True
    except Exception:
        logger.exception("Email yuborish xatosi: to=%s subject=%s", to, subject)
        if not fail_silently:
            raise
        return False


def send_welcome_email(user) -> bool:
    email = getattr(user, "email", "") or ""
    if not email:
        return False
    name = user.get_full_name() or user.username
    return send_templated_email(
        subject=f"Xush kelibsiz, {name}! — Oziq Ovqat",
        template_name="emails/welcome",
        context={"user": user, "name": name},
        to=email,
    )


def send_order_confirmation(order, email: Optional[str] = None) -> bool:
    """Mijozga buyurtma tasdiqlash xati."""
    email = (email or "").strip()
    if not email and order.user_id and getattr(order.user, "email", None):
        email = order.user.email
    if not email:
        return False
    items = list(order.items.select_related("product").all())
    return send_templated_email(
        subject=f"Buyurtma #{order.pk} qabul qilindi — Oziq Ovqat",
        template_name="emails/order_confirmation",
        context={
            "order": order,
            "items": items,
            "name": order.full_name,
            "status_display": order.get_status_display(),
        },
        to=email,
    )


def send_order_status_email(order, old_status: Optional[str] = None) -> bool:
    """Buyurtma holati o‘zgarganda mijozga xabar."""
    email = ""
    if order.user_id and getattr(order.user, "email", None):
        email = order.user.email
    if not email:
        return False
    items = list(order.items.all())
    return send_templated_email(
        subject=f"Buyurtma #{order.pk} holati: {order.get_status_display()} — Oziq Ovqat",
        template_name="emails/order_status",
        context={
            "order": order,
            "items": items,
            "name": order.full_name,
            "old_status": old_status,
            "status_display": order.get_status_display(),
        },
        to=email,
    )


def send_admin_new_order(order) -> bool:
    """Yangi buyurtma haqida administratorga xabar."""
    admin_email = getattr(settings, "ADMIN_NOTIFY_EMAIL", "") or ""
    if not admin_email:
        admin_email = getattr(settings, "EMAIL_HOST_USER", "") or ""
    if not admin_email:
        logger.info("Admin email sozlanmagan — yangi buyurtma xabari o‘tkazib yuborildi.")
        return False
    items = list(order.items.all())
    return send_templated_email(
        subject=f"[Yangi buyurtma] #{order.pk} — {order.full_name}",
        template_name="emails/admin_new_order",
        context={
            "order": order,
            "items": items,
            "status_display": order.get_status_display(),
        },
        to=admin_email,
    )


def send_contact_emails(name: str, contact: str, message: str, *, is_email: bool) -> bool:
    """Aloqa formasi: mijoz email yozsa unga javob + adminga xabar."""
    ok = False
    admin = getattr(settings, "ADMIN_NOTIFY_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", "") or ""
    # Adminga
    if admin:
        ok = send_templated_email(
            subject=f"[Aloqa] {name}",
            template_name="emails/contact_admin",
            context={"name": name, "contact": contact, "message": message, "is_email": is_email},
            to=admin,
        ) or ok
    # Mijoz email kiritsa — tasdiqlash xati
    if is_email and contact:
        ok = send_templated_email(
            subject="Xabaringiz qabul qilindi — Oziq Ovqat",
            template_name="emails/contact_user",
            context={"name": name, "message": message},
            to=contact,
        ) or ok
    return ok
