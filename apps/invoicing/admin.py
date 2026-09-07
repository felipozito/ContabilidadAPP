from django.contrib import admin
from .models import Contact, Invoice, InvoiceItem, Payment

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'id_number', 'contact_type', 'company', 'email', 'phone')
    list_filter = ('contact_type', 'company', 'is_active')
    search_fields = ('name', 'id_number', 'email')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'company', 'invoice_type', 'contact', 'issue_date', 'total', 'status')
    list_filter = ('company', 'invoice_type', 'status', 'issue_date')
    search_fields = ('invoice_number', 'contact__name')
    inlines = [InvoiceItemInline]

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'payment_date', 'payment_method', 'account', 'amount')
    list_filter = ('payment_method', 'payment_date')
