from django.test import TestCase
from django.core.exceptions import ValidationError
from apps.companies.models import Company

class CompanyModelTestCase(TestCase):
    def test_valid_ecuador_ruc(self):
        company = Company(
            name="Empresa Valida",
            tax_id="1790011674001",
            address="Quito",
            email="test@valido.ec"
        )
        company.full_clean()

    def test_invalid_ecuador_ruc_fails(self):
        company = Company(
            name="Empresa Invalida",
            tax_id="12345",
            address="Quito",
            email="test@invalido.ec"
        )
        with self.assertRaises(ValidationError):
            company.full_clean()

    def test_edit_company(self):
        company = Company.objects.create(
            name="Empresa Original",
            tax_id="1790011674001",
            address="Quito",
            email="original@empresa.ec"
        )
        company.name = "Empresa Editada S.A."
        company.save()

        updated = Company.objects.get(id=company.id)
        self.assertEqual(updated.name, "Empresa Editada S.A.")

    def test_delete_company(self):
        company = Company.objects.create(
            name="Empresa Para Borrar",
            tax_id="1790011674002",
            address="Guayaquil",
            email="borrar@empresa.ec"
        )
        comp_id = company.id
        company.delete()
        self.assertFalse(Company.objects.filter(id=comp_id).exists())
