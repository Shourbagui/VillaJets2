import csv
from django.core.management.base import BaseCommand
from flights.models import Airport

class Command(BaseCommand):
    help = "Import airports from the clean_airports.csv file"

    def handle(self, *args, **options):
        csv_file = 'flights/fixtures.nosync/clean_airports.csv'
        total_processed = 0
        total_imported = 0
        total_updated = 0
        
        # Clear existing airports
        Airport.objects.all().delete()
        self.stdout.write("Cleared existing airports")
        
        with open(csv_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                total_processed += 1
                try:
                    # Try to find an existing airport with the same name, city, and country_code
                    airport, created = Airport.objects.get_or_create(
                        name=row['name'],
                        city=row['city'],
                        country_code=row['country_code'],
                        defaults={
                            'iata_code': row['iata_code'] if row['iata_code'] != 'N/A' else None,
                            'type': row['type'],
                            'country_name': row['country_name'],
                            'latitude': float(row['latitude']),
                            'longitude': float(row['longitude']),
                            'elevation_ft': row['elevation_ft'] if row['elevation_ft'] != 'N/A' else None
                        }
                    )
                    
                    if created:
                        total_imported += 1
                    else:
                        # Update the existing airport with new data
                        airport.iata_code = row['iata_code'] if row['iata_code'] != 'N/A' else None
                        airport.type = row['type']
                        airport.country_name = row['country_name']
                        airport.latitude = float(row['latitude'])
                        airport.longitude = float(row['longitude'])
                        airport.elevation_ft = row['elevation_ft'] if row['elevation_ft'] != 'N/A' else None
                        airport.save()
                        total_updated += 1
                        
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Error importing airport {row['name']}: {str(e)}"))
        
        self.stdout.write(self.style.SUCCESS(
            f"\nImport Summary:"
            f"\n- Total processed: {total_processed}"
            f"\n- Successfully imported: {total_imported}"
            f"\n- Updated: {total_updated}"
            f"\n- Failed: {total_processed - total_imported - total_updated}"
        ))
        
        # Print some stats
        countries = Airport.objects.values('country_name').distinct().count()
        cities = Airport.objects.values('city').distinct().count()
        
        self.stdout.write(self.style.SUCCESS(
            f"\nDatabase Statistics:"
            f"\n- Total airports: {Airport.objects.count()}"
            f"\n- Unique countries: {countries}"
            f"\n- Unique cities: {cities}"
        )) 