import csv
from django.core.management.base import BaseCommand
from flights.models import Country, City, Airport
from collections import defaultdict
import pycountry

def iso2_to_iso3(iso2):
    try:
        return pycountry.countries.get(alpha_2=iso2).alpha_3
    except Exception:
        return None

class Command(BaseCommand):
    help = "Import countries, cities, and airports from OurAirports data. Only cities with airports will be created."

    def add_arguments(self, parser):
        parser.add_argument('--countries', type=str, required=True, help='Path to countries.csv')
        parser.add_argument('--airports', type=str, required=True, help='Path to airports.csv')

    def handle(self, *args, **options):
        self.import_countries(options['countries'])
        self.import_airports_and_cities(options['airports'])
        self.cleanup_cities()

    def import_countries(self, path):
        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                iso2 = row.get('code')
                iso3 = iso2_to_iso3(iso2)
                name = row.get('name')
                if iso3 and name:
                    Country.objects.update_or_create(
                        code=iso3,
                        defaults={'name': name}
                    )
        self.stdout.write(self.style.SUCCESS('Countries imported.'))

    def import_airports_and_cities(self, path):
        city_cache = {}  # (city_name, country_code) -> City
        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                iso2 = row.get('iso_country')
                iso3 = iso2_to_iso3(iso2)
                city_name = row.get('municipality')
                iata_code = row.get('iata_code')
                name = row.get('name')
                if not (iso3 and city_name and iata_code and name):
                    continue
                country = Country.objects.filter(code=iso3).first()
                if not country:
                    continue
                city_key = (city_name.strip(), country.code)
                if city_key not in city_cache:
                    city, _ = City.objects.get_or_create(
                        name=city_name.strip(),
                        country=country
                    )
                    city_cache[city_key] = city
                else:
                    city = city_cache[city_key]
                Airport.objects.update_or_create(
                    iata_code=iata_code,
                    defaults={
                        'name': name.strip(),
                        'city': city,
                        'country': country
                    }
                )
        self.stdout.write(self.style.SUCCESS('Airports and cities imported.'))

    def cleanup_cities(self):
        # Remove cities with no airports
        removed, _ = City.objects.filter(airports__isnull=True).delete()
        self.stdout.write(self.style.SUCCESS(f'Removed {removed} cities with no airports.')) 