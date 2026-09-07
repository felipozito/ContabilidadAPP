from django.db import models
from decimal import Decimal
from apps.companies.models import Company
from apps.accounting.models import Account, JournalEntry

class Contact(models.Model):
    CONTACT_TYPES = [
        ('CLIENT', 'Cliente'),
        ('SUPPLIER', 'Proveedor'),
        ('BOTH', 'Cliente / Proveedor'),
    ]

    ID_TYPES = [
        ('RUC', 'RUC (Ecuador)'),
        ('CEDULA', 'Cédula de Identidad'),
        ('PASSPORT', 'Pasaporte'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='contacts')
    contact_type = models.CharField(max_length=20, choices=CONTACT_TYPES, default='CLIENT', verbose_name="Tipo de Contacto")
    id_type = models.CharField(max_length=20, choices=ID_TYPES, default='RUC', verbose_name="Tipo Documento")
    id_number = models.CharField(max_length=20, verbose_name="Número de Documento / RUC")
    name = models.CharField(max_length=200, verbose_name="Razón Social / Nombre")
    email = models.EmailField(blank=True, null=True, verbose_name="Correo Electrónico")
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")
    address = models.TextField(blank=True, null=True, verbose_name="Dirección")
    
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Contacto"
        verbose_name_plural = "Contactos"
        unique_together = ('company', 'id_number')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.id_number})"


class Invoice(models.Model):
    INVOICE_TYPES = [
        ('SALE', 'Factura de Venta'),
        ('PURCHASE', 'Factura de Compra'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Borrador'),
        ('ISSUED', 'Emitida / Asentada'),
        ('PAID', 'Pagada'),
        ('CANCELLED', 'Anulada'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invoices')
    invoice_type = models.CharField(max_length=20, choices=INVOICE_TYPES, verbose_name="Tipo de Factura")
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name='invoices', verbose_name="Cliente / Proveedor")
    invoice_number = models.CharField(max_length=50, verbose_name="Número de Factura (ej: 001-001-000000001)")
    sri_authorization = models.CharField(max_length=49, blank=True, null=True, verbose_name="Clave de Acceso / Autorización SRI")
    
    issue_date = models.DateField(verbose_name="Fecha de Emisión")
    due_date = models.DateField(verbose_name="Fecha de Vencimiento")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="Estado")
    
    subtotal_15 = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name="Subtotal IVA 15%")
    subtotal_0 = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name="Subtotal IVA 0%")
    vat_15 = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name="IVA 15%")
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name="Total Factura")
    
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice', verbose_name="Asiento Contable Generado")

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        unique_together = ('company', 'invoice_type', 'invoice_number')
        ordering = ['-issue_date', '-invoice_number']

    def __str__(self):
        return f"{self.get_invoice_type_display()} {self.invoice_number} - {self.contact.name}"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=250, verbose_name="Descripción de Producto/Servicio")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name="Cantidad")
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Precio Unitario")
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('15.00'), verbose_name="Tarifa IVA %")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Subtotal")
    vat_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Monto IVA")
    total = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Total Linea")

    class Meta:
        verbose_name = "Detalle de Factura"
        verbose_name_plural = "Detalles de Facturas"


class Payment(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Efectivo / Caja Chica'),
        ('BANK_TRANSFER', 'Transferencia Bancaria'),
        ('CHECK', 'Cheque'),
        ('CARD', 'Tarjeta de Crédito / Débito'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments', verbose_name="Factura Afectada")
    payment_date = models.DateField(verbose_name="Fecha de Pago")
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHODS, default='BANK_TRANSFER', verbose_name="Forma de Pago")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name="Cuenta de Caja / Banco")
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Monto Pagado")
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nro. Comprobante / Transferencia")
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment', verbose_name="Asiento Contable de Pago")

    class Meta:
        verbose_name = "Pago / Cobro"
        verbose_name_plural = "Pagos / Cobros"
        ordering = ['-payment_date']

    def __str__(self):
        return f"Pago ${self.amount} ({self.payment_date}) - {self.invoice.invoice_number}"
