from decimal import Decimal
from django.db import models, transaction
from django.db.models import Sum

from apps.accounting.models import Account, FiscalYear, JournalEntry, JournalEntryLine, ReferenceNumbering


# =====================================================================
# PLAN DE CUENTAS BASE SRI (Ecuador)
# Pobla el catálogo de cuentas estándar de la Superintendencia de
# Compañías para una empresa recién creada.
# =====================================================================

def seed_sri_ecuador_chart_of_accounts(company):
    """
    Pobla el Plan de Cuentas base estándar del SRI / Superintendencia de Compañías para Ecuador.
    """
    accounts_data = [
        # 1. ACTIVO
        ("1", "ACTIVO", "ASSET", "CONTROL", None),
        ("1.1", "ACTIVO CORRIENTE", "ASSET", "CONTROL", "1"),
        ("1.1.01", "EFECTIVO Y EQUIVALENTES DE EFECTIVO", "ASSET", "CONTROL", "1.1"),
        ("1.1.01.001", "Caja General", "ASSET", "MOVEMENT", "1.1.01"),
        ("1.1.01.002", "Caja Chica", "ASSET", "MOVEMENT", "1.1.01"),
        ("1.1.01.003", "Bancos Nacionales", "ASSET", "MOVEMENT", "1.1.01"),
        ("1.1.02", "CUENTAS Y DOCUMENTOS POR COBRAR CLIENTES", "ASSET", "CONTROL", "1.1"),
        ("1.1.02.001", "Clientes Locales", "ASSET", "MOVEMENT", "1.1.02"),
        ("1.1.03", "ACTIVOS POR IMPUESTOS CORRIENTES", "ASSET", "CONTROL", "1.1"),
        ("1.1.03.001", "Crédito Tributario IVA (15%)", "ASSET", "MOVEMENT", "1.1.03"),
        ("1.1.03.002", "Retenciones en la Fuente Renta", "ASSET", "MOVEMENT", "1.1.03"),
        
        # 2. PASIVO
        ("2", "PASIVO", "LIABILITY", "CONTROL", None),
        ("2.1", "PASIVO CORRIENTE", "LIABILITY", "CONTROL", "2"),
        ("2.1.01", "CUENTAS Y DOCUMENTOS POR PAGAR PROVEEDORES", "LIABILITY", "CONTROL", "2.1"),
        ("2.1.01.001", "Proveedores Locales", "LIABILITY", "MOVEMENT", "2.1.01"),
        ("2.1.02", "OBLIGACIONES CON EL SRI Y SEGURIDAD SOCIAL", "LIABILITY", "CONTROL", "2.1"),
        ("2.1.02.001", "IVA Cobrado por Pagar (15%)", "LIABILITY", "MOVEMENT", "2.1.02"),
        ("2.1.02.002", "Retenciones por Pagar SRI", "LIABILITY", "MOVEMENT", "2.1.02"),
        ("2.1.02.003", "Aportes e Impuestos IESS por Pagar", "LIABILITY", "MOVEMENT", "2.1.02"),
        
        # 3. PATRIMONIO
        ("3", "PATRIMONIO", "EQUITY", "CONTROL", None),
        ("3.1", "CAPITAL SOCIAL", "EQUITY", "CONTROL", "3"),
        ("3.1.01", "Capital Suscrito o Asignado", "EQUITY", "MOVEMENT", "3.1"),
        ("3.2", "RESULTADOS", "EQUITY", "CONTROL", "3"),
        ("3.2.01", "Ganancia o Pérdida del Ejercicio", "EQUITY", "MOVEMENT", "3.2"),
        ("3.2.02", "Resultados Acumulados", "EQUITY", "MOVEMENT", "3.2"),
        
        # 4. INGRESOS
        ("4", "INGRESOS", "INCOME", "CONTROL", None),
        ("4.1", "INGRESOS DE ACTIVIDADES ORDINARIAS", "INCOME", "CONTROL", "4"),
        ("4.1.01", "Ventas Locales de Bienes y Servicios", "INCOME", "MOVEMENT", "4.1"),
        ("4.1.02", "Otros Ingresos Operacionales", "INCOME", "MOVEMENT", "4.1"),
        
        # 5. GASTOS
        ("5", "GASTOS Y COSTOS", "EXPENSE", "CONTROL", None),
        ("5.1", "COSTOS DE VENTAS Y OPERACIÓN", "EXPENSE", "CONTROL", "5"),
        ("5.1.01", "Costo de Ventas / Mercadería", "EXPENSE", "MOVEMENT", "5.1"),
        ("5.2", "GASTOS ADMINISTRATIVOS Y DE VENTAS", "EXPENSE", "CONTROL", "5"),
        ("5.2.01", "Sueldos, Salarios y Beneficios", "EXPENSE", "MOVEMENT", "5.2"),
        ("5.2.02", "Arriendos y Alquileres", "EXPENSE", "MOVEMENT", "5.2"),
        ("5.2.03", "Servicios Básicos (Luz, Agua, Internet)", "EXPENSE", "MOVEMENT", "5.2"),
        ("5.2.04", "Suministros y Gastos Generales", "EXPENSE", "MOVEMENT", "5.2"),
    ]

    account_map = {}
    with transaction.atomic():
        for code, name, acc_type, kind, parent_code in accounts_data:
            parent_acc = account_map.get(parent_code) if parent_code else None
            account, _ = Account.objects.get_or_create(
                company=company,
                code=code,
                defaults={
                    'name': name,
                    'account_type': acc_type,
                    'kind': kind,
                    'parent': parent_acc
                }
            )
            account_map[code] = account
    return len(account_map)


