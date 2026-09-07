from .models import Company, CompanyUserPermission

def company_context(request):
    """
    Context processor global que provee `all_companies` (empresas visibles
    para el usuario) en todas las plantillas HTML del sistema.
    """
    if request.user.is_authenticated:
        permissions = CompanyUserPermission.objects.select_related('company').filter(
            user=request.user, company__is_active=True, is_active=True
        )
        roles = {p.role for p in permissions}
        if request.user.is_superuser or 'ADMIN' in roles or 'ACCOUNTANT' in roles:
            all_companies = list(Company.objects.filter(is_active=True))
        elif permissions:
            all_companies = [p.company for p in permissions]
        else:
            all_companies = list(Company.objects.filter(is_active=True))
    else:
        all_companies = list(Company.objects.filter(is_active=True))

    return {
        'all_companies': all_companies,
    }
