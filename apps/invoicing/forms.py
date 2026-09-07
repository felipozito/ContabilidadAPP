from decimal import Decimal

from django import forms

from apps.invoicing.models import Contact, Invoice, InvoiceItem, Payment
from apps.accounting.models import Account


class ContactForm(forms.ModelForm):
    """
    Formulario de Clientes/Proveedores. El ModelForm valida y genera los campos
    automáticamente, eliminando el request.POST.get manual de las vistas.
    """

    class Meta:
        model = Contact
        fields = ['contact_type', 'id_type', 'id_number', 'name', 'email', 'phone', 'address']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        # La empresa se fija antes de validar para que el unique_together
        # (company + id_number) se compruebe correctamente.
        if company:
            self.instance.company = company
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class InvoiceItemForm(forms.ModelForm):
    """Formulario de una línea de detalle de la factura (producto/servicio)."""

    # Solo se permiten las tarifas de IVA del Ecuador: 15% y 0%
    vat_rate = forms.TypedChoiceField(
        coerce=Decimal,
        choices=[(Decimal('15.00'), 'IVA 15%'), (Decimal('0.00'), 'IVA 0%')],
    )

    class Meta:
        model = InvoiceItem
        fields = ['description', 'quantity', 'unit_price', 'vat_rate']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Clases CSS para que el JavaScript pueda calcular los totales en vivo
        self.fields['description'].widget.attrs.update({'class': 'form-control'})
        self.fields['quantity'].widget.attrs.update({'class': 'form-control qty-input'})
        self.fields['unit_price'].widget.attrs.update({'class': 'form-control price-input'})
        self.fields['vat_rate'].widget.attrs.update({'class': 'form-control vat-input'})
        # El checkbox "eliminar" de las filas existentes
        if 'DELETE' in self.fields:
            self.fields['DELETE'].widget.attrs.update({'class': 'delete-checkbox'})


# Conjunto de líneas de detalle que se renderiza dentro del formulario de factura.
# "inline" significa que todas las líneas pertenecen a la misma factura.
# Se exige al menos 1 línea (una factura sin detalle no tiene sentido).
class _InvoiceItemFormSet(forms.BaseInlineFormSet):
    """Agrega la clase CSS al checkbox de eliminar.

    Django añade el campo DELETE al formset DESPUÉS de construir el formulario
    (en add_fields), por lo que el __init__ del formulario no puede asignarle
    la clase. Aquí se hace en el momento correcto.
    """

    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.fields['DELETE'].widget.attrs.update({'class': 'delete-checkbox'})


InvoiceItemFormSet = forms.inlineformset_factory(
    Invoice,
    InvoiceItem,
    form=InvoiceItemForm,
    formset=_InvoiceItemFormSet,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class InvoiceForm(forms.ModelForm):
    """
    Formulario de Factura (Venta/Compra). Los subtotales e IVA se calculan
    automáticamente a partir de las líneas de detalle (InvoiceItemFormSet).
    """

    class Meta:
        model = Invoice
        fields = ['invoice_type', 'contact', 'invoice_number', 'issue_date', 'due_date']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.instance.company = company
            # Limitar el select de contacto a la empresa activa
            self.fields['contact'].queryset = Contact.objects.filter(company=company, is_active=True)
        # Fechas con selector nativo de calendario
        self.fields['issue_date'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        self.fields['due_date'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class PaymentForm(forms.ModelForm):
    """
    Formulario para registrar un Pago/Cobro. El pago genera automáticamente
    su asiento contable en la vista.
    """

    class Meta:
        model = Payment
        fields = ['invoice', 'payment_date', 'payment_method', 'account', 'amount', 'reference']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.instance.company = company
            # Solo se pueden pagar/cobrar facturas de la misma empresa
            self.fields['invoice'].queryset = Invoice.objects.filter(company=company)
            # La cuenta de caja/banco debe ser de movimiento de la empresa
            self.fields['account'].queryset = Account.objects.filter(company=company, kind='MOVEMENT')
        # Fecha con selector nativo de calendario
        self.fields['payment_date'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})