from django.contrib import admin
from .models import Account, FiscalYear, JournalEntry, JournalEntryLine, JournalEntryTemplate, JournalEntryTemplateLine

class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 2

class JournalEntryTemplateLineInline(admin.TabularInline):
    model = JournalEntryTemplateLine
    extra = 2

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'kind', 'company', 'is_active')
    list_filter = ('account_type', 'kind', 'company', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('company', 'code')

@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ('company', 'year', 'start_date', 'end_date', 'is_closed')
    list_filter = ('company', 'is_closed')

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('entry_number', 'company', 'date', 'entry_type', 'concept', 'status')
    list_filter = ('company', 'entry_type', 'status', 'date')
    search_fields = ('entry_number', 'concept', 'reference')
    inlines = [JournalEntryLineInline]

@admin.register(JournalEntryTemplate)
class JournalEntryTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'entry_type', 'concept')
    list_filter = ('company', 'entry_type')
    search_fields = ('name', 'concept', 'reference')
    inlines = [JournalEntryTemplateLineInline]
