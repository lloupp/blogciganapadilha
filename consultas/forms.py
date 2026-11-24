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


class MensagemForm(forms.Form):
    texto = forms.CharField(
        min_length=1,
        max_length=2000,
        strip=True,
        error_messages={
            'required': 'Escreva uma mensagem.',
            'max_length': 'A mensagem pode ter no máximo %(limit_value)d caracteres.',
        },
    )


class DepoimentoForm(forms.Form):
    nome = forms.CharField(
        label='Seu nome (como quer que apareça)',
        max_length=60,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex.: Maria S.'}),
    )
    cidade = forms.CharField(
        label='Cidade (opcional)',
        max_length=80,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
    )
    tipo_consulta = forms.ModelChoiceField(
        label='Qual consulta você fez? (opcional)',
        queryset=None,
        required=False,
        empty_label='—',
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    texto = forms.CharField(
        label='Seu depoimento',
        min_length=20,
        max_length=800,
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 5}),
        error_messages={'min_length': 'Escreva um pouquinho mais (pelo menos %(limit_value)d letras).'},
    )
    autorizo = forms.BooleanField(
        label='Autorizo a publicação deste depoimento no site, com o nome que informei.',
        error_messages={'required': 'Precisamos da sua autorização para publicar.'},
    )
    # Armadilha para robôs: campo escondido que pessoas não preenchem.
    site = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'tabindex': '-1', 'autocomplete': 'off',
    }))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import TipoConsulta
        self.fields['tipo_consulta'].queryset = TipoConsulta.objects.filter(ativo=True)
