from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldAdmin
from unfold.contrib.forms.widgets import ArrayWidget
from django.contrib.postgres.fields import ArrayField

from .models import (
    FlightRequest,
    PlaneRequirement,
    Flight,
    FlightChecklist,
)

@admin.register(FlightRequest)
class FlightRequestAdmin(UnfoldAdmin):
    list_display = ("client", "passengers", "departure_date", "return_date", "origin", "created_at")
    search_fields = ("client__name", "origin", "destinations")
    list_filter = ("departure_date",)
    autocomplete_fields = ("client",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    formfield_overrides = {
        ArrayField: {
            "widget": ArrayWidget,
        }
    }


@admin.register(PlaneRequirement)
class PlaneRequirementAdmin(UnfoldAdmin):
    list_display = ("flight_request", "model", "seat_count")
    search_fields = ("flight_request__client__name", "model", "other_requirements")
    autocomplete_fields = ("flight_request",)


@admin.register(Flight)
class FlightAdmin(UnfoldAdmin):
    list_display = ("flight_request", "status", "scheduled_departure", "scheduled_return")
    list_filter = ("status",)
    search_fields = ("flight_request__client__name",)
    autocomplete_fields = ("flight_request",)
    ordering = ("-scheduled_departure",)


@admin.register(FlightChecklist)
class FlightChecklistAdmin(UnfoldAdmin):
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
