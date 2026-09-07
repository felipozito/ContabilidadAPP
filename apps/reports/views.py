from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from datetime import date
from apps.accounting.services import (
    get_trial_balance,
    get_balance_sheet,
    get_income_statement
)
from apps.reports.exporters import export_trial_balance_excel, export_report_pdf

# =====================================================================
# REPORTES FINANCIEROS (Balance de Comprobación, Balance General,
# Estado de Resultados) con exportación a Excel y PDF.
# =====================================================================

@login_required(login_url='login')
def reports_home(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    return render(request, 'reports/reports_home.html', {
        'company': company,
        'today': date.today().isoformat()
    })


@login_required(login_url='login')
def trial_balance_view(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    start_date_str = request.GET.get('start_date') or f"{date.today().year}-01-01"
    end_date_str = request.GET.get('end_date') or date.today().isoformat()

    start_date = date.fromisoformat(start_date_str)
    end_date = date.fromisoformat(end_date_str)

    data = get_trial_balance(company, start_date, end_date)

    export_format = request.GET.get('export')
    if export_format == 'excel':
        return export_trial_balance_excel(company, data)

    return render(request, 'reports/trial_balance.html', {
        'company': company,
        'data': data,
        'start_date': start_date_str,
        'end_date': end_date_str
    })


@login_required(login_url='login')
def balance_sheet_view(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    cutoff_date_str = request.GET.get('cutoff_date') or date.today().isoformat()
    cutoff_date = date.fromisoformat(cutoff_date_str)

    data = get_balance_sheet(company, cutoff_date)

    export_format = request.GET.get('export')
    if export_format == 'pdf':
        html_string = render_to_string('reports/pdf_balance_sheet.html', {
            'company': company,
            'data': data
        })
        return export_report_pdf(html_string, f"Balance_General_{company.tax_id}.pdf")

    return render(request, 'reports/balance_sheet.html', {
        'company': company,
        'data': data,
        'cutoff_date': cutoff_date_str
    })


@login_required(login_url='login')
def income_statement_view(request):
    company = getattr(request, 'company', None)
    if not company:
        return redirect('company_create')

    start_date_str = request.GET.get('start_date') or f"{date.today().year}-01-01"
    end_date_str = request.GET.get('end_date') or date.today().isoformat()

    start_date = date.fromisoformat(start_date_str)
    end_date = date.fromisoformat(end_date_str)

    data = get_income_statement(company, start_date, end_date)

    export_format = request.GET.get('export')
    if export_format == 'pdf':
        html_string = render_to_string('reports/pdf_income_statement.html', {
            'company': company,
            'data': data
        })
        return export_report_pdf(html_string, f"Estado_Resultados_{company.tax_id}.pdf")

    return render(request, 'reports/income_statement.html', {
        'company': company,
        'data': data,
        'start_date': start_date_str,
        'end_date': end_date_str
    })
