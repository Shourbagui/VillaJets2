from django.db import models
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from django.utils import timezone
from crm.models import Client, Document  # adjust if path differs
import pycountry
from django.utils.html import format_html
from django.urls import reverse
from django.contrib import admin

# -------------------------------------------------------------------
# helper: ISO-2 / ISO-3 / full name → ISO-3  (always upper-case)
# -------------------------------------------------------------------
def _to_iso3(value: str) -> str:
    if not value:
        return ""
    v = str(value).strip().upper()
    # already ISO-3?
    if len(v) == 3:
        return v
    try:
        return pycountry.countries.lookup(v).alpha_3.upper()
    except LookupError:
        return v

class VisaRequirement(models.Model):
    class VisaType(models.TextChoices):
        VISA   = "VISA",  _( "Visa required")
        EVISA  = "EVISA", _( "e-Visa")
        VOA    = "VOA",   _( "Visa on arrival")
        NONE   = "NONE",  _( "No visa needed")
        OTHER  = "OTHER", _( "Other / check notes")

    document_country = models.CharField(max_length=3, db_index=True, null=True, blank=True)
    destination_country = models.CharField(max_length=3, db_index=True, null=True, blank=True)
    visa_type = models.CharField(max_length=50, choices=VisaType.choices, db_index=True)
    notes = models.TextField(blank=True)
    updated = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.document_country:
            self.document_country = self.document_country.upper().strip()
        if self.destination_country:
            self.destination_country = self.destination_country.upper().strip()
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document_country", "destination_country"],
                name="unique_document_destination_rule",
            )
        ]
        verbose_name = _("Visa requirement")
        verbose_name_plural = _("Visa requirements")
        indexes = [
            models.Index(fields=['document_country', 'destination_country']),
        ]

    def __str__(self):
        return (
            f"{self.document_country} → {self.destination_country}: "
            f"{self.get_visa_type_display()}"
        )

ISO3_COUNTRIES = sorted([(c.alpha_3, f"{c.alpha_3} - {c.name}") for c in pycountry.countries], key=lambda x: x[1])

class VisaCheck(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    destination_country = models.CharField(
        max_length=3,
        choices=ISO3_COUNTRIES,
    )
    visa_type = models.CharField(
        max_length=5,
        choices=VisaRequirement.VisaType.choices,
        editable=False,
        blank=True,
    )
    checked_at = models.DateTimeField(default=timezone.now, editable=False)

    @property
    def document_country(self):
        doc = self.client.documents.first()
        return doc.document_country if doc else None

    def _lookup_visa(self):
        doc_country = str(self.document_country).upper().strip()
        dest_country = str(self.destination_country).upper().strip()
        rule = VisaRequirement.objects.filter(
            document_country=doc_country,
            destination_country=dest_country,
        ).first()
        return rule.visa_type if rule else VisaRequirement.VisaType.OTHER

    def save(self, *args, **kwargs):
        self.destination_country = self.destination_country.upper().strip()
        self.visa_type = self._lookup_visa()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Visa check"
        verbose_name_plural = "Visa checks"
        ordering = ("-checked_at",)

    def __str__(self):
        return (
            f"{self.client} · {self.destination_country}: "
            f"{self.get_visa_type_display()}"
        )

class VisaCheckResult(models.Model):
    """One result per (VisaCheck × ClientDocument)."""
    visa_check = models.ForeignKey(
        "VisaCheck", on_delete=models.CASCADE, related_name="results"
    )
    document   = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="+"
    )
    visa_type  = models.CharField(
        max_length=5, choices=VisaRequirement.VisaType.choices
    )
    notes      = models.TextField(blank=True)

    class Meta:
        verbose_name = "Visa check result"
        verbose_name_plural = "Visa check results"
        ordering = ("document__document_country",)

    def __str__(self):
        return ""

    @admin.display(description="Document")
    def doc_type(self):
        app_label  = self.document._meta.app_label
        model_name = self.document._meta.model_name
        url_name   = f"admin:{app_label}_{model_name}_change"
        url        = reverse(url_name, args=[self.document.pk])
        label = self.document.document_type.capitalize()
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(description="Document Country")
    def document_country(self):
        return self.document.document_country

    @admin.display(description="Destination Country")
    def destination_country(self):
        return self.visa_check.destination_country

# Patch VisaCheck.save
old_save = VisaCheck.save

def new_save(self, *args, **kwargs):
    super(VisaCheck, self).save(*args, **kwargs)
    self.results.all().delete()
    for doc in self.client.documents.all():
        doc_country = str(doc.document_country).upper().strip()
        dest_country = str(self.destination_country).upper().strip()
        rule = VisaRequirement.objects.filter(
            document_country=doc_country,
            destination_country=dest_country,
        ).first()
        visa_type = rule.visa_type if rule else VisaRequirement.VisaType.OTHER
        VisaCheckResult.objects.create(
            visa_check=self,
            document=doc,
            visa_type=visa_type,
            notes=getattr(rule, "notes", ""),
        )
VisaCheck.save = new_save 