# =====================================================================
# AÑO FISCAL Y NUMERACIÓN CORRELATIVA
# =====================================================================

def get_next_entry_number(company, fiscal_year):
    """
    Obtiene el número correlativo siguiente para un asiento contable en la empresa.
    """
    last = JournalEntry.objects.filter(company=company, fiscal_year=fiscal_year).aggregate(max_num=models.Max('entry_number'))['max_num']
    return (last or 0) + 1


def get_or_create_fiscal_year(company, date):
    """
    Obtiene o genera el año fiscal activo según la fecha.
    """
    from datetime import date as dt_date
    year = date.year
    fy, _ = FiscalYear.objects.get_or_create(
        company=company,
        year=year,
        defaults={
            'start_date': dt_date(year, 1, 1),
            'end_date': dt_date(year, 12, 31),
            'is_closed': False
        }
    )
    return fy


# =====================================================================
# REPORTES CONTABLES
# =====================================================================

def get_trial_balance(company, start_date, end_date):
    """
    Calcula el Balance de Comprobación (Sumas y Saldos) para las cuentas de movimiento.

    Se usa UNA sola consulta con GROUP BY (en lugar de 1 consulta por cuenta, que
    era un problema "N+1" y escalaba mal con más cuentas o asientos).
    """
    # 1) Agrupar las líneas de asiento por cuenta en una única consulta
    sums_by_account = {
        row['account_id']: row
        for row in JournalEntryLine.objects.filter(
            entry__company=company,
            entry__status='POSTED',
            entry__date__gte=start_date,
            entry__date__lte=end_date,
            account__kind='MOVEMENT',
            account__is_active=True,
        ).values('account_id').annotate(
            sum_debit=Sum('debit'),
            sum_credit=Sum('credit'),
        )
    }

    trial_data = []

    total_debit_sum = Decimal('0.00')
    total_credit_sum = Decimal('0.00')
    total_debt_balance = Decimal('0.00')
    total_cred_balance = Decimal('0.00')

    # 2) Recorrer el plan de cuentas y aplicar la naturaleza de saldo de cada cuenta
    for account in Account.objects.filter(company=company, kind='MOVEMENT', is_active=True).order_by('code'):
        row = sums_by_account.get(account.id)
        if row:
            sum_debit = row['sum_debit'] or Decimal('0.00')
            sum_credit = row['sum_credit'] or Decimal('0.00')
        else:
            sum_debit = Decimal('0.00')
            sum_credit = Decimal('0.00')

        net = sum_debit - sum_credit
        debt_balance = Decimal('0.00')
        cred_balance = Decimal('0.00')

        # Naturalezas deudoras vs acreedoras
        if account.account_type in ['ASSET', 'EXPENSE']:
            if net >= 0:
                debt_balance = net
            else:
                cred_balance = abs(net)
        else:
            if net <= 0:
                cred_balance = abs(net)
            else:
                debt_balance = net

        total_debit_sum += sum_debit
        total_credit_sum += sum_credit
        total_debt_balance += debt_balance
        total_cred_balance += cred_balance

        trial_data.append({
            'account': account,
            'sum_debit': sum_debit,
            'sum_credit': sum_credit,
            'debt_balance': debt_balance,
            'cred_balance': cred_balance,
        })

    return {
        'lines': trial_data,
        'total_debit_sum': total_debit_sum,
        'total_credit_sum': total_credit_sum,
        'total_debt_balance': total_debt_balance,
        'total_cred_balance': total_cred_balance,
        'is_balanced': abs(total_debt_balance - total_cred_balance) < Decimal('0.01')
    }


