import re

from django import forms


class SolicitarConsultaForm(forms.Form):
    nome = forms.CharField(
        label='Nome completo',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
    )
    email = forms.EmailField(
        label='E-mail',
        widget=forms.EmailInput(attrs={'class': 'form-input'}),
    )
    whatsapp = forms.CharField(
        label='WhatsApp (com DDD)',
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'type': 'tel',
            'placeholder': '(11) 91234-5678',
        }),
    )

    def clean_whatsapp(self):
        """Normaliza para dígitos com DDI 55 (ex.: 5511912345678)."""
        digitos = re.sub(r'\D', '', self.cleaned_data['whatsapp'])
        if len(digitos) in (10, 11):
            digitos = '55' + digitos
        if not (len(digitos) in (12, 13) and digitos.startswith('55')):
            raise forms.ValidationError('Informe um número de WhatsApp válido com DDD, ex.: (11) 91234-5678.')
        return digitos
