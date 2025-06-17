import factory
from factory import fuzzy
from faker import Faker
from crm.models import Client, Document, DocumentTypes, Lead, LeadStatus, FlightQuote, FlightTypes

fake = Faker()


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    name = factory.Faker("name")
    email = factory.Faker("email")
    phone = factory.Faker("phone_number")


class DocumentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Document

    client = factory.SubFactory(ClientFactory)
    document_type = fuzzy.FuzzyChoice(DocumentTypes.values)
    number = factory.Faker("bothify", text="???######")
    document_country = factory.Faker("country")
    expiration_date = factory.Faker("future_date")
    file = None  # or use factory.django.FileField if testing upload


class LeadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Lead

    client = factory.SubFactory(ClientFactory)
    status = fuzzy.FuzzyChoice(LeadStatus.values)
    notes = factory.Faker("paragraph")


class FlightQuoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FlightQuote

    client = factory.SubFactory(ClientFactory)
    flight_type = fuzzy.FuzzyChoice(FlightTypes.values)
    waiting_area_required = factory.Faker("boolean")
    special_requirements = factory.Faker("paragraph")
