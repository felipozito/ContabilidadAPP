from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from datetime import date as dt_date
from collections import OrderedDict

from apps.companies.models import Company
from apps.accounting.models import Account, FiscalYear, JournalEntry, JournalEntryLine


MONICA_TIPO = {
    'A': 'ASSET',
    'P': 'LIABILITY',
    'C': 'EQUITY',
    'I': 'INCOME',
    'G': 'EXPENSE',
    'S': 'EXPENSE',
}


class Command(BaseCommand):
    help = "Importa el plan de cuentas y asientos de Mónica 9 (exportados a CSV) hacia una nueva empresa."

    def add_arguments(self, parser):
        parser.add_argument('--accounts-csv', default='/tmp/mssql/cuentas.csv')
        parser.add_argument('--entries-csv', default='/tmp/mssql/asientos.csv')
        parser.add_argument('--ruc', default='1799999999001')
        parser.add_argument('--name', default='EDIFICIO YURAJ PIRCA 2026')

    def handle(self, *args, **options):
        accounts_csv = options['accounts_csv']
        entries_csv = options['entries_csv']
        ruc = options['ruc']
        name = options['name']

        accounts = self._read_pipe(accounts_csv)
        lines = self._read_pipe(entries_csv)
        if not accounts or not lines:
            raise CommandError("Los CSV están vacíos o no se leyeron correctamente.")

        company, _ = Company.objects.get_or_create(
            tax_id=ruc,
            defaults={
                'name': name,
                'address': 'Edificio Yuraj Pirca (dirección por confirmar)',
                'email': 'info@yurajpirca.ec',
                'phone': 'Pendiente',
                'is_active': True,
            },
        )

        if JournalEntry.objects.filter(company=company).exists():
            raise CommandError(
                f"La empresa '{company.name}' ya tiene asientos importados. "
                "Borra los asientos y cuentas antes de volver a importar."
            )

        with transaction.atomic():
            self.stdout.write(f"Empresa: {company.name} ({company.tax_id})")
            acc_by_monica = self._import_accounts(company, accounts)
            self._import_entries(company, lines, acc_by_monica)

        self._report(company)

    # ------------------------------------------------------------------
    # Lectura de archivos planos (separador '|', salida de sqlcmd -W)
    # ------------------------------------------------------------------
    def _read_pipe(self, path):
        rows = []
        try:
            with open(path, encoding='utf-8') as fh:
                for line in fh:
                    line = line.rstrip('\n')
                    if not line.strip():
                        continue
                    rows.append([c.strip() for c in line.split('|')])
        except FileNotFoundError:
            raise CommandError(f"No se encontró el archivo: {path}")
        return rows

    # ------------------------------------------------------------------
    # Plan de cuentas con jerarquía y códigos con puntos
    # ------------------------------------------------------------------
    def _import_accounts(self, company, rows):
        # rows: code|name|tipo|nivel|balance
        accs = []
        for r in rows:
            if len(r) < 4:
                continue
            accs.append({'code': r[0], 'name': r[1], 'tipo': r[2], 'nivel': r[3]})

        code_set = {a['code'] for a in accs}
        parent_map = {}
        for a in accs:
            best = None
            for l in range(len(a['code']) - 1, 0, -1):
                if a['code'][:l] in code_set:
                    best = a['code'][:l]
                    break
            parent_map[a['code']] = best

        def dotted(code):
            chain, cur = [], code
            while cur:
                chain.append(cur)
                cur = parent_map.get(cur)
            chain.reverse()
            segs, prev = [], None
            for c in chain:
                segs.append(c if prev is None else c[len(prev):])
                prev = c
            return '.'.join(segs)

        # Crear primero los padres (orden por longitud de código)
        acc_by_monica = {}
        for a in sorted(accs, key=lambda x: (len(x['code']), x['code'])):
            parent_code = parent_map[a['code']]
            parent = acc_by_monica.get(parent_code) if parent_code else None
            obj, created = Account.objects.update_or_create(
                company=company,
                code=dotted(a['code']),
                defaults={
                    'name': a['name'],
                    'account_type': MONICA_TIPO.get(a['tipo'], 'EXPENSE'),
                    'kind': 'CONTROL' if a['nivel'] == 'S' else 'MOVEMENT',
                    'parent': parent,
                    'is_active': True,
                },
            )
            acc_by_monica[a['code']] = obj
        self.stdout.write(f"Cuentas importadas: {len(accs)}")
        return acc_by_monica

    # ------------------------------------------------------------------
    # Asientos contables (agrupados por codigo_asiento)
    # ------------------------------------------------------------------
    def _import_entries(self, company, rows, acc_by_monica):
        # rows: codigo|fecha|consecutivo|cuenta|debe_haber|cantidad|explicacion|referencia|comprobante|estado
        fy, _ = FiscalYear.objects.get_or_create(
            company=company, year=2026,
            defaults={'start_date': dt_date(2026, 1, 1), 'end_date': dt_date(2026, 12, 31)},
        )

        groups = OrderedDict()
        for r in rows:
            if len(r) < 6:
                continue
            cod = r[0]
            groups.setdefault(cod, {'fecha': r[1], 'explicacion': r[6], 'lines': []})
            groups[cod]['lines'].append({
                'cuenta': r[3],
                'debe_haber': r[4].upper(),
                'cantidad': Decimal(r[5] or '0'),
                'referencia': r[7] if len(r) > 7 else '',
            })

        # Reordenar cronológicamente y reasignar numeración secuencial
        sorted_groups = sorted(groups.items(), key=lambda kv: (kv[1]['fecha'], int(kv[0])))

        for idx, (cod, g) in enumerate(sorted_groups, start=1):
            concepto = g['explicacion'] or f'Asiento #{cod}'
            entry_type = 'OPENING' if concepto.upper().startswith('ASIENTO DE APERTURA') else 'GENERAL'

            entry = JournalEntry.objects.create(
                company=company,
                fiscal_year=fy,
                entry_number=idx,
                date=dt_date.fromisoformat(g['fecha']),
                entry_type=entry_type,
                concept=concepto,
                reference=cod,
                status='POSTED',
            )

            for ln in g['lines']:
                acc = acc_by_monica[ln['cuenta']]
                line_concept = ln['referencia'] or None
                JournalEntryLine.objects.create(
                    entry=entry,
                    account=acc,
                    debit=ln['cantidad'] if ln['debe_haber'] == 'D' else Decimal('0.00'),
                    credit=ln['cantidad'] if ln['debe_haber'] == 'H' else Decimal('0.00'),
                    concept=line_concept,
                )
        self.stdout.write(f"Asientos importados: {len(sorted_groups)}")

    # ------------------------------------------------------------------
    # Reporte de verificación
    # ------------------------------------------------------------------
    def _report(self, company):
        totals = JournalEntry.objects.filter(company=company).aggregate(
            db=Sum('lines__debit'),
            cr=Sum('lines__credit'),
        )
        self.stdout.write(f"Total Debe: {totals['db']} | Total Haber: {totals['cr']}")
        self.stdout.write(
            "Importación finalizada. Revisa Balance de Comprobación, "
            "Balance General y Libro Mayor."
        )