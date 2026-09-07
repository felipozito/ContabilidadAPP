from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from datetime import date
from decimal import Decimal
import re

from apps.invoicing.forms import ContactForm, InvoiceForm, InvoiceItemFormSet, PaymentForm
from apps.invoicing.models import Contact, Invoice, Payment
from apps.accounting.models import Account, JournalEntry, JournalEntryLine
from apps.accounting.services import get_or_create_fiscal_year, get_next_entry_number


# =====================================================================
# HELPERS
# =====================================================================

def _get_contact_account(contact):
    """Cuenta de cuentas por cobrar/pagar del contacto.

    Busca (o crea) una cuenta por contacto: 1.1.02.XXX para clientes
    (cobrar) y 2.1.01.XXX para proveedores (pagar). Solo se usan los
    últimos 3 dígitos del RUC/Cédula (debe ser numérico); si el documento
    no es numérico se usa la cuenta genérica 1.1.02.001 / 2.1.01.001.
    """
    company = contact.company
    if contact.contact_type in ('CLIENT', 'BOTH'):
        prefix_code = '1.1.02'
        default_account_type = 'ASSET'
        parent_code = '1.1.02'
        fallback_code = '1.1.02.001'
    else:
        prefix_code = '2.1.01'
        default_account_type = 'LIABILITY'
        parent_code = '2.1.01'
        fallback_code = '2.1.01.001'

    account_code = fallback_code
    if contact.id_number and contact.id_number != '9999999999999':
        digits = ''.join(re.findall(r'\d', contact.id_number))[-3:]
        if len(digits) == 3:
            account_code = f"{prefix_code}.{digits}"

    try:
        return Account.objects.get(company=company, code=account_code)
    except Account.DoesNotExist:
        parent = Account.objects.filter(company=company, code=parent_code).first()
        account = Account(
            company=company,
            code=account_code,
            name=contact.name,
            account_type=default_account_type,
            kind='MOVEMENT',
            parent=parent,
        )
        account.save()
        return account


def _compute_invoice_amounts(invoice, item_forms):
    """Recalcula subtotales (15% / 0%), IVA y total desde las líneas de detalle."""
    subtotal_15 = Decimal('0.00')
    subtotal_0 = Decimal('0.00')

    for form in item_forms:
        if not form.cleaned_data or form.cleaned_data.get('DELETE'):
            continue
        line_subtotal = form.cleaned_data['quantity'] * form.cleaned_data['unit_price']
        if form.cleaned_data['vat_rate'] == Decimal('15.00'):
            subtotal_15 += line_subtotal
        else:
            subtotal_0 += line_subtotal

    vat_15 = subtotal_15 * Decimal('0.15')
    invoice.subtotal_15 = subtotal_15
    invoice.subtotal_0 = subtotal_0
    invoice.vat_15 = vat_15
    invoice.vat_0 = Decimal('0.00')
    invoice.total = subtotal_15 + subtotal_0 + vat_15


def _ensure_invoice_journal_entry(company, invoice):
    """Crea o actualiza el asiento contable de la factura (Venta o Compra)."""
    journal_entry = invoice.journal_entry
    if journal_entry:
        journal_entry.lines.all().delete()

    fiscal_year = get_or_create_fiscal_year(company, invoice.issue_date)
    entry_number = get_next_entry_number(company, fiscal_year)

    if not journal_entry:
        journal_entry = JournalEntry(
            company=company,
            fiscal_year=fiscal_year,
            entry_number=entry_number,
            date=invoice.issue_date,
            entry_type=invoice.invoice_type,
            concept=f"{'Venta' if invoice.invoice_type == 'SALE' else 'Compra'} {invoice.invoice_number}",
            reference=invoice.invoice_number,
            status='POSTED',
        )
        journal_entry.save()

    net_amount = invoice.subtotal_15 + invoice.subtotal_0

    if invoice.invoice_type == 'SALE':
        # Venta: Dr Cuentas por Cobrar (TOTAL), Cr Ventas (subtotal), Cr IVA Cobrado por Pagar (IVA)
        JournalEntryLine.objects.create(entry=journal_entry, account=_get_contact_account(invoice.contact), debit=invoice.total, credit=0)
        JournalEntryLine.objects.create(entry=journal_entry, account=Account.objects.filter(company=company, code='4.1.01').first(), debit=0, credit=net_amount)
        if invoice.vat_15 > 0:
            JournalEntryLine.objects.create(entry=journal_entry, account=Account.objects.filter(company=company, code='2.1.02.001').first(), debit=0, credit=invoice.vat_15)
    else:
        # Compra: Dr Costo/Gasto (subtotal), Dr Crédito Tributario IVA (IVA), Cr Cuentas por Pagar Proveedores (TOTAL)
        JournalEntryLine.objects.create(entry=journal_entry, account=Account.objects.filter(company=company, code='5.1.01').first(), debit=net_amount, credit=0)
        if invoice.vat_15 > 0:
            JournalEntryLine.objects.create(entry=journal_entry, account=Account.objects.filter(company=company, code='1.1.03.001').first(), debit=invoice.vat_15, credit=0)
        JournalEntryLine.objects.create(entry=journal_entry, account=_get_contact_account(invoice.contact), debit=0, credit=invoice.total)

    invoice.journal_entry = journal_entry
    invoice.save()
    return journal_entry


