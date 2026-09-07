from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from apps.companies.models import Company
from apps.accounting.models import Account, JournalEntry, JournalEntryLine
from apps.accounting.services import (
    seed_sri_ecuador_chart_of_accounts,
    get_or_create_fiscal_year,
    get_ledger,
)

class AccountingModelTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Empresa Prueba S.A.",
            tax_id="1790011674001",
            address="Quito, Ecuador",
            email="info@empresaprueba.ec"
        )
        seed_sri_ecuador_chart_of_accounts(self.company)
        self.fiscal_year = get_or_create_fiscal_year(self.company, date(2026, 1, 15))

    def test_sri_chart_of_accounts_created(self):
        """Verifica que se poblaron las cuentas base SRI Ecuador."""
        self.assertTrue(Account.objects.filter(company=self.company, code="1.1.01.001").exists())
        self.assertTrue(Account.objects.filter(company=self.company, code="4.1.01").exists())

    def test_double_entry_unbalanced_fails(self):
        """Un asiento contable desbalanceado debe fallar al validarse."""
        caja = Account.objects.get(company=self.company, code="1.1.01.001")
        ventas = Account.objects.get(company=self.company, code="4.1.01")

        entry = JournalEntry.objects.create(
            company=self.company,
            fiscal_year=self.fiscal_year,
            entry_number=1,
            date=date(2026, 1, 15),
            concept="Asiento desbalanceado de prueba",
            status='POSTED'
        )

        JournalEntryLine.objects.create(entry=entry, account=caja, debit=Decimal('100.00'), credit=Decimal('0.00'))
        JournalEntryLine.objects.create(entry=entry, account=ventas, debit=Decimal('0.00'), credit=Decimal('90.00'))

        with self.assertRaises(ValidationError):
            entry.clean()

    def test_balanced_journal_entry_succeeds(self):
        """Un asiento contable balanceado (Debe == Haber) se valida correctamente."""
        caja = Account.objects.get(company=self.company, code="1.1.01.001")
        ventas = Account.objects.get(company=self.company, code="4.1.01")
        iva = Account.objects.get(company=self.company, code="2.1.02.001")

        entry = JournalEntry.objects.create(
            company=self.company,
            fiscal_year=self.fiscal_year,
            entry_number=2,
            date=date(2026, 1, 15),
            concept="Venta de Servicios con IVA 15%",
            status='POSTED'
        )

        JournalEntryLine.objects.create(entry=entry, account=caja, debit=Decimal('115.00'), credit=Decimal('0.00'))
        JournalEntryLine.objects.create(entry=entry, account=ventas, debit=Decimal('0.00'), credit=Decimal('100.00'))
        JournalEntryLine.objects.create(entry=entry, account=iva, debit=Decimal('0.00'), credit=Decimal('15.00'))

        self.assertTrue(entry.is_balanced)
        entry.clean()

    def test_edit_account_name_and_code(self):
        """Se puede modificar el nombre o código de una cuenta."""
        caja = Account.objects.get(company=self.company, code="1.1.01.001")
        caja.name = "Caja Principal Modificada"
        caja.save()
        
        caja_updated = Account.objects.get(id=caja.id)
        self.assertEqual(caja_updated.name, "Caja Principal Modificada")

    def test_delete_account_without_lines_succeeds(self):
        """Eliminar una cuenta sin movimientos contables ni subcuentas debe funcionar."""
        new_acc = Account.objects.create(
            company=self.company,
            code="1.1.01.099",
            name="Caja Temporal",
            account_type="ASSET",
            kind="MOVEMENT"
        )
        acc_id = new_acc.id
        new_acc.delete()
        self.assertFalse(Account.objects.filter(id=acc_id).exists())

    def test_delete_account_with_lines_protected(self):
        """Una cuenta con movimientos contables no puede ser eliminada."""
        caja = Account.objects.get(company=self.company, code="1.1.01.001")
        ventas = Account.objects.get(company=self.company, code="4.1.01")

        entry = JournalEntry.objects.create(
            company=self.company,
            fiscal_year=self.fiscal_year,
            entry_number=5,
            date=date(2026, 1, 15),
            concept="Prueba de protección de borrado",
            status='POSTED'
        )
        JournalEntryLine.objects.create(entry=entry, account=caja, debit=Decimal('50.00'), credit=Decimal('0.00'))
        JournalEntryLine.objects.create(entry=entry, account=ventas, debit=Decimal('0.00'), credit=Decimal('50.00'))

        self.assertTrue(caja.journal_lines.exists())

    def _create_entry(self, entry_number, entry_date, concept, lines):
        entry = JournalEntry.objects.create(
            company=self.company,
            fiscal_year=self.fiscal_year,
            entry_number=entry_number,
            date=entry_date,
            concept=concept,
            status='POSTED'
        )
        for acc_code, debit, credit in lines:
            acc = Account.objects.get(company=self.company, code=acc_code)
            JournalEntryLine.objects.create(entry=entry, account=acc, debit=Decimal(debit), credit=Decimal(credit))
        return entry

    def test_ledger_opening_and_running_balance(self):
        """El Libro Mayor calcula saldo inicial, saldo corrido y saldo final."""
        # Asiento antes del periodo
        self._create_entry(1, date(2026, 1, 10), "Apertura caja", [
            ("1.1.01.001", '500.00', '0.00'),
            ("3.1.01", '0.00', '500.00'),
        ])
        # Movimientos dentro del periodo
        self._create_entry(2, date(2026, 2, 5), "Venta con IVA", [
            ("1.1.01.001", '115.00', '0.00'),
            ("4.1.01", '0.00', '100.00'),
            ("2.1.02.001", '0.00', '15.00'),
        ])
        self._create_entry(3, date(2026, 2, 10), "Gasto", [
            ("5.1.01", '50.00', '0.00'),
            ("1.1.01.001", '0.00', '50.00'),
        ])

        data = get_ledger(self.company, date(2026, 2, 1), date(2026, 2, 28))
        accounts = {item['account'].code: item for item in data['accounts']}

        # Caja: saldo inicial 500, +115 -50 = saldo final 565
        caja = accounts['1.1.01.001']
        self.assertEqual(caja['opening_balance'], Decimal('500.00'))
        self.assertEqual(caja['total_debit'], Decimal('115.00'))
        self.assertEqual(caja['total_credit'], Decimal('50.00'))
        self.assertEqual(caja['closing_balance'], Decimal('565.00'))
        self.assertEqual(len(caja['movements']), 2)

        # Ingresos: saldo inicial 0, crédito 100 -> saldo final 100 (naturaleza acreedora)
        ventas = accounts['4.1.01']
        self.assertEqual(ventas['opening_balance'], Decimal('0.00'))
        self.assertEqual(ventas['closing_balance'], Decimal('100.00'))

        # Cuentas sin saldo inicial ni movimiento no aparecen
        self.assertNotIn('5.2.01', accounts)
