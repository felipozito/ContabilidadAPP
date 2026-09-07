from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from .models import Company, CompanyUserPermission
from apps.accounting.services import seed_sri_ecuador_chart_of_accounts

def user_login(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('/')
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"¡Bienvenido al sistema, {user.username}!")
            if user.is_staff or user.is_superuser:
                return redirect('/')
            return redirect('dashboard')
        else:
            messages.error(request, "Usuario o contraseña incorrectos. Intente nuevamente.")

    return render(request, 'login.html')


def user_logout(request):
    logout(request)
    messages.info(request, "Has cerrado sesión correctamente.")
    return redirect('login')


@login_required(login_url='login')
def company_list(request):
    permissions = CompanyUserPermission.objects.select_related('company').filter(
        user=request.user, company__is_active=True, is_active=True
    )
    roles = {p.role for p in permissions}
    if request.user.is_superuser or 'ADMIN' in roles or 'ACCOUNTANT' in roles:
        companies = Company.objects.filter(is_active=True)
    else:
        companies = Company.objects.filter(user_permissions__user=request.user, is_active=True)

    return render(request, 'companies/company_list.html', {
        'companies': companies
    })


@login_required(login_url='login')
def company_create(request):
    company = None
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        trade_name = request.POST.get('trade_name', '').strip()
        tax_id = request.POST.get('tax_id', '').strip()
        address = request.POST.get('address', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        seed_accounts = request.POST.get('seed_accounts') == 'on'

        company = Company(
            name=name,
            trade_name=trade_name,
            tax_id=tax_id,
            address=address,
            phone=phone,
            email=email
        )
        try:
            company.full_clean()
            company.save()

            if request.user.is_authenticated:
                CompanyUserPermission.objects.create(
                    user=request.user,
                    company=company,
                    role='ADMIN' if request.user.is_superuser else 'ACCOUNTANT'
                )

            if seed_accounts:
                count = seed_sri_ecuador_chart_of_accounts(company)
                messages.success(request, f"Empresa '{company.name}' creada exitosamente con {count} cuentas del Plan Base SRI Ecuador.")
            else:
                messages.success(request, f"Empresa '{company.name}' creada exitosamente.")

            request.session['active_company_id'] = company.id
            return redirect('dashboard')

        except ValidationError as ve:
            if hasattr(ve, 'message_dict'):
                for field, errs in ve.message_dict.items():
                    messages.error(request, f"['{field}']: {' '.join(errs)}")
            else:
                messages.error(request, f"Error de validación: {' '.join(ve.messages)}")
        except Exception as e:
            messages.error(request, f"Error al crear empresa: {e}")

    return render(request, 'companies/company_form.html', {'company_item': company})


@login_required(login_url='login')
def company_edit(request, company_id):
    if request.user.is_superuser:
        company = get_object_or_404(Company, id=company_id, is_active=True)
    else:
        perm = get_object_or_404(CompanyUserPermission, user=request.user, company_id=company_id, is_active=True)
        company = perm.company

    if request.method == 'POST':
        company.name = request.POST.get('name', '').strip()
        company.trade_name = request.POST.get('trade_name', '').strip()
        company.tax_id = request.POST.get('tax_id', '').strip()
        company.address = request.POST.get('address', '').strip()
        company.phone = request.POST.get('phone', '').strip()
        company.email = request.POST.get('email', '').strip()

        try:
            company.full_clean()
            company.save()
            messages.success(request, f"Empresa '{company.name}' actualizada con éxito.")
            return redirect('company_list')
        except ValidationError as ve:
            if hasattr(ve, 'message_dict'):
                for field, errs in ve.message_dict.items():
                    messages.error(request, f"['{field}']: {' '.join(errs)}")
            else:
                messages.error(request, f"Error de validación: {' '.join(ve.messages)}")
        except Exception as e:
            messages.error(request, f"Error al actualizar la empresa: {e}")

    return render(request, 'companies/company_form.html', {'company_item': company})


@login_required(login_url='login')
def company_delete(request, company_id):
    if request.user.is_superuser:
        company = get_object_or_404(Company, id=company_id)
    else:
        perm = get_object_or_404(CompanyUserPermission, user=request.user, company_id=company_id, role='ADMIN')
        company = perm.company

    if request.method == 'POST':
        company_name = company.name
        if company.journal_entries.exists() or company.invoices.exists():
            company.is_active = False
            company.save()
            messages.warning(request, f"La empresa '{company_name}' posee transacciones registradas y ha sido desactivada para preservar la auditoría.")
        else:
            company.delete()
            messages.success(request, f"Empresa '{company_name}' eliminada exitosamente.")

        if request.session.get('active_company_id') == company_id:
            request.session.pop('active_company_id', None)

    return redirect('company_list')


@login_required(login_url='login')
def switch_company(request):
    if request.method == 'POST':
        company_id = request.POST.get('company_id')
        if company_id:
            request.session['active_company_id'] = int(company_id)
            messages.info(request, "Empresa activa actualizada.")
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
