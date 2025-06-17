import factory
from factory import fuzzy
from faker import Faker
from django.utils import timezone
from datetime import timedelta
from flights.models import (
    FlightRequest, PlaneRequirement, Flight, FlightStatus,
    FlightChecklist
)
from crm.models import (CustomerFeedback, CustomerFeedbackType)
from crm.factories import ClientFactory  # reuse CRM factories

fake = Faker()


class FlightRequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FlightRequest

    client = factory.SubFactory(ClientFactory)
    passengers = fuzzy.FuzzyInteger(1, 12)
    departure_date = factory.LazyFunction(lambda: timezone.now().date() + timedelta(days=3))
    return_date = factory.LazyAttribute(lambda o: o.departure_date + timedelta(days=7))
    origin = factory.Faker("city")
    destinations = factory.LazyFunction(lambda: [fake.city(), fake.city()])
    notes = factory.Faker("paragraph")


class PlaneRequirementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PlaneRequirement

    flight_request = factory.SubFactory(FlightRequestFactory)
    model = factory.Faker("word")
    seat_count = fuzzy.FuzzyInteger(4, 12)
    other_requirements = factory.Faker("sentence")


class FlightFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Flight

    flight_request = factory.SubFactory(FlightRequestFactory)
    status = fuzzy.FuzzyChoice(FlightStatus.values)
    scheduled_departure = factory.LazyFunction(lambda: timezone.now() + timedelta(days=5))
    scheduled_return = factory.LazyAttribute(lambda o: o.scheduled_departure + timedelta(hours=4))


class FlightChecklistFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FlightChecklist

    flight = factory.SubFactory(FlightFactory)
    airports_ready = factory.Faker("boolean")
    itinerary_ready = factory.Faker("boolean")
    crew_ready = factory.Faker("boolean")
    customs_ready = factory.Faker("boolean")
    notes = factory.Faker("sentence")
    completed_at = factory.LazyFunction(timezone.now)


class CustomerFeedbackFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomerFeedback

    flight = factory.SubFactory(FlightFactory)
    feedback_type = fuzzy.FuzzyChoice(CustomerFeedbackType.values)
    content = factory.Faker("paragraph")
    created_at = factory.LazyFunction(timezone.now)
