import csv
from django.core.management.base import BaseCommand
from flights.models import AirportsDataCache
from pathlib import Path

class Command(BaseCommand):
    help = "Build a nested airports dictionary from clean_airports.csv and store it in AirportsDataCache."

    def handle(self, *args, **options):
        input_file = Path('flights/fixtures.nosync/clean_airports.csv')
        if not input_file.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {input_file}"))
            return

        airports_dict = {"countries": {}}
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                country_name = row['country_name']
                country_code = row['country_code']
                city_name = row['city']
                airport_name = row['name']
                iata_code = row['iata_code']

                if not country_name or not city_name or not airport_name:
                    continue

                countries = airports_dict["countries"]
                if country_name not in countries:
                    countries[country_name] = {
                        "name": country_name,
                        "code": country_code,
                        "cities": {}
                    }
                cities = countries[country_name]["cities"]
                if city_name not in cities:
                    cities[city_name] = {
                        "name": city_name,
                        "airports": []
                    }
                cities[city_name]["airports"].append({
                    "name": airport_name,
                    "iata_code": iata_code
                })

        AirportsDataCache.objects.all().delete()  # Only keep one
        AirportsDataCache.objects.create(data=airports_dict)
        self.stdout.write(self.style.SUCCESS("Airports dictionary built and stored in AirportsDataCache.")) 