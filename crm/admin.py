from django.contrib import admin, messages
from unfold.admin import ModelAdmin as UnfoldAdmin
from unfold.decorators import display, action
from django.utils.translation import gettext_lazy as _
from .models import (
    Client,
    Document,
    Lead,
    LeadStatus,
    FlightQuote,
    CustomerFeedback,
    CustomerFeedbackType,
    Mail,
    MailSettings
)
from django.conf import settings
from django.utils.html import format_html
from django.urls import reverse, reverse_lazy
from django.db import models
from unfold.contrib.forms.widgets import WysiwygWidget
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from datetime import date
from django import forms
import re
from django.shortcuts import redirect

class MailInline(admin.TabularInline):
    model = Mail
    extra = 0
    fields = ("subject", "email", "created_at")
    readonly_fields = ("subject", "email", "created_at")
    can_delete = False
    show_change_link = True
    tab = "Mails"

class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    can_delete = False
    fields = ("document_type", "number", "document_country", "expiration_date", "file_preview", "valid_for_flight_inline")
    readonly_fields = ("file_preview", "valid_for_flight_inline")
    tab = "Documents"

    def document_type_display(self, obj):
        return obj.document_type
    document_type_display.short_description = "Document type"

    def file_preview(self, obj):
        if obj.file and obj.file.url:
            url = obj.file.url
            lower_url = url.lower()
            if lower_url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.heic')):
                return format_html(
                    '<a href="{}" target="_blank" class="button button--primary">Open image</a>',
                    url)
            elif lower_url.endswith('.pdf'):
                return format_html(
                    '<a href="{}" target="_blank" class="button button--primary">Open PDF</a>',
                    url)
            else:
                return format_html(
                    '<a href="{}" target="_blank" class="button button--primary">Open file</a>',
                    url)
        return "No preview"
    file_preview.short_description = "Preview"

    def valid_for_flight_inline(self, obj):
        is_valid = obj.is_valid_for_flight() is True
        if is_valid:
            return format_html('<span class="badge badge--success">True</span>')
        else:
            return format_html('<span class="badge badge--danger">False</span>')
    valid_for_flight_inline.short_description = "Valid for Travel"

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = '__all__'

    def clean_number(self):
        number = self.cleaned_data.get('number')
        if not number:
            return ''
        return re.sub(r'[^A-Za-z0-9]', '', number)

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            valid_mime_types = [
                'application/pdf',
                'image/png',
            ]
            valid_extensions = ['.pdf', '.png']
            import os
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError('Only PDF and PNG files are allowed. Please upload a valid file.')
            if hasattr(file, 'content_type') and file.content_type not in valid_mime_types:
                raise forms.ValidationError('Only PDF and PNG files are allowed. Please upload a valid file.')
        return file

@admin.register(Client)
class ClientAdmin(UnfoldAdmin):
    inlines = [DocumentInline]
    change_form_template = "admin/crm/change_form.html"
    list_display = ("name", "email", "phone", "created_at", "view_mails_link")
    search_fields = ("name", "email", "phone")
    ordering = ("-created_at",)

    def view_mails_link(self, obj):
        url = f"{reverse('admin:crm_mail_changelist')}?q={obj.email}"
        return format_html('<a href="{}">View Mails</a>', url)

    view_mails_link.short_description = "Mails"


