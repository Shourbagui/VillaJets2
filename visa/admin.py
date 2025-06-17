from unfold.admin import ModelAdmin, TabularInline
from django.contrib import admin
from .models import VisaRequirement, VisaCheck, VisaCheckResult
import pycountry

@admin.register(VisaRequirement)
class VisaRequirementAdmin(ModelAdmin):
    list_display = (
        "document_country",
        "destination_country",
        "visa_type",
        "updated",
    )
    list_filter = ("visa_type", "document_country", "destination_country")
    search_fields = ("document_country", "destination_country")
    ordering = ("document_country", "destination_country")

class VisaCheckResultInline(TabularInline):
    model = VisaCheckResult
    extra = 0
    can_delete = False
    fields = (
        "doc_type",
        "document_country",
        "destination_country",
        "visa_type",
    )
    readonly_fields = (
        "doc_type",
        "document_country",
        "destination_country",
        "visa_type",
    )

@admin.register(VisaCheck)
class VisaCheckAdmin(ModelAdmin):
    list_display = ("client", "destination_country", "checked_at")
    autocomplete_fields = ("client",)
    readonly_fields = ("checked_at",)
    list_filter = ("destination_country",)
    inlines = (VisaCheckResultInline,)

    def response_add(self, request, obj, post_url_continue=None):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        return HttpResponseRedirect(
            reverse("admin:visa_visacheck_change", args=[obj.pk])
        )

    def document_country(self, obj):
        return obj.document_country
    document_country.short_description = "Document Country"