from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.template.loader import render_to_string
from datetime import date
from decimal import Decimal
import json

from apps.companies.models import Company
from apps.accounting.models import Account, JournalEntry, JournalEntryLine, JournalEntryTemplate, JournalEntryTemplateLine
from apps.accounting.forms import AccountForm
from apps.accounting.services import (
    seed_sri_ecuador_chart_of_accounts,
    get_or_create_fiscal_year,
    get_next_entry_number,
    get_next_reference_number,
    peek_next_reference_number,
    advance_reference_counter,
    get_income_statement,
    get_ledger,
)
from apps.reports.exporters import export_report_pdf, export_journal_excel, export_ledger_excel


def _journal_lines_from_post(request, company, entry):
    """Construye las líneas válidas de un asiento con una sola consulta."""
    raw_lines = zip(
        request.POST.getlist('account_id[]'),
        request.POST.getlist('line_concept[]'),
        request.POST.getlist('debit[]'),
        request.POST.getlist('credit[]'),
    )
    parsed_lines = []
    account_ids = set()
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')

    for account_id, concept, debit_value, credit_value in raw_lines:
        if not account_id:
            continue
        debit = Decimal(debit_value or '0.00')
        credit = Decimal(credit_value or '0.00')
        if debit > 0 and credit > 0:
            raise ValueError("Una línea no puede tener valores en el Debe y el Haber al mismo tiempo.")
        if debit <= 0 and credit <= 0:
            continue
        account_id = int(account_id)
        parsed_lines.append((account_id, concept, debit, credit))
        account_ids.add(account_id)
        total_debit += debit
        total_credit += credit

    if len(parsed_lines) < 2:
        raise ValueError("Un asiento contable requiere al menos dos líneas con valores.")

    accounts = Account.objects.filter(
        company=company,
        kind='MOVEMENT',
        id__in=account_ids,
    ).in_bulk()
    if len(accounts) != len(account_ids):
        raise ValueError("Las líneas solo pueden usar cuentas de movimiento de la empresa activa.")

    lines = [
        JournalEntryLine(
            entry=entry,
            account=accounts[account_id],
            concept=concept,
            debit=debit,
            credit=credit,
        )
        for account_id, concept, debit, credit in parsed_lines
    ]
    return lines, total_debit, total_credit

# =====================================================================
# DASHBOARD (Vista principal del sistema)
# =====================================================================

@login_required(login_url='login')
def dashboard(request):
    company = getattr(request, 'company', None)
    
    if not company and not Company.objects.exists():
        company = Company.objects.create(
            name="Empresa Demo Ecuador S.A.",
            trade_name="Demo Contable SRI",
            tax_id="1790011674001",
            address="Av. Amazonas y Eloy Alfaro, Quito",
            phone="022345678",
            email="contacto@democontable.ec"
        )
        seed_sri_ecuador_chart_of_accounts(company)
        request.session['active_company_id'] = company.id
        request.company = company
        messages.info(request, "Se ha inicializado automáticamente la Empresa Demo con el Plan de Cuentas base SRI Ecuador.")

    today = date.today()

    selected_month = request.GET.get('month', '')
    try:
        selected_date = date.fromisoformat(selected_month + '-01') if selected_month else None
    except ValueError:
        selected_date = None
    if selected_date is None:
        selected_date = date(today.year, today.month, 1)

    if selected_date > date(today.year, today.month, 1):
        selected_date = date(today.year, today.month, 1)

    if selected_date.month == 12:
        next_month = date(selected_date.year + 1, 1, 1)
    else:
        next_month = date(selected_date.year, selected_date.month + 1, 1)
    end_of_month = next_month - date.resolution

    start_of_month = selected_date

    income_stmt = get_income_statement(company, start_of_month, end_of_month) if company else None

    recent_entries = JournalEntry.objects.filter(
        company=company, date__gte=start_of_month, date__lte=end_of_month
    ).order_by('-date', '-entry_number')[:5] if company else []

    month_options = []
    first_entry = JournalEntry.objects.filter(company=company).order_by('date').first()
    if company and first_entry:
        cursor = date(first_entry.date.year, first_entry.date.month, 1)
        cursor_end = date(today.year, today.month, 1)
        while cursor <= cursor_end:
            month_options.append(cursor.strftime('%Y-%m'))
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
    if not month_options:
        month_options = [selected_date.strftime('%Y-%m')]

    return render(request, 'dashboard.html', {
        'company': company,
        'income_stmt': income_stmt,
        'recent_entries': recent_entries,
        'active_accounts_count': Account.objects.filter(company=company, is_active=True).count() if company else 0,
        'selected_month': selected_date.strftime('%Y-%m'),
        'month_options': month_options,
    })


