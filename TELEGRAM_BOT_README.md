# Oziq Ovqat — Telegram Bot

## Imkoniyatlar

- 🛒 **Katalog** — kategoriyalar va mahsulotlar
- 🔍 **Qidiruv** — nom bo‘yicha
- 🧺 **Savat** — qo‘shish / o‘chirish / miqdor
- 📝 **Buyurtma** — Telegram orqali to‘liq buyurtma (DB ga yoziladi)
- 📦 **Buyurtmalarim** — telefon bo‘yicha holat
- 🛠 **Admin panel** — pending buyurtmalar, status o‘zgartirish, statistika
- Saytdan kelgan buyurtmalar ham admin Telegram ga keladi

## Token

`.env` da:

```
TELEGRAM_BOT_TOKEN=8657251455:AAHbY-zi1gZVVYoWpC31cCFBJXVLCUXH6to
TELEGRAM_CHAT_ID=7500183115
TELEGRAM_ADMIN_CHAT_IDS=7500183115
```

Admin chat ID ni o‘zgartirish: `@userinfobot` ga yozing, o‘z ID ni oling va `TELEGRAM_ADMIN_CHAT_IDS` ga yozing.

## Lokal ishga tushirish

```bash
cd "Oziq Ovqat CRM Website"
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo   # ixtiyoriy demo mahsulotlar
python telegram_bot.py
```

## PythonAnywhere

1. **Web app** (Django) ni odatiy tartibda sozlang:
   - Source code: `/home/USERNAME/oziq/`
   - WSGI: `config.wsgi`
   - Virtualenv + `pip install -r requirements.txt`
   - `ALLOWED_HOSTS` ga `USERNAME.pythonanywhere.com` qo‘shing
   - Static: `python manage.py collectstatic` (agar static papka bo‘lsa)

2. **Telegram bot (Always-on task)** — Pulling uchun:
   - Tasks → Always-on task
   - Command:
     ```
     /home/USERNAME/.virtualenvs/venv/bin/python /home/USERNAME/oziq/telegram_bot.py
     ```
   - Yoki Consoles → Bash da `python telegram_bot.py` (sessiya yopilsa to‘xtaydi)

3. SQLite `db.sqlite3` bir xil papkada bo‘lishi kerak (sayt va bot bir DB dan o‘qiydi).

## Eslatma

- Bot polling rejimida ishlaydi (webhook shart emas).
- Admin tugmalari faqat `TELEGRAM_ADMIN_CHAT_IDS` dagi chat larga ko‘rinadi.
- Sayt buyurtmasi yaratilganda avtomatik Telegram xabar yuboriladi.
