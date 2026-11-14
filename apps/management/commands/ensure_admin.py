from django.core.management.base import BaseCommand
from apps.views import ensure_site_admin

class Command(BaseCommand):
    help = "Mirsamad / 123456 admin hisobini yaratadi yoki yangilaydi"

    def handle(self, *args, **options):
        ensure_site_admin()
        self.stdout.write(self.style.SUCCESS("Admin tayyor: Mirsamad / 123456"))