def get_balance_sheet(company, cutoff_date):
    """
    Calcula el Balance General (Estado de Situación Financiera: Activo = Pasivo + Patrimonio).

    Dos consultas con GROUP BY: una para cuentas de balance (Activo/Pasivo/Patrimonio)
    y otra para Ingresos/Gastos (resultado del ejercicio).
    """
    lines_qs = JournalEntryLine.objects.filter(
        entry__company=company,
        entry__status='POSTED',
        entry__date__lte=cutoff_date,
    )

    # 1) Sumas (Debe/Haber) por cuenta de balance hasta la fecha de corte
    sums_by_account = {
        row['account_id']: row
        for row in lines_qs.filter(account__account_type__in=['ASSET', 'LIABILITY', 'EQUITY'])
        .values('account_id')
        .annotate(sum_debit=Sum('debit'), sum_credit=Sum('credit'))
    }

    assets = []
    liabilities = []
    equity = []

    total_assets = Decimal('0.00')
    total_liabilities = Decimal('0.00')
    total_equity = Decimal('0.00')

    for acc in Account.objects.filter(company=company, kind='MOVEMENT', account_type__in=['ASSET', 'LIABILITY', 'EQUITY']).order_by('code'):
        row = sums_by_account.get(acc.id)
        if row:
            sum_debit = row['sum_debit'] or Decimal('0.00')
            sum_credit = row['sum_credit'] or Decimal('0.00')
        else:
            sum_debit = Decimal('0.00')
            sum_credit = Decimal('0.00')

        if acc.account_type == 'ASSET':
            balance = sum_debit - sum_credit
            assets.append({'account': acc, 'balance': balance})
            total_assets += balance
        elif acc.account_type == 'LIABILITY':
            balance = sum_credit - sum_debit
            liabilities.append({'account': acc, 'balance': balance})
            total_liabilities += balance
        elif acc.account_type == 'EQUITY':
            balance = sum_credit - sum_debit
            equity.append({'account': acc, 'balance': balance})
            total_equity += balance

    # 2) Resultado del ejercicio (Ingresos - Gastos) hasta la fecha, agrupado por tipo
    totals_by_type = {
        row['account__account_type']: row
        for row in lines_qs.filter(account__account_type__in=['INCOME', 'EXPENSE'])
        .values('account__account_type')
        .annotate(sum_debit=Sum('debit'), sum_credit=Sum('credit'))
    }

    income_row = totals_by_type.get('INCOME')
    expense_row = totals_by_type.get('EXPENSE')

    total_income = (income_row['sum_credit'] - income_row['sum_debit']) if income_row else Decimal('0.00')
    total_expense = (expense_row['sum_debit'] - expense_row['sum_credit']) if expense_row else Decimal('0.00')
    current_period_result = total_income - total_expense

    total_equity_with_result = total_equity + current_period_result

    return {
        'cutoff_date': cutoff_date,
        'assets': assets,
        'total_assets': total_assets,
        'liabilities': liabilities,
        'total_liabilities': total_liabilities,
        'equity': equity,
        'current_period_result': current_period_result,
        'total_equity': total_equity_with_result,
        'total_liabilities_and_equity': total_liabilities + total_equity_with_result,
        'is_balanced': abs(total_assets - (total_liabilities + total_equity_with_result)) < Decimal('0.01')
    }


def get_ledger(company, start_date, end_date):
    """
    Calcula el Libro Mayor por cuenta para el periodo indicado:
    saldo inicial, movimientos (debe/haber con saldo corrido), sumas
    y saldo final. Solo incluye cuentas con saldo inicial o movimiento.
    """
    def _balance(account, signed):
        # signed = +deudor / -acreedor; se muestra en la naturaleza de la cuenta
        if account.account_type in ('ASSET', 'EXPENSE'):
            return signed
        return -signed

    lines_in_period = JournalEntryLine.objects.filter(
        entry__company=company,
        entry__status='POSTED',
        entry__date__gte=start_date,
        entry__date__lte=end_date,
        account__kind='MOVEMENT',
        account__is_active=True,
    ).select_related('entry', 'account').order_by('entry__date', 'entry__entry_number')

    by_account = {}
    for line in lines_in_period:
        by_account.setdefault(line.account_id, []).append(line)

    opening_rows = JournalEntryLine.objects.filter(
        entry__company=company,
        entry__status='POSTED',
        entry__date__lt=start_date,
        account__kind='MOVEMENT',
        account__is_active=True,
    ).values('account_id').annotate(
        sum_debit=Sum('debit'),
        sum_credit=Sum('credit'),
    )
    opening_by_account = {
        row['account_id']: (row['sum_debit'] or Decimal('0.00')) - (row['sum_credit'] or Decimal('0.00'))
        for row in opening_rows
    }

    accounts = list(Account.objects.filter(company=company, kind='MOVEMENT', is_active=True).order_by('code'))

    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')

    ledger_accounts = []
    for account in accounts:
        opening_signed = opening_by_account.get(account.id, Decimal('0.00'))
        lines = by_account.get(account.id, [])

        if opening_signed == 0 and not lines:
            continue

        running = opening_signed
        movements = []
        for line in lines:
            running += (line.debit or Decimal('0.00')) - (line.credit or Decimal('0.00'))
            movements.append({
                'date': line.entry.date,
                'entry_number': line.entry.entry_number,
                'reference': line.entry.reference or '',
                'concept': line.entry.concept,
                'line_concept': line.concept or '',
                'debit': line.debit,
                'credit': line.credit,
                'balance': _balance(account, running),
            })

        acc_debit = sum((m['debit'] or Decimal('0.00')) for m in movements)
        acc_credit = sum((m['credit'] or Decimal('0.00')) for m in movements)
        total_debit += acc_debit
        total_credit += acc_credit

        ledger_accounts.append({
            'account': account,
            'opening_balance': _balance(account, opening_signed),
            'movements': movements,
            'total_debit': acc_debit,
            'total_credit': acc_credit,
            'closing_balance': _balance(account, running),
            'nature_debt': account.account_type in ('ASSET', 'EXPENSE'),
        })

    return {
        'accounts': ledger_accounts,
        'start_date': start_date,
        'end_date': end_date,
        'total_debit': total_debit,
        'total_credit': total_credit,
    }


