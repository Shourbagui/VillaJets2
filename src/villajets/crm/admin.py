from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldAdmin
from unfold.decorators import display
from django.utils.translation import gettext_lazy as _
from .models import (
    Client,
    Document,
    Lead,
    LeadStatus,
    FlightQuote,
    CustomerFeedback,
    CustomerFeedbackType
)

@admin.register(Client)
class ClientAdmin(UnfoldAdmin):
    list_display = ("name", "email", "phone", "created_at")
    search_fields = ("name", "email", "phone")
    ordering = ("-created_at",)


@admin.register(Document)
class DocumentAdmin(UnfoldAdmin):
    list_display = ("client", "document_type", "number", "issued_country", "expiration_date", "created_at")
    search_fields = ("client__name", "number", "issued_country")
    list_filter = ("document_type",)
    autocomplete_fields = ("client",)
    ordering = ("-created_at",)


@admin.register(Lead)
class LeadAdmin(UnfoldAdmin):
    list_display = ("client", "show_status_customized_color", "created_at")
    search_fields = ("client__name", "notes")
    list_filter = ("status",)
    autocomplete_fields = ("client",)
    ordering = ("-created_at",)

    @display(
        description=_("Status"),
        ordering="status",
        label={
            LeadStatus.ACCEPTED: "success",
            LeadStatus.APPROACH: "info",  
            LeadStatus.CLOSED: "success",  
            LeadStatus.LOST: "danger",  
            LeadStatus.QUOTED : "warning"
        },
    )
    def show_status_customized_color(self, obj):
        return obj.status


@admin.register(FlightQuote)
class FlightQuoteAdmin(UnfoldAdmin):
    list_display = ("client", "flight_type", "waiting_area_required", "created_at")
    search_fields = ("client__name", "special_requirements")
    list_filter = ("flight_type", "waiting_area_required")
    autocomplete_fields = ("client",)
    ordering = ("-created_at",)


@admin.register(CustomerFeedback)
class CustomerFeedbackAdmin(UnfoldAdmin):
    list_display = ("flight", "show_customer_feedback_type_customized_color", "created_at")
    search_fields = ("flight__client__name", "content")
    list_filter = ("feedback_type",)
    autocomplete_fields = ("flight",)
    ordering = ("-created_at",)

    @display(
        description=_("Feedback Type"),
        ordering="feedback_type",
        label={
            CustomerFeedbackType.COMPLAINT: "danger",
            CustomerFeedbackType.SATISFACTION: "success",  
            CustomerFeedbackType.CHANGE_REQUEST: "info"
        },
    )
    def show_customer_feedback_type_customized_color(self, obj):
        return obj.feedback_type