def _ensure_payment_journal_entry(company, payment):
    """Crea el asiento contable del pago/cobro (Débito a Caja/Banco, Crédito a Cobrar/Pagar)."""
    journal_entry = payment.journal_entry
    if journal_entry:
        journal_entry.lines.all().delete()
        payment.journal_entry = None
        payment.save()
        journal_entry.delete()

    fiscal_year = get_or_create_fiscal_year(company, payment.payment_date)
    entry_number = get_next_entry_number(company, fiscal_year)

    journal_entry = JournalEntry.objects.create(
        company=company,
        fiscal_year=fiscal_year,
        entry_number=entry_number,
        date=payment.payment_date,
        entry_type='PAYMENT',
        concept=f"Pago {payment.invoice.invoice_number}",
        reference=payment.reference or payment.invoice.invoice_number,
        status='POSTED',
    )

    if payment.invoice.invoice_type == 'SALE':
        # Cobro de venta: Dr Caja/Banco, Cr Cuentas por Cobrar
        debit_account = payment.account
        credit_account = _get_contact_account(payment.invoice.contact)
    else:
        # Pago de compra: Dr Cuentas por Pagar, Cr Caja/Banco
        debit_account = _get_contact_account(payment.invoice.contact)
        credit_account = payment.account

    JournalEntryLine.objects.create(entry=journal_entry, account=debit_account, debit=payment.amount, credit=0)
    JournalEntryLine.objects.create(entry=journal_entry, account=credit_account, debit=0, credit=payment.amount)

    payment.journal_entry = journal_entry
    payment.save()

    payment.invoice.status = 'PAID'
    payment.invoice.save()

    return journal_entry


def _save_invoice_items(formset, invoice):
    """Guarda el detalle de la factura calculando los valores por línea.

    Se guarda form por form (no formset.save()) porque Django 5+ persiste los
    formsets con bulk_create, que omite estos cálculos, insertando NULL.
    """
    for form in formset.forms:
        if form in formset.deleted_forms or not form.cleaned_data:
            continue
        item = form.save(commit=False)
        item.invoice = invoice
        item.subtotal = item.quantity * item.unit_price
        item.vat_amount = item.subtotal * (item.vat_rate / Decimal('100'))
        item.total = item.subtotal + item.vat_amount
        item.save()

    for form in formset.deleted_forms:
        if form.instance.pk:
            form.instance.delete()


# =====================================================================
# CONTACTOS (Clientes / Proveedores)
# =====================================================================