def get_income_statement(company, start_date, end_date):
    """
    Calcula el Estado de Resultados (ingresos y gastos) del periodo seleccionado.
    """
    # Una sola consulta con GROUP BY por cuenta de ingreso/gasto
    sums_by_account = {
        row['account_id']: row
        for row in JournalEntryLine.objects.filter(
            entry__company=company,
            entry__status='POSTED',
            entry__date__gte=start_date,
            entry__date__lte=end_date,
            account__kind='MOVEMENT',
            account__account_type__in=['INCOME', 'EXPENSE'],
        ).values('account_id').annotate(
            sum_debit=Sum('debit'),
            sum_credit=Sum('credit'),
        )
    }

    incomes = []
    expenses = []
    total_income = Decimal('0.00')
    total_expense = Decimal('0.00')

    for acc in Account.objects.filter(company=company, kind='MOVEMENT', account_type__in=['INCOME', 'EXPENSE']).order_by('code'):
        row = sums_by_account.get(acc.id)
        if not row:
            continue  # cuenta sin movimiento en el periodo

        credit = row['sum_credit'] or Decimal('0.00')
        debit = row['sum_debit'] or Decimal('0.00')

        if acc.account_type == 'INCOME':
            balance = credit - debit  # los ingresos tienen naturaleza acreedora
            if balance != 0:
                incomes.append({'account': acc, 'balance': balance})
                total_income += balance
        else:
            balance = debit - credit  # los gastos tienen naturaleza deudora
            if balance != 0:
                expenses.append({'account': acc, 'balance': balance})
                total_expense += balance

    net_profit = total_income - total_expense

    return {
        'start_date': start_date,
        'end_date': end_date,
        'incomes': incomes,
        'total_income': total_income,
        'expenses': expenses,
        'total_expense': total_expense,
        'net_profit': net_profit
    }


def _get_reference_numbering(company, fiscal_year, prefix):
    """Obtiene (o crea) el control de numeración de referencia de la empresa/año.
    Si ya existe, se respeta su prefijo y contador actuales."""
    ref_numbering, _ = ReferenceNumbering.objects.get_or_create(
        company=company,
        fiscal_year=fiscal_year,
        defaults={'next_number': 1, 'prefix': prefix}
    )
    return ref_numbering


def peek_next_reference_number(company, fiscal_year, prefix=''):
    """
    Obtiene la siguiente referencia a usar SIN consumirla (para precargar el formulario).
    Formato: PREFIX + 8 dígitos (ej: RET 00000001)
    """
    return _get_reference_numbering(company, fiscal_year, prefix).get_peek_reference()


def get_next_reference_number(company, fiscal_year, prefix=''):
    """
    Obtiene el siguiente número de referencia incremental para la empresa y año fiscal
    y avanza el contador. Formato: PREFIX + 8 dígitos (ej: RET 00000001).
    """
    return _get_reference_numbering(company, fiscal_year, prefix).get_next_reference()


def advance_reference_counter(company, fiscal_year, reference, prefix=''):
    """
    Cuando el usuario guarda con una referencia propia, avanza el contador
    automático más allá de esa referencia para que el siguiente valor por defecto
    nunca se repita.
    """
    if not reference:
        return
    import re
    match = re.search(r'(\d+)\s*$', str(reference))
    if not match:
        return
    used = int(match.group(1))
    ref_numbering = _get_reference_numbering(company, fiscal_year, prefix)
    if used >= ref_numbering.next_number:
        ref_numbering.next_number = used + 1
        ref_numbering.save()