# =====================================================================
# PLAN DE CUENTAS (CRUD de cuentas contables)
# =====================================================================

@login_required(login_url='login')
def account_list(request):
    company = getattr(request, 'company', None)
    if not company:
        messages.warning(request, "Por favor seleccione o cree una empresa activa.")
        return redirect('company_create')

    accounts = Account.objects.filter(company=company).order_by('code')
    return render(request, 'accounting/account_list.html', {
        'company': company,
        'accounts': accounts
    })


@login_required(login_url='login')
def seed_accounts_action(request):
    company = getattr(request, 'company', None)
    if company:
        count = seed_sri_ecuador_chart_of_accounts(company)
        messages.success(request, f"Se han generado {count} cuentas del Plan Base SRI Ecuador.")
    return redirect('account_list')


@login_required(login_url='login')
def account_create(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    if request.method == 'POST':
        form = AccountForm(request.POST, company=company)
        if form.is_valid():
            account = form.save(commit=False)
            account.company = company
            account.save()
            messages.success(request, f"Cuenta {account.code} - {account.name} creada correctamente.")
            return redirect('account_list')
    else:
        form = AccountForm(company=company)

    return render(request, 'accounting/account_form.html', {
        'company': company,
        'form': form,
    })


@login_required(login_url='login')
def account_edit(request, account_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    account = get_object_or_404(Account, id=account_id, company=company)

    if request.method == 'POST':
        form = AccountForm(request.POST, instance=account, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f"Cuenta {account.code} - {account.name} actualizada correctamente.")
            return redirect('account_list')
    else:
        form = AccountForm(instance=account, company=company)

    return render(request, 'accounting/account_form.html', {
        'company': company,
        'form': form,
    })



@login_required(login_url='login')
def account_delete(request, account_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    account = get_object_or_404(Account, id=account_id, company=company)

    if request.method == 'POST':
        if account.journal_lines.exists():
            messages.error(request, f"No se puede eliminar la cuenta '{account.code} - {account.name}' porque posee asientos contables registrados.")
        elif account.children.exists():
            messages.error(request, f"No se puede eliminar la cuenta agrupadora '{account.code} - {account.name}' porque posee subcuentas asociadas.")
        else:
            code_name = f"{account.code} - {account.name}"
            account.delete()
            messages.success(request, f"Cuenta '{code_name}' eliminada exitosamente.")

    return redirect('account_list')


# =====================================================================
# LIBRO DIARIO (Asientos contables con partida doble)
# =====================================================================

@login_required(login_url='login')
def journal_entry_list(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    start_date_str = request.GET.get('start_date') or f"{date.today().year}-01-01"
    end_date_str = request.GET.get('end_date') or date.today().isoformat()
    start_date = date.fromisoformat(start_date_str)
    end_date = date.fromisoformat(end_date_str)

    # Filtro opcional por cuenta(s) contable(s)
    account_ids = request.GET.getlist('account_id')
    account_ids = [int(a) for a in account_ids if a.isdigit()]

    entries_qs = JournalEntry.objects.filter(
        company=company,
        date__gte=start_date,
        date__lte=end_date,
    )

    if account_ids:
        entries_qs = entries_qs.filter(
            lines__account_id__in=account_ids
        ).distinct()

    entries = entries_qs.prefetch_related('lines__account').order_by('-date', '-entry_number')

    # Cuentas disponibles para el filtro (libro diario usa cuentas de movimiento)
    movement_accounts = Account.objects.filter(
        company=company, kind='MOVEMENT', is_active=True
    ).order_by('code')
    selected_accounts = Account.objects.filter(company=company, id__in=account_ids)

    export_format = request.GET.get('export')
    if export_format == 'excel':
        return export_journal_excel(company, entries, start_date, end_date, selected_account_ids=account_ids)
    if export_format == 'pdf':
        if account_ids:
            account_id_set = set(account_ids)
        else:
            account_id_set = None

        def _filtered_subtotals(entry):
            if not account_id_set:
                return entry.total_debit, entry.total_credit, list(entry.lines.all())
            sum_d = Decimal('0.00')
            sum_c = Decimal('0.00')
            lines = []
            for line in entry.lines.all():
                if line.account_id in account_id_set:
                    sum_d += line.debit or Decimal('0.00')
                    sum_c += line.credit or Decimal('0.00')
                    lines.append(line)
            return sum_d, sum_c, lines

        rows = []
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        for entry in entries:
            entry.total_debit_filtered, entry.total_credit_filtered, entry.lines_filtered = _filtered_subtotals(entry)
            total_debit += entry.total_debit_filtered
            total_credit += entry.total_credit_filtered
            rows.append(entry)
        html_string = render_to_string('accounting/pdf_journal.html', {
            'company': company,
            'entries': rows,
            'start_date': start_date,
            'end_date': end_date,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'selected_accounts': selected_accounts,
            'selected_account_ids': account_ids,
        })
        return export_report_pdf(html_string, f"Libro_Diario_{company.tax_id}.pdf")

    return render(request, 'journal_entry_list.html', {
        'company': company,
        'entries': entries,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'movement_accounts': movement_accounts,
        'selected_account_ids': [a.id for a in selected_accounts],
    })


@login_required(login_url='login')
def journal_entry_create(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    movement_accounts = Account.objects.filter(company=company, kind='MOVEMENT', is_active=True).order_by('code')

    if request.method == 'POST':
        entry_date_str = request.POST.get('date')
        entry_type = request.POST.get('entry_type')
        concept = request.POST.get('concept')
        reference = request.POST.get('reference')
        
        entry_date = date.fromisoformat(entry_date_str) if entry_date_str else date.today()
        fiscal_year = get_or_create_fiscal_year(company, entry_date)
        entry_num = get_next_entry_number(company, fiscal_year)
        
        # Referencia: si no se proporciona se genera la correlativa automática;
        # si se proporciona (precargada o modificada) se avanza el contador
        # para que el siguiente valor por defecto nunca se repita.
        if not reference:
            reference = get_next_reference_number(company, fiscal_year, prefix='RET ')
        else:
            advance_reference_counter(company, fiscal_year, reference, prefix='RET ')

        entry = JournalEntry(
            company=company,
            fiscal_year=fiscal_year,
            entry_number=entry_num,
            date=entry_date,
            entry_type=entry_type,
            concept=concept,
            reference=reference,
            status='DRAFT'
        )

        try:
            lines, total_d, total_c = _journal_lines_from_post(request, company, entry)
            if abs(total_d - total_c) > Decimal('0.001'):
                messages.error(request, f"No se pudo guardar el asiento. Está desbalanceado: Debe (${total_d:.2f}) != Haber (${total_c:.2f}).")
            else:
                with transaction.atomic():
                    entry.status = 'POSTED'
                    entry.save()
                    JournalEntryLine.objects.bulk_create(lines)
                messages.success(request, f"Asiento #{entry.entry_number} asentado exitosamente por un total de ${total_d:.2f}.")
                return redirect('journal_entry_list')

        except Exception as e:
            messages.error(request, f"Error al procesar asiento contable: {e}")

    today_date = date.today()
    next_reference = peek_next_reference_number(
        company, get_or_create_fiscal_year(company, today_date), prefix='RET '
    )

    return render(request, 'journal_entry_form.html', {
        'company': company,
        'movement_accounts': movement_accounts,
        'account_options_json': json.dumps([
            {'id': a.id, 'code': a.code, 'name': a.name} for a in movement_accounts
        ]),
        'today_date': today_date.isoformat(),
        'next_reference': next_reference,
    })


@login_required(login_url='login')
def journal_entry_edit(request, entry_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    entry = get_object_or_404(JournalEntry, id=entry_id, company=company)
    movement_accounts = Account.objects.filter(company=company, kind='MOVEMENT', is_active=True).order_by('code')

    if request.method == 'POST':
        entry.date = date.fromisoformat(request.POST.get('date')) if request.POST.get('date') else date.today()
        entry.entry_type = request.POST.get('entry_type')
        entry.concept = request.POST.get('concept')
        entry.reference = request.POST.get('reference')

        try:
            lines, total_d, total_c = _journal_lines_from_post(request, company, entry)
            if abs(total_d - total_c) > Decimal('0.001'):
                messages.error(request, f"No se pudo guardar el asiento. Está desbalanceado: Debe (${total_d:.2f}) != Haber (${total_c:.2f}).")
            else:
                with transaction.atomic():
                    entry.save()
                    entry.lines.all().delete()
                    JournalEntryLine.objects.bulk_create(lines)
                messages.success(request, f"Asiento #{entry.entry_number} actualizado exitosamente.")
                return redirect('journal_entry_list')

        except Exception as e:
            messages.error(request, f"Error al actualizar asiento contable: {e}")

    return render(request, 'journal_entry_form.html', {
        'company': company,
        'entry': entry,
        'movement_accounts': movement_accounts,
        'account_options_json': json.dumps([
            {'id': a.id, 'code': a.code, 'name': a.name} for a in movement_accounts
        ]),
        'today_date': date.today().isoformat()
    })


@login_required(login_url='login')
def journal_entry_delete(request, entry_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    entry = get_object_or_404(JournalEntry, id=entry_id, company=company)

    if request.method == 'POST':
        entry_num = entry.entry_number
        entry.delete()
        messages.success(request, f"Asiento #{entry_num} eliminado exitosamente.")

    return redirect('journal_entry_list')


# =====================================================================
# LIBRO MAYOR (detalle de movimientos y saldos por cuenta)
# =====================================================================

@login_required(login_url='login')
def ledger_view(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    start_date_str = request.GET.get('start_date') or f"{date.today().year}-01-01"
    end_date_str = request.GET.get('end_date') or date.today().isoformat()
    start_date = date.fromisoformat(start_date_str)
    end_date = date.fromisoformat(end_date_str)

    data = get_ledger(company, start_date, end_date)

    export_format = request.GET.get('export')
    if export_format == 'excel':
        return export_ledger_excel(company, data)
    if export_format == 'pdf':
        html_string = render_to_string('accounting/pdf_ledger.html', {
            'company': company,
            'data': data,
        })
        return export_report_pdf(html_string, f"Libro_Mayor_{company.tax_id}.pdf")

    return render(request, 'accounting/ledger.html', {
        'company': company,
        'data': data,
        'start_date': start_date_str,
        'end_date': end_date_str,
    })


# =====================================================================
# PLANTILLAS DE ASIENTOS RECURRENTES
# =====================================================================

def _template_common_context(company, template=None):
    """Contexto compartido para las vistas de plantillas."""
    movement_accounts = Account.objects.filter(company=company, kind='MOVEMENT', is_active=True).order_by('code')
    return {
        'company': company,
        'movement_accounts': movement_accounts,
        'account_options_json': json.dumps([
            {'id': a.id, 'code': a.code, 'name': a.name} for a in movement_accounts
        ]),
        'template': template,
    }


@login_required(login_url='login')
def template_list(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    templates = JournalEntryTemplate.objects.filter(company=company).prefetch_related('lines__account')
    return render(request, 'accounting/template_list.html', {
        'company': company,
        'templates': templates,
    })


@login_required(login_url='login')
def template_create(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        entry_type = request.POST.get('entry_type') or 'GENERAL'
        concept = request.POST.get('concept', '').strip()
        reference = request.POST.get('reference', '').strip() or None

        account_ids = request.POST.getlist('account_id[]')
        concepts = request.POST.getlist('line_concept[]')
        debits = request.POST.getlist('debit[]')
        credits = request.POST.getlist('credit[]')

        if not name:
            messages.error(request, "Debe indicar un nombre para la plantilla.")
        elif not account_ids:
            messages.error(request, "La plantilla debe tener al menos una línea con cuenta contable.")
        else:
            try:
                template = JournalEntryTemplate.objects.create(
                    company=company,
                    name=name,
                    entry_type=entry_type,
                    concept=concept,
                    reference=reference,
                )
                for acc_id, conc, d_val, c_val in zip(account_ids, concepts, debits, credits):
                    if not acc_id:
                        continue
                    d = Decimal(d_val) if d_val else Decimal('0.00')
                    c = Decimal(c_val) if c_val else Decimal('0.00')
                    if d > 0 or c > 0:
                        JournalEntryTemplateLine.objects.create(
                            template=template,
                            account=Account.objects.get(id=acc_id, company=company),
                            concept=conc,
                            debit=d,
                            credit=c,
                        )
                messages.success(request, f"Plantilla '{name}' creada correctamente.")
                return redirect('template_list')
            except Exception as e:
                messages.error(request, f"Error al crear la plantilla: {e}")

    return render(request, 'accounting/template_form.html', _template_common_context(company))


@login_required(login_url='login')
def template_edit(request, template_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    template = get_object_or_404(JournalEntryTemplate, id=template_id, company=company)

    if request.method == 'POST':
        template.name = request.POST.get('name', '').strip()
        template.entry_type = request.POST.get('entry_type') or 'GENERAL'
        template.concept = request.POST.get('concept', '').strip()
        template.reference = request.POST.get('reference', '').strip() or None

        account_ids = request.POST.getlist('account_id[]')
        concepts = request.POST.getlist('line_concept[]')
        debits = request.POST.getlist('debit[]')
        credits = request.POST.getlist('credit[]')

        if not template.name:
            messages.error(request, "Debe indicar un nombre para la plantilla.")
        else:
            try:
                template.lines.all().delete()
                for acc_id, conc, d_val, c_val in zip(account_ids, concepts, debits, credits):
                    if not acc_id:
                        continue
                    d = Decimal(d_val) if d_val else Decimal('0.00')
                    c = Decimal(c_val) if c_val else Decimal('0.00')
                    if d > 0 or c > 0:
                        JournalEntryTemplateLine.objects.create(
                            template=template,
                            account=Account.objects.get(id=acc_id, company=company),
                            concept=conc,
                            debit=d,
                            credit=c,
                        )
                template.save()
                messages.success(request, f"Plantilla '{template.name}' actualizada correctamente.")
                return redirect('template_list')
            except Exception as e:
                messages.error(request, f"Error al actualizar la plantilla: {e}")

    context = _template_common_context(company, template)
    return render(request, 'accounting/template_form.html', context)


@login_required(login_url='login')
def template_save_existing(request, entry_id):
    """Guarda un asiento ya asentado como plantilla reutilizable."""
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    entry = get_object_or_404(JournalEntry, id=entry_id, company=company)

    # Si viene por GET, se muestra un pequeño formulario para nombrar la plantilla
    if request.method == 'GET':
        suggested = f"{entry.concept[:60]}" if entry.concept else f"Asiento #{entry.entry_number}"
        lines = [{
            'account_id': l.account_id,
            'account_display': f"{l.account.name} - {l.account.code}",
            'concept': l.concept or '',
            'debit': l.debit,
            'credit': l.credit,
        } for l in entry.lines.select_related('account').all()]
        context = _template_common_context(company)
        context.update({
            'source_entry': entry,
            'suggested_name': suggested,
            'prefill_lines': lines,
        })
        return render(request, 'accounting/template_save.html', context)

    # POST: crear la plantilla a partir del asiento
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, "Debe indicar un nombre para la plantilla.")
        return redirect('journal_entry_list')

    template, _ = JournalEntryTemplate.objects.get_or_create(
        company=company,
        name=name,
        defaults={
            'entry_type': entry.entry_type,
            'concept': entry.concept,
            'reference': entry.reference,
        },
    )
    if not template.id or not template.lines.exists():
        template.entry_type = entry.entry_type
        template.concept = entry.concept
        template.reference = entry.reference
        template.save()
        template.lines.all().delete()
        for line in entry.lines.select_related('account').all():
            JournalEntryTemplateLine.objects.create(
                template=template,
                account=line.account,
                concept=line.concept,
                debit=line.debit,
                credit=line.credit,
            )
    messages.success(request, f"Asiento guardado como plantilla '{name}'.")
    return redirect('template_list')


@login_required(login_url='login')
def template_use(request, template_id):
    """Precarga el formulario de nuevo asiento con las líneas de la plantilla."""
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    template = get_object_or_404(JournalEntryTemplate, id=template_id, company=company)
    movement_accounts = Account.objects.filter(company=company, kind='MOVEMENT', is_active=True).order_by('code')

    prefill_lines = [{
        'account_id': l.account_id,
        'account_display': f"{l.account.name} - {l.account.code}",
        'concept': l.concept or '',
        'debit': l.debit,
        'credit': l.credit,
    } for l in template.lines.select_related('account').all()]

    today_date = date.today()
    next_reference = peek_next_reference_number(
        company, get_or_create_fiscal_year(company, today_date), prefix='RET '
    )

    return render(request, 'journal_entry_form.html', {
        'company': company,
        'movement_accounts': movement_accounts,
        'account_options_json': json.dumps([
            {'id': a.id, 'code': a.code, 'name': a.name} for a in movement_accounts
        ]),
        'today_date': today_date.isoformat(),
        'default_entry_type': template.entry_type,
        'default_concept': template.concept,
        'reference_default': template.reference,
        'prefill_lines': prefill_lines,
        'used_template': template,
        'next_reference': next_reference,
    })


@login_required(login_url='login')
def template_delete(request, template_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    template = get_object_or_404(JournalEntryTemplate, id=template_id, company=company)

    if request.method == 'POST':
        name = template.name
        template.delete()
        messages.success(request, f"Plantilla '{name}' eliminada correctamente.")

    return redirect('template_list')
