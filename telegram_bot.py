#!/usr/bin/env python3
"""
Oziq Ovqat CRM — professional Telegram Bot
Sayt bilan bir xil SQLite DB dan o‘qiydi.
Website ga product qo‘shsangiz — botda ham darhol ko‘rinadi.

Ishga tushirish:
  python telegram_bot.py
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.models import Category, Order, OrderItem, Product

try:
    import telebot
    from telebot import types
    from telebot.apihelper import ApiTelegramException
except ImportError:
    print("pyTelegramBotAPI o'rnatilmagan: pip install pyTelegramBotAPI")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

# ─── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = (
    os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    or "8657251455:AAHbY-zi1gZVVYoWpC31cCFBJXVLCUXH6to"
)
ADMIN_CHAT_IDS: set[int] = set()
_raw = os.environ.get("TELEGRAM_ADMIN_CHAT_IDS", "") or os.environ.get(
    "TELEGRAM_CHAT_ID", "7500183115"
)
for part in str(_raw).replace(";", ",").split(","):
    part = part.strip()
    if part.lstrip("-").isdigit():
        ADMIN_CHAT_IDS.add(int(part))

if not BOT_TOKEN:
    print("TELEGRAM_BOT_TOKEN topilmadi!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("oziq_bot")

# chat_id -> state
USER_STATE: dict[int, dict] = {}
PAGE_SIZE = 8


def get_state(chat_id: int) -> dict:
    if chat_id not in USER_STATE:
        USER_STATE[chat_id] = {
            "cart": {},  # product_id -> qty
            "mode": None,
            "order_data": {},
            "cat_slug": "all",
            "page": 0,
        }
    return USER_STATE[chat_id]


def is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_CHAT_IDS


def money(n: int | float) -> str:
    try:
        return f"{int(n):,}".replace(",", " ") + " so'm"
    except (TypeError, ValueError):
        return "0 so'm"


def safe_answer(call, text: str = "", show_alert: bool = False):
    try:
        bot.answer_callback_query(call.id, text=text, show_alert=show_alert)
    except Exception:
        pass


def safe_edit(chat_id: int, message_id: int, text: str, reply_markup=None):
    try:
        bot.edit_message_text(
            text, chat_id, message_id, reply_markup=reply_markup, parse_mode="HTML"
        )
        return True
    except ApiTelegramException as e:
        if "message is not modified" in str(e).lower():
            return True
        log.warning("edit_message failed: %s", e)
    except Exception as e:
        log.warning("edit_message failed: %s", e)
    return False


def safe_send(chat_id: int, text: str, reply_markup=None, retries: int = 2):
    last_err = None
    for i in range(retries + 1):
        try:
            return bot.send_message(
                chat_id, text, reply_markup=reply_markup, parse_mode="HTML"
            )
        except Exception as e:
            last_err = e
            time.sleep(0.8 * (i + 1))
    log.error("safe_send failed: %s", last_err)
    return None


# ─── Keyboards ───────────────────────────────────────────────────────────────
def main_keyboard(chat_id: int) -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("🛒 Katalog"),
        types.KeyboardButton("🔍 Qidiruv"),
    )
    kb.add(
        types.KeyboardButton("🧺 Savatim"),
        types.KeyboardButton("📦 Buyurtmalarim"),
    )
    kb.add(
        types.KeyboardButton("📝 Buyurtma berish"),
        types.KeyboardButton("ℹ️ Biz haqimizda"),
    )
    if is_admin(chat_id):
        kb.add(types.KeyboardButton("🛠 Admin panel"))
    return kb


def categories_inline() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    cats = (
        Category.objects.annotate(
            cnt=Count("products", filter=Q(products__is_active=True))
        )
        .filter(cnt__gt=0)
        .order_by("name")
    )
    buttons = []
    for c in cats:
        icon = (c.icon or "📦").strip() or "📦"
        buttons.append(
            types.InlineKeyboardButton(
                f"{icon} {c.name} ({c.cnt})",
                callback_data=f"cat:{c.slug}",
            )
        )
    if buttons:
        kb.add(*buttons)
    kb.add(
        types.InlineKeyboardButton("📋 Barcha mahsulotlar", callback_data="cat:all")
    )
    return kb


def products_keyboard(
    products: list,
    page: int = 0,
    page_size: int = PAGE_SIZE,
    cat_slug: str = "all",
) -> types.InlineKeyboardMarkup:
    """products — doim list (QuerySet emas)."""
    items = list(products)
    total = len(items)
    start = max(0, page * page_size)
    chunk = items[start : start + page_size]

    kb = types.InlineKeyboardMarkup(row_width=1)
    for p in chunk:
        sale = f" (-{p.sale}%)" if getattr(p, "sale", 0) else ""
        kb.add(
            types.InlineKeyboardButton(
                f"{p.name} — {money(p.final_price)}{sale}",
                callback_data=f"p:{p.pk}",
            )
        )

    nav = []
    if page > 0:
        nav.append(
            types.InlineKeyboardButton(
                "⬅️ Oldingi", callback_data=f"page:{cat_slug}:{page - 1}"
            )
        )
    if start + page_size < total:
        nav.append(
            types.InlineKeyboardButton(
                "Keyingi ➡️", callback_data=f"page:{cat_slug}:{page + 1}"
            )
        )
    if nav:
        kb.row(*nav)

    pages = max(1, (total + page_size - 1) // page_size)
    if total > page_size:
        kb.add(
            types.InlineKeyboardButton(
                f"📄 {page + 1}/{pages} · jami {total}",
                callback_data="noop",
            )
        )
    kb.add(types.InlineKeyboardButton("🔙 Kategoriyalar", callback_data="back_cats"))
    return kb


def product_detail_kb(product_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Savatga", callback_data=f"add:{product_id}"),
        types.InlineKeyboardButton(
            "🛒 1 dona buyurtma", callback_data=f"buy1:{product_id}"
        ),
    )
    kb.add(types.InlineKeyboardButton("🔙 Katalog", callback_data="back_cats"))
    return kb


def load_products(cat_slug: str = "all", limit: int = 100) -> list:
    qs = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .order_by("-created_at")
    )
    if cat_slug and cat_slug != "all":
        qs = qs.filter(category__slug=cat_slug)
    return list(qs[:limit])


def cat_title(slug: str) -> str:
    if slug == "all":
        return "Barcha mahsulotlar"
    c = Category.objects.filter(slug=slug).first()
    if c:
        return f"{(c.icon or '').strip()} {c.name}".strip()
    return slug


# ─── /start ──────────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    chat_id = message.chat.id
    get_state(chat_id)
    name = message.from_user.first_name or "Do'st"
    text = (
        f"Assalomu alaykum, <b>{name}</b>! 👋\n\n"
        f"🍎 <b>Oziq Ovqat</b> — yangi va sifatli mahsulotlar\n"
        f"Katalogni ko‘ring, savatga qo‘shing va buyurtma bering.\n\n"
        f"Bot: @UstozshogirttBot\n"
        f"Quyidagi tugmalardan foydalaning 👇"
    )
    safe_send(chat_id, text, reply_markup=main_keyboard(chat_id))


@bot.message_handler(commands=["menu", "katalog"])
def cmd_menu(message):
    safe_send(
        message.chat.id,
        "📂 <b>Kategoriyalar</b>\nTanlang:",
        reply_markup=categories_inline(),
    )


# ─── Reply buttons ───────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🛒 Katalog")
def btn_katalog(message):
    safe_send(
        message.chat.id,
        "📂 <b>Kategoriyalar</b>\nTanlang:",
        reply_markup=categories_inline(),
    )


@bot.message_handler(func=lambda m: m.text == "🔍 Qidiruv")
def btn_search(message):
    st = get_state(message.chat.id)
    st["mode"] = "search"
    safe_send(
        message.chat.id,
        "🔍 Qidirmoqchi bo‘lgan mahsulot nomini yozing:\n"
        "Masalan: <i>sut, non, olma</i>",
    )


@bot.message_handler(func=lambda m: m.text == "🧺 Savatim")
def btn_cart(message):
    show_cart(message.chat.id)


@bot.message_handler(func=lambda m: m.text == "📦 Buyurtmalarim")
def btn_my_orders(message):
    st = get_state(message.chat.id)
    st["mode"] = "my_orders_phone"
    safe_send(
        message.chat.id,
        "📦 Buyurtmalaringizni ko‘rish uchun <b>telefon raqamingizni</b> yuboring:\n"
        "Masalan: <code>+998901234567</code>",
    )


@bot.message_handler(func=lambda m: m.text == "📝 Buyurtma berish")
def btn_order(message):
    st = get_state(message.chat.id)
    if not st["cart"]:
        safe_send(
            message.chat.id,
            "Savat bo‘sh. Avval katalogdan mahsulot qo‘shing 🛒",
            reply_markup=categories_inline(),
        )
        return
    start_checkout(message.chat.id)


@bot.message_handler(func=lambda m: m.text == "ℹ️ Biz haqimizda")
def btn_about(message):
    text = (
        "🍎 <b>Oziq Ovqat</b>\n\n"
        "Yangi, sifatli oziq-ovqat mahsulotlari.\n"
        "Yetkazib berish — Toshkent bo‘ylab.\n\n"
        "• Katalog va buyurtma — shu bot orqali\n"
        "• Savol/taklif — shu yerga yozing, adminlarga yetadi\n\n"
        "Bot: @UstozshogirttBot"
    )
    safe_send(message.chat.id, text, reply_markup=main_keyboard(message.chat.id))


@bot.message_handler(func=lambda m: m.text == "🛠 Admin panel")
def btn_admin(message):
    if not is_admin(message.chat.id):
        safe_send(message.chat.id, "⛔ Ruxsat yo‘q.")
        return
    pending = Order.objects.filter(status="pending").count()
    today = Order.objects.filter(created_at__date=timezone.localdate()).count()
    total_sum = (
        Order.objects.filter(status__in=["confirmed", "delivering", "done"]).aggregate(
            s=Sum("total")
        )["s"]
        or 0
    )
    products_cnt = Product.objects.filter(is_active=True).count()
    text = (
        f"🛠 <b>Admin panel</b>\n\n"
        f"⏳ Kutilayotgan: <b>{pending}</b>\n"
        f"📅 Bugun: <b>{today}</b>\n"
        f"✅ Savdo (tasdiqlangan): <b>{money(total_sum)}</b>\n"
        f"📦 Faol mahsulotlar: <b>{products_cnt}</b>\n"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("⏳ Pending", callback_data="admin:pending")
    )
    kb.add(
        types.InlineKeyboardButton("📋 Oxirgi 10", callback_data="admin:last10")
    )
    kb.add(
        types.InlineKeyboardButton("📊 Statistika", callback_data="admin:stats")
    )
    safe_send(message.chat.id, text, reply_markup=kb)


# ─── Callbacks ───────────────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    data = call.data or ""
    st = get_state(chat_id)
    mid = call.message.message_id

    try:
        if data == "noop":
            safe_answer(call)
            return

        if data == "back_cats":
            safe_edit(
                chat_id,
                mid,
                "📂 <b>Kategoriyalar</b>\nTanlang:",
                reply_markup=categories_inline(),
            )
            safe_answer(call)
            return

        # Katalog / kategoriya
        if data.startswith("cat:"):
            slug = data.split(":", 1)[1]
            products = load_products(slug)
            if not products:
                safe_answer(call, "Mahsulot topilmadi", show_alert=True)
                return
            st["cat_slug"] = slug
            st["page"] = 0
            title = cat_title(slug)
            safe_edit(
                chat_id,
                mid,
                f"🛍 <b>{title}</b>\nTanlang:",
                reply_markup=products_keyboard(products, page=0, cat_slug=slug),
            )
            safe_answer(call)
            return

        # Sahifa
        if data.startswith("page:"):
            # page:slug:N
            parts = data.split(":")
            if len(parts) >= 3:
                slug = parts[1]
                page = int(parts[2])
            else:
                safe_answer(call)
                return
            products = load_products(slug)
            st["cat_slug"] = slug
            st["page"] = page
            title = cat_title(slug)
            safe_edit(
                chat_id,
                mid,
                f"🛍 <b>{title}</b>\nTanlang:",
                reply_markup=products_keyboard(products, page=page, cat_slug=slug),
            )
            safe_answer(call)
            return

        # Mahsulot kartochkasi
        if data.startswith("p:"):
            pid = int(data.split(":")[1])
            p = Product.objects.filter(pk=pid, is_active=True).first()
            if not p:
                safe_answer(call, "Topilmadi", show_alert=True)
                return
            about = (p.about or "")[:400]
            text = (
                f"<b>{p.name}</b>\n\n"
                f"💰 Narx: <b>{money(p.final_price)}</b>"
            )
            if p.sale:
                text += f"  <s>{money(p.price)}</s> (-{p.sale}%)"
            text += (
                f"\n⭐ Reyting: {p.rating}/5"
                f"\n📦 Birlik: {p.unit or 'dona'}\n\n"
                f"{about}"
            )
            cover = p.get_cover()
            try:
                bot.send_photo(
                    chat_id,
                    cover,
                    caption=text,
                    reply_markup=product_detail_kb(p.pk),
                    parse_mode="HTML",
                )
            except Exception:
                safe_send(chat_id, text, reply_markup=product_detail_kb(p.pk))
            safe_answer(call)
            return

        if data.startswith("add:"):
            pid = int(data.split(":")[1])
            if not Product.objects.filter(pk=pid, is_active=True).exists():
                safe_answer(call, "Mahsulot yo‘q", show_alert=True)
                return
            st["cart"][pid] = st["cart"].get(pid, 0) + 1
            safe_answer(call, f"✅ Savatga (+{st['cart'][pid]})")
            return

        if data.startswith("buy1:"):
            pid = int(data.split(":")[1])
            if not Product.objects.filter(pk=pid, is_active=True).exists():
                safe_answer(call, "Mahsulot yo‘q", show_alert=True)
                return
            st["cart"] = {pid: 1}
            safe_answer(call)
            start_checkout(chat_id)
            return

        if data.startswith("cplus:"):
            pid = int(data.split(":")[1])
            st["cart"][pid] = st["cart"].get(pid, 0) + 1
            show_cart(chat_id, edit_msg=call.message)
            safe_answer(call)
            return

        if data.startswith("cminus:"):
            pid = int(data.split(":")[1])
            if pid in st["cart"]:
                st["cart"][pid] -= 1
                if st["cart"][pid] <= 0:
                    del st["cart"][pid]
            show_cart(chat_id, edit_msg=call.message)
            safe_answer(call)
            return

        if data.startswith("cdel:"):
            pid = int(data.split(":")[1])
            st["cart"].pop(pid, None)
            show_cart(chat_id, edit_msg=call.message)
            safe_answer(call, "O‘chirildi")
            return

        if data == "clear_cart":
            st["cart"] = {}
            safe_edit(chat_id, mid, "🗑 Savat tozalandi.")
            safe_answer(call)
            return

        if data == "checkout":
            safe_answer(call)
            start_checkout(chat_id)
            return

        # Admin
        if data.startswith("admin:"):
            if not is_admin(chat_id):
                safe_answer(call, "Ruxsat yo‘q", show_alert=True)
                return
            action = data.split(":", 1)[1]
            if action == "pending":
                orders = list(
                    Order.objects.filter(status="pending").order_by("-created_at")[:15]
                )
                if not orders:
                    safe_answer(call, "Pending yo‘q", show_alert=True)
                    return
                lines = ["⏳ <b>Kutilayotgan buyurtmalar</b>\n"]
                kb = types.InlineKeyboardMarkup()
                for o in orders:
                    lines.append(
                        f"#{o.pk} — {o.full_name} — {money(o.total)}\n📞 {o.phone}"
                    )
                    kb.row(
                        types.InlineKeyboardButton(
                            f"✅ #{o.pk}",
                            callback_data=f"ostatus:{o.pk}:confirmed",
                        ),
                        types.InlineKeyboardButton(
                            f"❌ #{o.pk}",
                            callback_data=f"ostatus:{o.pk}:cancelled",
                        ),
                    )
                safe_send(chat_id, "\n".join(lines), reply_markup=kb)
            elif action == "last10":
                orders = Order.objects.order_by("-created_at")[:10]
                lines = ["📋 <b>Oxirgi 10 buyurtma</b>\n"]
                for o in orders:
                    lines.append(
                        f"#{o.pk} [{o.status}] {o.full_name} — {money(o.total)}"
                    )
                safe_send(chat_id, "\n".join(lines) if lines else "Bo‘sh")
            elif action == "stats":
                rows = (
                    Order.objects.values("status")
                    .annotate(c=Count("id"), s=Sum("total"))
                    .order_by("status")
                )
                lines = ["📊 <b>Statistika</b>\n"]
                for row in rows:
                    lines.append(
                        f"• {row['status']}: {row['c']} ta — {money(row['s'] or 0)}"
                    )
                safe_send(chat_id, "\n".join(lines))
            safe_answer(call)
            return

        if data.startswith("ostatus:"):
            if not is_admin(chat_id):
                safe_answer(call, "Ruxsat yo‘q", show_alert=True)
                return
            parts = data.split(":")
            oid, status = int(parts[1]), parts[2]
            o = Order.objects.filter(pk=oid).first()
            if o:
                o.status = status
                o.save(update_fields=["status", "updated_at"])
                safe_answer(call, f"#{oid} → {status}")
                safe_send(
                    chat_id,
                    f"✅ Buyurtma <b>#{oid}</b> holati: <b>{status}</b>",
                )
            else:
                safe_answer(call, "Topilmadi", show_alert=True)
            return

        safe_answer(call)
    except Exception:
        log.exception("callback error data=%s", data)
        safe_answer(call, "Xatolik yuz berdi", show_alert=True)


# ─── Cart ────────────────────────────────────────────────────────────────────
def show_cart(chat_id: int, edit_msg=None):
    st = get_state(chat_id)
    if not st["cart"]:
        text = "🧺 Savat bo‘sh.\nKatalogdan mahsulot qo‘shing."
        if edit_msg:
            safe_edit(chat_id, edit_msg.message_id, text)
        else:
            safe_send(chat_id, text, reply_markup=categories_inline())
        return

    lines = ["🧺 <b>Savat</b>\n"]
    total = 0
    valid = {}
    for pid, qty in list(st["cart"].items()):
        p = Product.objects.filter(pk=pid, is_active=True).first()
        if not p:
            continue
        valid[pid] = qty
        sub = p.final_price * qty
        total += sub
        lines.append(f"• {p.name} × {qty} = {money(sub)}")
    st["cart"] = valid

    if not valid:
        text = "🧺 Savat bo‘sh (mahsulotlar o‘chirilgan)."
        if edit_msg:
            safe_edit(chat_id, edit_msg.message_id, text)
        else:
            safe_send(chat_id, text)
        return

    lines.append(f"\n<b>Jami: {money(total)}</b>")
    text = "\n".join(lines)

    kb = types.InlineKeyboardMarkup(row_width=3)
    for pid, qty in valid.items():
        p = Product.objects.filter(pk=pid).first()
        label = (p.name[:14] + "…") if p and len(p.name) > 14 else (p.name if p else str(pid))
        kb.row(
            types.InlineKeyboardButton("➖", callback_data=f"cminus:{pid}"),
            types.InlineKeyboardButton(f"{label} ×{qty}", callback_data=f"p:{pid}"),
            types.InlineKeyboardButton("➕", callback_data=f"cplus:{pid}"),
        )
        kb.row(
            types.InlineKeyboardButton(f"❌ {label}", callback_data=f"cdel:{pid}")
        )
    kb.add(types.InlineKeyboardButton("✅ Buyurtma berish", callback_data="checkout"))
    kb.add(types.InlineKeyboardButton("🗑 Tozalash", callback_data="clear_cart"))

    if edit_msg:
        if not safe_edit(chat_id, edit_msg.message_id, text, reply_markup=kb):
            safe_send(chat_id, text, reply_markup=kb)
    else:
        safe_send(chat_id, text, reply_markup=kb)


def start_checkout(chat_id: int):
    st = get_state(chat_id)
    st["mode"] = "order_name"
    st["order_data"] = {}
    safe_send(chat_id, "📝 <b>Buyurtma</b>\n\n1/4 — To‘liq ismingizni yozing:")


def finish_order(chat_id: int):
    st = get_state(chat_id)
    data = st.get("order_data") or {}
    cart = dict(st.get("cart") or {})
    if not cart:
        safe_send(chat_id, "Savat bo‘sh.")
        return

    full_name = (data.get("name") or "").strip()[:150]
    phone = (data.get("phone") or "").strip()[:30]
    address = (data.get("address") or "").strip()[:500]
    note = (data.get("note") or "").strip()[:500]

    items = []
    total = 0
    for pid, qty in cart.items():
        p = Product.objects.filter(pk=pid, is_active=True).first()
        if not p:
            continue
        items.append((p, qty, p.final_price))
        total += p.final_price * qty

    if not items:
        safe_send(chat_id, "Mahsulotlar topilmadi yoki faol emas.")
        return

    order = Order.objects.create(
        session_key=f"tg_{chat_id}",
        full_name=full_name,
        phone=phone,
        address=address,
        note=note or f"Telegram (chat_id={chat_id})",
        total=total,
        status="pending",
    )
    for p, qty, price in items:
        OrderItem.objects.create(
            order=order,
            product=p,
            product_name=p.name,
            price=price,
            quantity=qty,
        )

    st["cart"] = {}
    st["mode"] = None
    st["order_data"] = {}

    safe_send(
        chat_id,
        f"✅ <b>Buyurtma qabul qilindi!</b>\n"
        f"🔢 Raqam: <b>#{order.pk}</b>\n"
        f"👤 {full_name}\n"
        f"📞 {phone}\n"
        f"📍 {address}\n"
        f"💰 Jami: <b>{money(total)}</b>\n\n"
        f"Tez orada bog‘lanamiz.",
        reply_markup=main_keyboard(chat_id),
    )

    admin_text = (
        f"🛒 <b>Yangi buyurtma #{order.pk}</b> (Telegram)\n\n"
        f"👤 {full_name}\n📞 {phone}\n📍 {address}\n"
        f"💰 {money(total)}\n📝 {note or '—'}\n\nMahsulotlar:\n"
    )
    for p, qty, price in items:
        admin_text += f"• {p.name} ×{qty} = {money(price * qty)}\n"

    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton(
            "✅ Tasdiqlash", callback_data=f"ostatus:{order.pk}:confirmed"
        ),
        types.InlineKeyboardButton(
            "🚚 Yetkazish", callback_data=f"ostatus:{order.pk}:delivering"
        ),
    )
    kb.row(
        types.InlineKeyboardButton(
            "✔️ Yakunlash", callback_data=f"ostatus:{order.pk}:done"
        ),
        types.InlineKeyboardButton(
            "❌ Bekor", callback_data=f"ostatus:{order.pk}:cancelled"
        ),
    )
    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(aid, admin_text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            log.warning("Admin notify %s: %s", aid, e)


# ─── Text handler ────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    st = get_state(chat_id)
    mode = st.get("mode")

    if mode == "search":
        st["mode"] = None
        if len(text) < 2:
            safe_send(chat_id, "Kamida 2 ta harf yozing.")
            return
        products = list(
            Product.objects.filter(is_active=True)
            .filter(Q(name__icontains=text) | Q(about__icontains=text))
            .order_by("-created_at")[:30]
        )
        if not products:
            safe_send(chat_id, f"«{text}» bo‘yicha hech narsa topilmadi.")
            return
        st["cat_slug"] = "all"
        safe_send(
            chat_id,
            f"🔍 Natijalar: <b>{len(products)}</b> ta\nTanlang:",
            reply_markup=products_keyboard(products, page=0, cat_slug="all"),
        )
        return

    if mode == "my_orders_phone":
        st["mode"] = None
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) < 7:
            safe_send(chat_id, "To‘g‘ri telefon raqam yuboring.")
            return
        orders = list(
            Order.objects.filter(phone__icontains=digits[-9:]).order_by("-created_at")[
                :10
            ]
        )
        if not orders:
            safe_send(chat_id, "Bu raqam bo‘yicha buyurtma topilmadi.")
            return
        lines = [f"📦 <b>Buyurtmalar</b>\n"]
        for o in orders:
            lines.append(
                f"#{o.pk} — <b>{o.get_status_display()}</b> — {money(o.total)}\n"
                f"📅 {timezone.localtime(o.created_at).strftime('%d.%m.%Y %H:%M')}"
            )
        safe_send(chat_id, "\n\n".join(lines))
        return

    if mode == "order_name":
        st["order_data"]["name"] = text[:150]
        st["mode"] = "order_phone"
        safe_send(
            chat_id,
            "2/4 — Telefon raqamingiz:\nMasalan: <code>+99890xxxxxxx</code>",
        )
        return

    if mode == "order_phone":
        st["order_data"]["phone"] = text[:30]
        st["mode"] = "order_address"
        safe_send(chat_id, "3/4 — Yetkazib berish manzili:")
        return

    if mode == "order_address":
        st["order_data"]["address"] = text[:500]
        st["mode"] = "order_note"
        safe_send(
            chat_id,
            "4/4 — Izoh (ixtiyoriy). Yo‘q bo‘lsa <b>-</b> yozing:",
        )
        return

    if mode == "order_note":
        low = text.lower()
        st["order_data"]["note"] = (
            "" if low in ("-", "—", "yoq", "yo‘q", "yo'q", "no") else text[:500]
        )
        st["mode"] = None
        finish_order(chat_id)
        return

    # Oddiy xabar — adminga
    if not is_admin(chat_id) and text and not text.startswith("/"):
        uname = message.from_user.username or ""
        fwd = (
            f"💬 <b>Bot xabar</b>\n"
            f"From: {message.from_user.first_name} (@{uname})\n"
            f"ID: <code>{chat_id}</code>\n\n{text}"
        )
        for aid in ADMIN_CHAT_IDS:
            try:
                bot.send_message(aid, fwd, parse_mode="HTML")
            except Exception:
                pass
        safe_send(
            chat_id,
            "Xabaringiz qabul qilindi ✅\nKatalog: /start",
            reply_markup=main_keyboard(chat_id),
        )


if __name__ == "__main__":
    log.info("Oziq Ovqat bot ishga tushmoqda...")
    log.info("Admin chat IDs: %s", ADMIN_CHAT_IDS)
    try:
        bot.remove_webhook()
    except Exception:
        pass
    # Tarmoq uzilsa qayta urinish
    while True:
        try:
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=40,
                skip_pending=True,
                allowed_updates=["message", "callback_query"],
            )
        except Exception as e:
            log.error("Polling xato, 5 soniyadan keyin qayta: %s", e)
            time.sleep(5)
