from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

class Company(models.Model):
    name = models.CharField(max_length=200, verbose_name="Razón Social")
    trade_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="Nombre Comercial")
    tax_id = models.CharField(max_length=20, unique=True, verbose_name="Identificación Fiscal / RUC")
    address = models.TextField(verbose_name="Dirección Matriz")
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")
    email = models.EmailField(verbose_name="Correo Electrónico")
    
    # SRI Ecuador specifics
    is_accounting_required = models.BooleanField(default=True, verbose_name="Obligado a llevar Contabilidad")
    special_taxpayer_resolution = models.CharField(max_length=50, blank=True, null=True, verbose_name="Resolución Contribuyente Especial")
    is_rimpe = models.BooleanField(default=False, verbose_name="Régimen RIMPE")
    
    logo = models.ImageField(upload_to='companies/logos/', blank=True, null=True, verbose_name="Logo de la Empresa")
    is_active = models.BooleanField(default=True, verbose_name="Empresa Activa")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ['name']

    def clean(self):
        super().clean()
        if self.tax_id:
            cleaned_tax_id = self.tax_id.strip()
            if len(cleaned_tax_id) != 13:
                raise ValidationError({'tax_id': 'El RUC en Ecuador debe tener exactamente 13 dígitos.'})
            if not cleaned_tax_id.isdigit():
                raise ValidationError({'tax_id': 'El RUC debe contener únicamente dígitos numéricos.'})
            if not cleaned_tax_id.endswith('001'):
                raise ValidationError({'tax_id': 'Un RUC válido en Ecuador debe finalizar en 001.'})

    def __str__(self):
        return f"{self.name} ({self.tax_id})"


class CompanyUserPermission(models.Model):
    ROLE_CHOICES = [
        ('ADMIN', 'Administrador'),
        ('ACCOUNTANT', 'Contador'),
        ('VIEWER', 'Solo Lectura'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='company_permissions')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='user_permissions')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='ACCOUNTANT')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Permiso de Usuario en Empresa"
        verbose_name_plural = "Permisos de Usuarios en Empresas"
        unique_together = ('user', 'company')

    def __str__(self):
        return f"{self.user.username} - {self.company.name} ({self.get_role_display()})"
