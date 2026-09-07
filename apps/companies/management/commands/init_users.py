from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.companies.models import Company, CompanyUserPermission

class Command(BaseCommand):
    help = 'Inicializa los usuarios predeterminados admin y contador con sus permisos'

    def handle(self, *args, **options):
        # 1. Crear Superusuario / Admin
        admin_user, created_admin = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@contable.ec',
                'is_staff': True,
                'is_superuser': True
            }
        )
        if created_admin or not admin_user.check_password('admin123'):
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Usuario 'admin' configurado (Pass: admin123)"))

        # 2. Crear usuario Contador
        contador_user, created_contador = User.objects.get_or_create(
            username='contador',
            defaults={
                'email': 'contador@contable.ec',
                'is_staff': False,
                'is_superuser': False
            }
        )
        if created_contador or not contador_user.check_password('contador123'):
            contador_user.set_password('contador123')
            contador_user.save()
            self.stdout.write(self.style.SUCCESS("Usuario 'contador' configurado (Pass: contador123)"))

        # 3. Asignar permisos en todas las empresas activas
        companies = Company.objects.filter(is_active=True)
        for comp in companies:
            CompanyUserPermission.objects.get_or_create(
                user=admin_user,
                company=comp,
                defaults={'role': 'ADMIN', 'is_active': True}
            )
            CompanyUserPermission.objects.get_or_create(
                user=contador_user,
                company=comp,
                defaults={'role': 'ACCOUNTANT', 'is_active': True}
            )

        self.stdout.write(self.style.SUCCESS("Usuarios predeterminados y permisos inicializados correctamente."))