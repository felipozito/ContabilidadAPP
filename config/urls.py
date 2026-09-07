from django.contrib import admin
from django.urls import path
from apps.accounting import views as acc_views
from apps.companies import views as comp_views
from apps.invoicing import views as inv_views
from apps.reports import views as rep_views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Autenticación y Login
    path('login/', comp_views.user_login, name='login'),
    path('logout/', comp_views.user_logout, name='logout'),
    
    # Dashboard & General
    path('', acc_views.dashboard, name='dashboard'),

    
    # Companies
    path('companies/', comp_views.company_list, name='company_list'),
    path('companies/create/', comp_views.company_create, name='company_create'),
    path('companies/<int:company_id>/edit/', comp_views.company_edit, name='company_edit'),
    path('companies/<int:company_id>/delete/', comp_views.company_delete, name='company_delete'),
    path('companies/switch/', comp_views.switch_company, name='switch_company'),

    
    # Accounting / Plan de Cuentas / Diario
    path('accounting/accounts/', acc_views.account_list, name='account_list'),
    path('accounting/accounts/create/', acc_views.account_create, name='account_create'),
    path('accounting/accounts/<int:account_id>/edit/', acc_views.account_edit, name='account_edit'),
    path('accounting/accounts/<int:account_id>/delete/', acc_views.account_delete, name='account_delete'),
    path('accounting/accounts/seed/', acc_views.seed_accounts_action, name='seed_accounts_action'),

    path('accounting/journal/', acc_views.journal_entry_list, name='journal_entry_list'),
    path('accounting/journal/create/', acc_views.journal_entry_create, name='journal_entry_create'),
    path('accounting/journal/<int:entry_id>/edit/', acc_views.journal_entry_edit, name='journal_entry_edit'),
    path('accounting/journal/<int:entry_id>/delete/', acc_views.journal_entry_delete, name='journal_entry_delete'),
    path('accounting/ledger/', acc_views.ledger_view, name='ledger'),
    path('accounting/templates/', acc_views.template_list, name='template_list'),
    path('accounting/templates/create/', acc_views.template_create, name='template_create'),
    path('accounting/templates/<int:template_id>/edit/', acc_views.template_edit, name='template_edit'),
    path('accounting/templates/<int:template_id>/use/', acc_views.template_use, name='template_use'),
    path('accounting/templates/<int:template_id>/delete/', acc_views.template_delete, name='template_delete'),
    path('accounting/templates/save-from-entry/<int:entry_id>/', acc_views.template_save_existing, name='template_save_existing'),
    
    # Invoicing / Contacts
    path('invoicing/contacts/', inv_views.contact_list, name='contact_list'),
    path('invoicing/contacts/create/', inv_views.contact_create, name='contact_create'),
    path('invoicing/contacts/<int:contact_id>/edit/', inv_views.contact_edit, name='contact_edit'),
    path('invoicing/contacts/<int:contact_id>/delete/', inv_views.contact_delete, name='contact_delete'),
    path('invoicing/invoices/', inv_views.invoice_list, name='invoice_list'),
    path('invoicing/invoices/create/', inv_views.invoice_create, name='invoice_create'),
    path('invoicing/invoices/<int:invoice_id>/edit/', inv_views.invoice_edit, name='invoice_edit'),
    path('invoicing/invoices/<int:invoice_id>/delete/', inv_views.invoice_delete, name='invoice_delete'),
    path('invoicing/payments/', inv_views.payment_list, name='payment_list'),
    path('invoicing/payments/create/', inv_views.payment_create, name='payment_create'),
    path('invoicing/payments/invoice-info/<int:invoice_id>/', inv_views.payment_invoice_info, name='payment_invoice_info'),
    path('invoicing/payments/<int:payment_id>/delete/', inv_views.payment_delete, name='payment_delete'),
    
    # Reports
    path('reports/', rep_views.reports_home, name='reports_home'),
    path('reports/trial-balance/', rep_views.trial_balance_view, name='trial_balance'),
    path('reports/balance-sheet/', rep_views.balance_sheet_view, name='balance_sheet'),
    path('reports/income-statement/', rep_views.income_statement_view, name='income_statement'),
]