@login_required(login_url='login')
def contact_list(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    contacts = Contact.objects.filter(company=company).order_by('name')
    return render(request, 'invoicing/contact_list.html', {'contacts': contacts, 'company': company})


@login_required(login_url='login')
def contact_create(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    if request.method == 'POST':
        form = ContactForm(request.POST, company=company)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.company = company
            contact.save()
            messages.success(request, f"Contacto {contact.name} registrado con éxito.")
            return redirect('contact_list')
    else:
        form = ContactForm(company=company)

    return render(request, 'invoicing/contact_form.html', {'form': form, 'company': company})


@login_required(login_url='login')
def contact_edit(request, contact_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    contact = get_object_or_404(Contact, id=contact_id, company=company)

    if request.method == 'POST':
        form = ContactForm(request.POST, instance=contact, company=company)
        if form.is_valid():
            contact = form.save()
            messages.success(request, f"Contacto {contact.name} actualizado con éxito.")
            return redirect('contact_list')
    else:
        form = ContactForm(instance=contact, company=company)

    return render(request, 'invoicing/contact_form.html', {'form': form, 'company': company})


@login_required(login_url='login')
def contact_delete(request, contact_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    contact = get_object_or_404(Contact, id=contact_id, company=company)
    if request.method == 'POST':
        contact.delete()
        messages.success(request, f"Contacto {contact.name} eliminado.")
    return redirect('contact_list')


# =====================================================================
# FACTURAS
# =====================================================================

@login_required(login_url='login')
def invoice_list(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    invoices = Invoice.objects.filter(company=company).select_related('contact', 'journal_entry').order_by('-issue_date', '-id')
    return render(request, 'invoicing/invoice_list.html', {'invoices': invoices, 'company': company})


@login_required(login_url='login')
def invoice_create(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    if request.method == 'POST':
        form = InvoiceForm(request.POST, company=company)
        formset = InvoiceItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            _compute_invoice_amounts(invoice, formset.forms)

            if invoice.total <= 0:
                messages.error(request, "La factura debe incluir al menos una línea de detalle con valores.")
            else:
                try:
                    with transaction.atomic():
                        invoice.company = company
                        invoice.due_date = invoice.issue_date
                        invoice.status = 'ISSUED'
                        invoice.save()

                        _save_invoice_items(formset, invoice)

                        _ensure_invoice_journal_entry(company, invoice)

                    messages.success(request, f"Factura {invoice.invoice_number} registrada con éxito.")
                    return redirect('invoice_list')
                except Exception as e:
                    messages.error(request, f"Error registrando factura: {e}")
    else:
        form = InvoiceForm(company=company)
        formset = InvoiceItemFormSet()

    return render(request, 'invoicing/invoice_form.html', {
        'company': company,
        'form': form,
        'formset': formset,
        'today_date': date.today().isoformat(),
    })


@login_required(login_url='login')
def invoice_edit(request, invoice_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    invoice = get_object_or_404(Invoice, id=invoice_id, company=company)

    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice, company=company)
        formset = InvoiceItemFormSet(request.POST, instance=invoice)

        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            _compute_invoice_amounts(invoice, formset.forms)

            if invoice.total <= 0:
                messages.error(request, "La factura debe incluir al menos una línea de detalle con valores.")
            else:
                try:
                    with transaction.atomic():
                        invoice.due_date = invoice.issue_date
                        invoice.save()

                        _save_invoice_items(formset, invoice)

                        _ensure_invoice_journal_entry(company, invoice)

                    messages.success(request, f"Factura {invoice.invoice_number} actualizada con éxito.")
                    return redirect('invoice_list')
                except Exception as e:
                    messages.error(request, f"Error al actualizar factura: {e}")
    else:
        form = InvoiceForm(instance=invoice, company=company)
        formset = InvoiceItemFormSet(instance=invoice)

    return render(request, 'invoicing/invoice_form.html', {
        'company': company,
        'form': form,
        'formset': formset,
        'invoice': invoice,
        'today_date': date.today().isoformat(),
    })


@login_required(login_url='login')
def invoice_delete(request, invoice_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    invoice = get_object_or_404(Invoice, id=invoice_id, company=company)
    if request.method == 'POST':
        if invoice.payments.exists():
            messages.error(request, "No se puede eliminar: la factura tiene pagos registrados.")
        else:
            entry = invoice.journal_entry
            invoice.delete()
            if entry:
                entry.lines.all().delete()
                entry.delete()
            messages.success(request, f"Factura {invoice.invoice_number} eliminada.")
    return redirect('invoice_list')


# =====================================================================
# PAGOS / COBROS
# =====================================================================

@login_required(login_url='login')
def payment_list(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    payments = Payment.objects.filter(company=company).select_related('invoice', 'invoice__contact', 'account', 'journal_entry').order_by('-payment_date', '-id')
    return render(request, 'invoicing/payment_list.html', {'payments': payments, 'company': company})


@login_required(login_url='login')
def payment_invoice_info(request, invoice_id):
    """Devuelve el total de una factura en JSON para precargar el monto del pago."""
    company = getattr(request, 'company', None)
    if not company:
        return JsonResponse({'error': 'Sin empresa'}, status=400)
    invoice = get_object_or_404(Invoice, id=invoice_id, company=company)
    return JsonResponse({'id': invoice.id, 'total': str(invoice.total)})


@login_required(login_url='login')
def payment_create(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    invoice_id = request.GET.get('invoice')
    if request.method == 'POST':
        form = PaymentForm(request.POST, company=company)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.company = company
            try:
                with transaction.atomic():
                    payment.save()
                    _ensure_payment_journal_entry(company, payment)
                messages.success(request, f"Pago de {payment.amount} registrado con éxito.")
                return redirect('payment_list')
            except Exception as e:
                messages.error(request, f"Error registrando pago: {e}")
    else:
        initial = {}
        invoice = None
        if invoice_id:
            try:
                invoice = Invoice.objects.get(id=invoice_id, company=company)
                initial['invoice'] = invoice.id
                initial['amount'] = invoice.total
            except Invoice.DoesNotExist:
                pass
        form = PaymentForm(company=company, initial=initial)

    return render(request, 'invoicing/payment_form.html', {'form': form, 'company': company, 'invoice': invoice})


@login_required(login_url='login')
def payment_delete(request, payment_id):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    payment = get_object_or_404(Payment, id=payment_id, company=company)
    if request.method == 'POST':
        invoice = payment.invoice
        entry = payment.journal_entry
        if entry:
            entry.lines.all().delete()
            entry.delete()
        payment.delete()
        invoice.status = 'ISSUED'
        invoice.save()
        messages.success(request, "Pago eliminado y asiento contable revertido.")
    return redirect('payment_list')