@admin.register(Document)
class DocumentAdmin(UnfoldAdmin):
    form = DocumentForm
    list_display = ("client_link", "document_type", "number_display", "document_country_display", "expiration_date_display", "valid_for_flight")
    search_fields = ("client__name", "number", "document_country")
    list_filter = ("document_type",)
    autocomplete_fields = ("client",)
    ordering = ("-created_at",)
    readonly_fields = ("file_preview", )
    fields = ("client", "document_type", "file", "file_preview", "number", "document_country", "expiration_date")
    change_form_template = "admin/crm/document/change_form.html"
    actions_row = ["edit_document_action"]

    def file_preview(self, obj):
        if obj.file and obj.file.url:
            url = obj.file.url
            lower_url = url.lower()
            if lower_url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.heic')):
                return format_html(
                    '<a href="{}" target="_blank" class="button button--primary">Open image</a>',
                    url)
            elif lower_url.endswith('.pdf'):
                return format_html(
                    '<a href="{}" target="_blank" class="button button--primary">Open PDF</a>',
                    url)
            else:
                return format_html(
                    '<a href="{}" target="_blank" class="button button--primary">Open file</a>',
                    url)
        return "No document available"
    file_preview.short_description = "Document Preview"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # After save, check for missing fields
        missing = []
        if not obj.number:
            missing.append('Document Number')
        if not obj.document_country:
            missing.append('Document Country')
        if not obj.expiration_date:
            missing.append('Expiration Date')
        if missing:
            # Show warning and preview together
            preview_html = self.file_preview(obj)
            self.message_user(
                request,
                format_html(
                    "<div class='error-message'>Please fill in the following missing fields: <b>{}</b></div>",
                    ', '.join(missing)
                ),
                level=messages.WARNING
            )

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'inline_update/<int:doc_id>/',
                self.admin_site.admin_view(self.inline_update_view),
                name='crm_document_inline_update',
            ),
        ]
        return custom_urls + urls

    @method_decorator(csrf_exempt)
    def inline_update_view(self, request, doc_id):
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
                doc = Document.objects.get(pk=doc_id)
                for field in ['number', 'document_country', 'expiration_date']:
                    if field in data:
                        setattr(doc, field, data[field] or None)
                doc.save()
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})
        return JsonResponse({'success': False, 'error': 'Invalid request'})

    @display(
        description="Valid for Flight",
        label={}
    )
    def valid_for_flight(self, obj:Document):
        return obj.is_valid_for_flight() if obj.is_valid_for_flight() else False
    
    valid_for_flight.boolean = True

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        reasons = request.GET.get('invalid', '')
        reason_map = {
                'missing_number': 'Document Number is missing',
            'missing_document_country': 'Document Country is missing',
                'missing_expiration_date': 'Expiration Date is missing',
                'expired': 'Expiration Date is in the past',
            }
        if reasons:
            reason_list = [reason_map.get(r, r) for r in reasons.split(',') if r]
            extra_context['invalid_reasons'] = reason_list
        else:
            # If not valid and no ?invalid=..., compute reasons dynamically
            obj = self.get_object(request, object_id)
            if obj and not obj.is_valid_for_flight():
                dynamic_reasons = []
                if not obj.number:
                    dynamic_reasons.append(reason_map['missing_number'])
                if not obj.document_country:
                    dynamic_reasons.append(reason_map['missing_document_country'])
                if not obj.expiration_date:
                    dynamic_reasons.append(reason_map['missing_expiration_date'])
                elif obj.expiration_date and obj.expiration_date < date.today():
                    dynamic_reasons.append(reason_map['expired'])
                if dynamic_reasons:
                    extra_context['invalid_reasons'] = dynamic_reasons
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def client_link(self, obj):
        url = reverse('admin:crm_client_change', args=[obj.client.pk])
        return format_html('<a href="{}">{}</a>', url, obj.client)
    client_link.short_description = "Client"
    client_link.admin_order_field = "client"

    @admin.display(description='Number')
    def number_display(self, obj):
        if not obj.number:
            return format_html('<span style="color: red;">To Be Extracted</span>')
        return obj.number

    @admin.display(description='Document Country')
    def document_country_display(self, obj):
        if not obj.document_country:
            return format_html('<span style="color: red;">To Be Extracted</span>')
        return obj.document_country

    @admin.display(description='Expiration Date')
    def expiration_date_display(self, obj):
        if not obj.expiration_date:
            return format_html('<span style="color: red;">To Be Extracted</span>')
        return obj.expiration_date

    @action(
        description=_("Edit document"),
        permissions=["edit_document_action"],
        url_path="edit-document-action"
    )
    def edit_document_action(self, request: HttpRequest, object_id: int):
        return redirect(reverse_lazy("admin:crm_document_change", args=[object_id]))

    def has_edit_document_action_permission(self, request: HttpRequest):
        # Always allow for demonstration; add your own logic if needed
        return True


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


@admin.register(Mail)
class MailAdmin(UnfoldAdmin):
    list_display = ("sender", "email", "subject", "created_at")
    search_fields = ("sender", "email", "subject", "content")
    list_filter = ("is_read", "client")
    ordering = ("-created_at",)
    formfield_overrides = {
        models.TextField: {'widget': WysiwygWidget},
    }


@admin.register(MailSettings)
class MailSettingsAdmin(admin.ModelAdmin):
    change_list_template = "admin/crm/mail_settings_changelist.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['mail_user'] = settings.MAIL_USER
        extra_context['mail_password'] = settings.MAIL_PASSWORD
        return super().changelist_view(request, extra_context=extra_context)