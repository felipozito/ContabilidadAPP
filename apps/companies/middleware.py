from .models import Company

class ActiveCompanyMiddleware:
    """
    Middleware que garantiza que `request.company` esté SIEMPRE asignado
    en cada petición HTTP (autenticado o sesión anónima).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.company = None
        active_company_id = request.session.get('active_company_id')

        if active_company_id:
            try:
                request.company = Company.objects.get(id=active_company_id, is_active=True)
            except Company.DoesNotExist:
                request.session.pop('active_company_id', None)

        # Si no hay empresa activa en la sesión, asignar la primera empresa activa disponible
        if not request.company:
            first_company = Company.objects.filter(is_active=True).first()
            if first_company:
                request.company = first_company
                request.session['active_company_id'] = first_company.id

        response = self.get_response(request)
        return response
