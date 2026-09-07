from django.contrib import admin
from .models import Company, CompanyUserPermission

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'tax_id', 'email', 'is_accounting_required', 'is_active')
    search_fields = ('name', 'tax_id', 'email')
    list_filter = ('is_active', 'is_accounting_required')

@admin.register(CompanyUserPermission)
class CompanyUserPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('user__username', 'company__name')
