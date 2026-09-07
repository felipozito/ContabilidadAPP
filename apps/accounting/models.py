from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.companies.models import Company

# =====================================================================
# PLAN DE CUENTAS
# =====================================================================

class Account(models.Model):
    ACCOUNT_TYPES = [
        ('ASSET', 'Activo'),
        ('LIABILITY', 'Pasivo'),
        ('EQUITY', 'Patrimonio'),
        ('INCOME', 'Ingresos'),
        ('EXPENSE', 'Gastos'),
    ]

    ACCOUNT_KINDS = [
        ('CONTROL', 'Título / Agrupadora'),
        ('MOVEMENT', 'Movimiento / Detalle'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='accounts')
    code = models.CharField(max_length=50, verbose_name="Código Decimal (ej: 1.1.01.001)")
    name = models.CharField(max_length=200, verbose_name="Nombre de la Cuenta")
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, verbose_name="Naturaleza de Cuenta")
    kind = models.CharField(max_length=20, choices=ACCOUNT_KINDS, default='MOVEMENT', verbose_name="Tipo de Cuenta")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name="Cuenta Padre")
    is_active = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Cuenta Contable"
        verbose_name_plural = "Cuentas Contables"
        unique_together = ('company', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def level(self):
        return len(self.code.split('.'))

    def clean(self):
        super().clean()
        if self.parent:
            if self.parent.kind == 'MOVEMENT':
                raise ValidationError({'parent': 'Una cuenta de tipo "Movimiento" no puede tener subcuentas. Cámbiela a "Título / Agrupadora".'})
            if self.parent.account_type != self.account_type:
                raise ValidationError({'account_type': f'La cuenta hija debe mantener la naturaleza ({self.parent.get_account_type_display()}) de su cuenta padre.'})


# =====================================================================
# AÑO FISCAL
# =====================================================================

class FiscalYear(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='fiscal_years')
    year = models.PositiveIntegerField(verbose_name="Año Fiscal")
    start_date = models.DateField(verbose_name="Fecha Inicio")
    end_date = models.DateField(verbose_name="Fecha Fin")
    is_closed = models.BooleanField(default=False, verbose_name="Cerrado")

    class Meta:
        verbose_name = "Año Fiscal"
        verbose_name_plural = "Años Fiscales"
        unique_together = ('company', 'year')
        ordering = ['-year']

    def __str__(self):
        status = "Cerrado" if self.is_closed else "Abierto"
        return f"Año Fiscal {self.year} ({status})"


# =====================================================================
# ASIENTOS CONTABLES (comprobante + líneas de partida doble)
# =====================================================================

class JournalEntry(models.Model):
    ENTRY_TYPES = [
        ('GENERAL', 'Diario / Ajuste'),
        ('SALE', 'Venta'),
        ('PURCHASE', 'Compra'),
        ('PAYMENT', 'Cobro / Pago'),
        ('OPENING', 'Apertura'),
        ('CLOSING', 'Cierre'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Borrador'),
        ('POSTED', 'Asentado / Publicado'),
        ('CANCELLED', 'Anulado'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='journal_entries')
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name='journal_entries')
    entry_number = models.PositiveIntegerField(verbose_name="Número de Asiento")
    date = models.DateField(verbose_name="Fecha")
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='GENERAL', verbose_name="Tipo de Comprobante")
    concept = models.TextField(verbose_name="Concepto / Glosa")
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name="Documento / Referencia")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="Estado")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Asiento Contable"
        verbose_name_plural = "Asientos Contables"
        unique_together = ('company', 'fiscal_year', 'entry_number')
        ordering = ['-date', '-entry_number']

    def __str__(self):
        return f"Asiento #{self.entry_number} ({self.date}) - {self.concept[:40]}"

    @property
    def total_debit(self):
        return sum(line.debit for line in self.lines.all())

    @property
    def total_credit(self):
        return sum(line.credit for line in self.lines.all())

    @property
    def is_balanced(self):
        return abs(self.total_debit - self.total_credit) < Decimal('0.001')

    def clean(self):
        super().clean()
        if self.status == 'POSTED':
            if self.lines.count() < 2:
                raise ValidationError("Un asiento contable requiere al menos 2 líneas (partida doble).")
            if not self.is_balanced:
                raise ValidationError(f"El asiento está desbalanceado. Debe (${self.total_debit:.2f}) != Haber (${self.total_credit:.2f}). Diff: ${abs(self.total_debit - self.total_credit):.2f}")


class JournalEntryLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    concept = models.CharField(max_length=200, blank=True, null=True, verbose_name="Detalle de Línea")
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name="Debe / Débito")
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name="Haber / Crédito")

    class Meta:
        verbose_name = "Línea de Asiento"
        verbose_name_plural = "Líneas de Asiento"

    def clean(self):
        super().clean()
        if self.account.kind != 'MOVEMENT':
            raise ValidationError({'account': 'Solo se puede contabilizar en cuentas de tipo "Movimiento / Detalle".'})
        if self.debit > 0 and self.credit > 0:
            raise ValidationError('Una línea no puede tener valores en el Debe y el Haber simultáneamente.')
        if self.debit <= 0 and self.credit <= 0:
            raise ValidationError('La línea debe registrar un valor mayor a cero en el Debe o en el Haber.')

    def __str__(self):
        return f"{self.account.code} | Debe: {self.debit} | Haber: {self.credit}"


# =====================================================================
# PLANTILLAS DE ASIENTOS RECURRENTES (para repetición mensual)
# =====================================================================

class JournalEntryTemplate(models.Model):
    """
    Plantilla para asientos que se repiten periódicamente (p.ej. alícuotas,
    arriendos, servicios mensuales). Permite reutilizar las mismas líneas
    sin reescribirlas cada mes.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='journal_templates')
    name = models.CharField(max_length=200, verbose_name="Nombre de la Plantilla")
    entry_type = models.CharField(max_length=20, choices=JournalEntry.ENTRY_TYPES, default='GENERAL', verbose_name="Tipo de Comprobante")
    concept = models.TextField(verbose_name="Concepto / Glosa")
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name="Documento / Referencia (opcional)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plantilla de Asiento"
        verbose_name_plural = "Plantillas de Asiento"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.concept[:40]})"

    @property
    def total_debit(self):
        return sum(line.debit for line in self.lines.all())

    @property
    def total_credit(self):
        return sum(line.credit for line in self.lines.all())


class JournalEntryTemplateLine(models.Model):
    template = models.ForeignKey(JournalEntryTemplate, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='template_lines')
    concept = models.CharField(max_length=200, blank=True, null=True, verbose_name="Detalle de Línea")
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name="Debe / Débito")
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name="Haber / Crédito")

    class Meta:
        verbose_name = "Línea de Plantilla"
        verbose_name_plural = "Líneas de Plantilla"

    def __str__(self):
        return f"{self.account.code} | Debe: {self.debit} | Haber: {self.credit}"


# =====================================================================
# CONTROL DE NUMERACIÓN DE REFERENCIAS (ej: REF-000001)
# =====================================================================

class ReferenceNumbering(models.Model):
    """
    Modelo para mantener el control del número de referencia incremental 
    para cada empresa y año fiscal.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='reference_numbering')
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name='reference_numbering')
    next_number = models.PositiveIntegerField(default=1, verbose_name="Próximo Número de Referencia")
    prefix = models.CharField(max_length=10, blank=True, null=True, verbose_name="Prefijo de Referencia (ej: REF-)")

    class Meta:
        verbose_name = "Numeración de Referencia"
        verbose_name_plural = "Numeraciones de Referencia"
        unique_together = ('company', 'fiscal_year')
        ordering = ['-fiscal_year']

    def __str__(self):
        return f"{self.company.name} - Año {self.fiscal_year.year} - Próximo: {self.next_number}"

    def get_peek_reference(self):
        """
        Obtiene la referencia actual (sin incrementar el contador).
        Formato: PREFIJO + 8 dígitos (ej: RET 00000001), o número simple si no hay prefijo.
        """
        if self.prefix:
            return f"{self.prefix}{self.next_number:08d}"
        return f"{self.next_number}"

    def get_next_reference(self):
        """
        Obtiene la siguiente referencia incremental y avanza el contador.
        Formato: PREFIJO + 8 dígitos (ej: RET 00000001).
        """
        reference = self.get_peek_reference()
        self.next_number += 1
        self.save()
        return reference
