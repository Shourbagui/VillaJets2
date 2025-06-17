from django import forms
from .models import FlightRequest, get_city_choices, get_country_choices

class FlightRequestForm(forms.ModelForm):
    class Meta:
        model = FlightRequest
        fields = '__all__'
        widgets = {
            'origin_country': forms.Select(attrs={'class': 'select2', 'data-placeholder': 'Select origin country'}),
            'origin_city': forms.Select(attrs={'class': 'select2', 'data-placeholder': 'Select origin city'}),
            'destination_country': forms.Select(attrs={'class': 'select2', 'data-placeholder': 'Select destination country'}),
            'destination_city': forms.Select(attrs={'class': 'select2', 'data-placeholder': 'Select destination city'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')

        # Set up country choices
        self.fields['origin_country'].choices = [('', '---------')] + list(get_country_choices())
        self.fields['destination_country'].choices = [('', '---------')] + list(get_country_choices())

        # Set up initial city choices if we have a country selected
        if instance:
            if instance.origin_country:
                self.fields['origin_city'].widget.choices = [('', '---------')] + list(get_city_choices(instance.origin_country))
            if instance.destination_country:
                self.fields['destination_city'].widget.choices = [('', '---------')] + list(get_city_choices(instance.destination_country)) 