from django.contrib import admin
from .models import Country, City, Airport, FlightRequest, PlaneRequirement, Flight, FlightChecklist, FlightLeg
from visa.models import VisaRequirement
from unfold.admin import StackedInline
from smart_selects.db_fields import ChainedForeignKey
from django import forms
from django_quill.widgets import QuillWidget
from django.urls import path
from django.http import JsonResponse
from django.db.models import Count
from unfold.admin import ModelAdmin
from django.db import models

class FlightInline(StackedInline):
    model = Flight
    extra = 1
    autocomplete_fields = ("flight_request",)
    tab=True

class FlightLegInline(StackedInline):
    model = FlightLeg
    extra = 1
    autocomplete_fields = ("origin_airport", "destination_airport")
    fields = ("origin_airport", "destination_airport", "departure_date", "passengers")
    show_change_link = True
    tab = "Itinerary"
    class Media:
        js = ('admin/js/flight_leg_autofill.js',)

class FlightRequestForm(forms.ModelForm):
    class Meta:
        model = FlightRequest
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ['client']:
            widget = self.fields[field].widget
            widget.can_add_related = False
            widget.can_change_related = True
            widget.can_delete_related = False
            widget.can_view_related = False

@admin.register(Country)
class CountryAdmin(ModelAdmin):
    search_fields = ("name", "code")
    list_display = ("code", "name")

@admin.register(City)
class CityAdmin(ModelAdmin):
    search_fields = ("name",)
    list_display = ("name", "country")
    list_filter = ("country",)
    autocomplete_fields = ("country",)

@admin.register(Airport)
class AirportAdmin(ModelAdmin):
    search_fields = ("name", "iata_code", "city", "country_name")
    list_display = ("iata_code", "name", "city", "country_name", "type")
    list_filter = ("country_name", "type", "city")
    ordering = ("country_name", "city", "name")


@admin.register(FlightRequest)
class FlightRequestAdmin(ModelAdmin):
    form = FlightRequestForm
    inlines = [FlightLegInline]
    list_display = (
        "client", "get_origin_airport", "get_final_destination", "get_legs_count", "trip_start", "passengers"
    )
    search_fields = ("client__name",)
    fieldsets = (
        ("Client Information", {
            "fields": ("client", "passengers", "notes")
        }),
    )
    tabs = [
        {"name": "General", "fieldsets": ["Client Information"]},
        {"name": "Itinerary", "inlines": ["FlightLegInline"]}
    ]
    class Media:
        js = ('admin/js/jquery.init.js', 'js/flight_request_admin.js')

    def get_origin_airport(self, obj):
        first_leg = obj.legs.order_by('departure_date').first()
        return first_leg.origin_airport if first_leg else None
    get_origin_airport.short_description = "Origin Airport"

    def get_final_destination(self, obj):
        last_leg = obj.legs.order_by('departure_date').last()
        return last_leg.destination_airport if last_leg else None
    get_final_destination.short_description = "Final Destination"

    def get_legs_count(self, obj):
        return obj.legs.count()
    get_legs_count.short_description = "Legs"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('get-cities/', self.get_cities_view, name='get-cities'),
        ]
        return custom_urls + urls

    def get_cities_view(self, request):
        country = request.GET.get('country')
        if country:
            cities = Airport.objects.filter(country_name=country).values_list('city', flat=True).distinct().order_by('city')
            return JsonResponse({'cities': list(cities)})
        return JsonResponse({'cities': []})

    class Meta:
        verbose_name = "Itinerary"
        verbose_name_plural = "Itineraries"

@admin.register(PlaneRequirement)
class PlaneRequirementAdmin(ModelAdmin):
    list_display = ("flight_request", "model", "seat_count")
    search_fields = ("flight_request__client__name", "model", "other_requirements")
    autocomplete_fields = ("flight_request",)

@admin.register(Flight)
class FlightAdmin(ModelAdmin):
    list_display = ("flight_request", "status", "scheduled_departure", "scheduled_return")
    list_filter = ("status",)
    search_fields = ("flight_request__client__name",)
    autocomplete_fields = ("flight_request",)
    ordering = ("-scheduled_departure",)

@admin.register(FlightChecklist)
class FlightChecklistAdmin(ModelAdmin):
    list_display = (
        "flight",
        "airports_ready",
        "itinerary_ready",
        "crew_ready",
        "customs_ready",
        "completed_at",
    )
    search_fields = ("flight__flight_request__client__name", "notes")
    autocomplete_fields = ("flight",)
    ordering = ("-completed_at",)

def clean(self):
    # Only validate if the parent FlightRequest is saved
    if self.flight_request and self.flight_request.pk:
        previous_legs = FlightLeg.objects.filter(flight_request=self.flight_request).order_by('departure_date')
        if previous_legs.exists():
            last_leg = previous_legs.last()
            if last_leg and last_leg.passengers != self.passengers:
                from django.core.exceptions import ValidationError
                raise ValidationError('Number of passengers must remain the same for all legs unless explicitly changed.')