from django.db import models
from crm.models import Client
from django.contrib.postgres.fields import ArrayField

class FlightRequest(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    passengers = models.PositiveIntegerField()
    departure_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    origin = models.CharField(max_length=255)
    destinations = ArrayField(
        models.CharField(max_length=255),
        help_text="List of one or more destination airports/locations"
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

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
    flight_request = models.OneToOneField(FlightRequest, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=FlightStatus.choices)
    scheduled_departure = models.DateTimeField()
    scheduled_return = models.DateTimeField(null=True, blank=True)

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