from django.db import models
from crm.models import Client
from django.contrib.postgres.fields import ArrayField
from django.core.cache import cache
from django_quill.fields import QuillField
from django.contrib import admin
from unfold.admin import ModelAdmin


class Country(models.Model):
    code = models.CharField(max_length=3, unique=True)  # ISO3
    name = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.code} - {self.name}"

class City(models.Model):
    name = models.CharField(max_length=100)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="cities")
    def __str__(self):
        return f"{self.name}, {self.country.code}"

def get_airports_dict():
    airports_dict = cache.get('airports_dict')
    if airports_dict is None:
        cache_obj = AirportsDataCache.objects.first()
        if cache_obj:
            airports_dict = cache_obj.data
            cache.set('airports_dict', airports_dict, timeout=60*60*24)  # 24 hours
    return airports_dict

def get_country_choices():
    airports_dict = get_airports_dict()
    if not airports_dict:
        return []
    return [(c['name'], c['name']) for c in airports_dict['countries'].values()]

def get_city_choices(country_name):
    airports_dict = get_airports_dict()
    if not airports_dict:
        return []
    country = airports_dict['countries'].get(country_name)
    if not country:
        return []
    return [(city['name'], city['name']) for city in country['cities'].values()]

class Airport(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    iata_code = models.CharField(max_length=3, null=True, blank=True, db_index=True)
    type = models.CharField(max_length=50, null=True, blank=True)
    city = models.CharField(max_length=200, null=True, blank=True, db_index=True)
    country_code = models.CharField(max_length=2, null=True, blank=True)
    country_name = models.CharField(max_length=200, null=True, blank=True, db_index=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    elevation_ft = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        unique_together = ['name', 'city', 'country_code']
        indexes = [
            models.Index(fields=['country_name', 'city']),
            models.Index(fields=['city', 'name']),
        ]

    def __str__(self):
        if self.iata_code:
            return f"{self.iata_code} - {self.name} ({self.city}, {self.country_name})"
        return f"{self.name} ({self.city}, {self.country_name})"

class FlightRequest(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    passengers = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Flight Request #{self.pk} - {self.client.name}"

    @property
    def trip_start(self):
        first_leg = self.legs.order_by('departure_date').first()
        return first_leg.departure_date if first_leg else None

    class Meta:
        verbose_name = "Flight Request"
        verbose_name_plural = "Flight Requests"
        indexes = [
            # Remove index on departure_date, return_date
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

class PlaneRequirement(models.Model):
    flight_request = models.OneToOneField(FlightRequest, on_delete=models.CASCADE)
    model = models.CharField(max_length=100, blank=True)
    seat_count = models.PositiveIntegerField()
    other_requirements = models.TextField(blank=True)

class FlightStatus(models.TextChoices):
    REQUESTED = "requested"
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    PREPARED = "prepared"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class Flight(models.Model):
    flight_request = models.ForeignKey(FlightRequest, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=FlightStatus.choices)
    scheduled_departure = models.DateTimeField()
    scheduled_return = models.DateTimeField(null=True, blank=True)
    origin = models.CharField(max_length=255,null=True)
    destination = models.CharField(max_length=255,null=True)
    order = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"#{self.pk} - {self.status.title()} - {self.scheduled_departure.date()} - {self.scheduled_departure.date()}"


class FlightChecklist(models.Model):
    flight = models.OneToOneField(Flight, on_delete=models.CASCADE)
    airports_ready = models.BooleanField(default=False)
    itinerary_ready = models.BooleanField(default=False)
    crew_ready = models.BooleanField(default=False)
    customs_ready = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

class AirportsDataCache(models.Model):
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

class FlightLeg(models.Model):
    flight_request = models.ForeignKey(FlightRequest, on_delete=models.CASCADE, related_name='legs')
    origin_airport = models.ForeignKey(Airport, on_delete=models.CASCADE, related_name='+')
    destination_airport = models.ForeignKey(Airport, on_delete=models.CASCADE, related_name='+')
    departure_date = models.DateTimeField()
    passengers = models.PositiveIntegerField()

    def clean(self):
        # No strict validation: allow passenger count to change between legs
        pass

    class Meta:
        ordering = ['departure_date']

    def __str__(self):
        return f"{self.origin_airport} → {self.destination_airport} on {self.departure_date.strftime('%Y-%m-%d %H:%M')} ({self.passengers} pax)"
