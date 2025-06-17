from django.db import models

class Client(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
class DocumentTypes(models.TextChoices):
    PASSPORT = "passport"
    VISA = "visa"
    ID_CARD = "id_card"

class Document(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=10, choices=DocumentTypes.choices)
    number = models.CharField(max_length=100)
    issued_country = models.CharField(max_length=100)
    expiration_date = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to="documents/", null=True, blank=True)

    def __str__(self):
        return f"{self.document_type} for {self.client.name}"


class LeadStatus(models.TextChoices):
    APPROACH = "approach"
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    LOST = "lost"
    CLOSED = "closed"

class Lead(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=LeadStatus.choices)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Lead for {self.client.name}"
    
class FlightTypes(models.TextChoices):
    INTRATERRITORY = "intraterritory"
    INTERNATIONAL = "international"


class FlightQuote(models.Model):
    client = models.OneToOneField(Client, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    flight_type = models.CharField(max_length=50, choices=FlightTypes.choices)
    waiting_area_required = models.BooleanField(default=False)
    special_requirements = models.TextField(blank=True)

class CustomerFeedbackType(models.TextChoices):
    CHANGE_REQUEST = "change_request"
    COMPLAINT = "complaint"
    SATISFACTION = "satisfaction"

class CustomerFeedback(models.Model):
    from flights.models import Flight
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE)
    feedback_type = models.CharField(max_length=15, choices=models.TextChoices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
