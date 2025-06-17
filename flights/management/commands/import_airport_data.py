import csv
import pycountry
from django.core.management.base import BaseCommand
from flights.models import Country, City, Airport

def iso2_to_iso3(iso2):
    try:
        return pycountry.countries.get(alpha_2=iso2).alpha_3
    except Exception:
        return None

class Command(BaseCommand):
    help = "Import countries, cities, and airports from CSV files (OurAirports format, with ISO2 to ISO3 mapping)"

    def add_arguments(self, parser):
        parser.add_argument('--countries', type=str, help='Path to countries.csv')
        parser.add_argument('--cities', type=str, help='Path to regions.csv')
        parser.add_argument('--airports', type=str, help='Path to airports.csv')

    def handle(self, *args, **options):
        if options['countries']:
            self.import_countries(options['countries'])
        if options['cities']:
            self.import_cities(options['cities'])
        if options['airports']:
            self.import_airports(options['airports'])

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

    def import_cities(self, path):
        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                iso2 = row.get('iso_country')
                iso3 = iso2_to_iso3(iso2)
                name = row.get('name')
                if iso3 and name:
                    country = Country.objects.filter(code=iso3).first()
                    if country:
                        City.objects.update_or_create(
                            name=name,
                            country=country
                        )
        self.stdout.write(self.style.SUCCESS('Cities imported.'))

    def import_airports(self, path):
        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                iso2 = row.get('iso_country')
                iso3 = iso2_to_iso3(iso2)
                city_name = row.get('municipality') or row.get('city')
                iata_code = row.get('iata_code')
                name = row.get('name')
                if iso3 and city_name and iata_code and name:
                    country = Country.objects.filter(code=iso3).first()
                    city = City.objects.filter(name=city_name, country=country).first()
                    if country and city:
                        Airport.objects.update_or_create(
                            iata_code=iata_code,
                            defaults={
                                'name': name,
                                'city': city,
                                'country': country
                            }
                        )
        self.stdout.write(self.style.SUCCESS('Airports imported.')) 