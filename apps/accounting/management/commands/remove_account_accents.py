import unicodedata
from django.core.management.base import BaseCommand
from apps.accounting.models import Account


def remove_accents(text):
    if not text:
        return text
    decomposed = unicodedata.normalize('NFD', text)
    return unicodedata.normalize('NFC', ''.join(
        ch for ch in decomposed if unicodedata.category(ch) != 'Mn'
    ))


class Command(BaseCommand):
    help = "Elimina las tildes de los nombres de todas las cuentas contables."

    def handle(self, *args, **options):
        changed = 0
        for account in Account.objects.all().iterator():
            cleaned = remove_accents(account.name)
            if cleaned != account.name:
                self.stdout.write(f"  {account.code}: {account.name!r} -> {cleaned!r}")
                account.name = cleaned
                account.save(update_fields=['name'])
                changed += 1
        self.stdout.write(self.style.SUCCESS(f"Se actualizaron {changed} cuentas."))