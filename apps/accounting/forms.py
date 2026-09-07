from django import forms

from apps.accounting.models import Account


class AccountForm(forms.ModelForm):
    """
    Formulario para crear/editar una cuenta del Plan de Cuentas.

    Con un ModelForm Django:
    - Genera los campos HTML automáticamente desde el modelo.
    - Valida los datos antes de guardarlos (longitud, unicidad, etc.).
    - Evita el código repetido de request.POST.get() que existía en las vistas.
    """

    class Meta:
        model = Account
        fields = ['code', 'name', 'account_type', 'kind', 'parent']

    def __init__(self, *args, company=None, **kwargs):
        """
        Constructor personalizado que recibe la empresa activa para
        limitar el select de "cuenta padre" a las agrupadoras de esa empresa.
        """
        super().__init__(*args, **kwargs)

        if company:
            self.instance.company = company
            qs = Account.objects.filter(company=company, kind='CONTROL')
            # En edición no se permite elegirse a sí misma como padre
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields['parent'].queryset = qs

        # Estilo CSS por defecto para todos los campos
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        """
        Regla de negocio: si la cuenta tiene padre, hereda la naturaleza
        (Activo/Pasivo/Patrimonio/Ingreso/Gasto) de la cuenta agrupadora.
        """
        cleaned_data = super().clean()
        parent = cleaned_data.get('parent')
        if parent:
            cleaned_data['account_type'] = parent.account_type
        return cleaned_data