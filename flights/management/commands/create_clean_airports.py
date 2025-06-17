import csv
import pycountry
from django.core.management.base import BaseCommand
from pathlib import Path

class Command(BaseCommand):
    help = "Create a clean airports dataset with only relevant columns for private jet operations"

    def handle(self, *args, **options):
        input_file = 'flights/fixtures.nosync/airports.csv'
        output_file = 'flights/fixtures.nosync/clean_airports.csv'
        
        # Fields we want to keep
        fieldnames = [
            'name',
            'iata_code',
            'type',
            'city',
            'country_code',
            'country_name',
            'latitude',
            'longitude',
            'elevation_ft'
        ]
        
        # Valid airport types for private jets
        valid_types = {'small_airport', 'medium_airport', 'large_airport'}
        
        cleaned_airports = []
        total_read = 0
        total_kept = 0
        
        # Read and clean data
        with open(input_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                total_read += 1
                
                # Skip invalid types
                if row['type'] not in valid_types:
                    continue
                    
                # Skip if no municipality (city) data
                if not row['municipality']:
                    continue
                
                try:
                    # Get proper country name
                    country = pycountry.countries.get(alpha_2=row['iso_country'])
                    if not country:
                        continue
                        
                    cleaned_airport = {
                        'name': row['name'].strip(),
                        'iata_code': row['iata_code'].strip() if row['iata_code'] else 'N/A',
                        'type': row['type'],
                        'city': row['municipality'].strip(),
                        'country_code': country.alpha_2,
                        'country_name': country.name,
                        'latitude': row['latitude_deg'],
                        'longitude': row['longitude_deg'],
                        'elevation_ft': row['elevation_ft'] or 'N/A'
                    }
                    
                    cleaned_airports.append(cleaned_airport)
                    total_kept += 1
                    
                except Exception as e:
                    continue
        
        # Write cleaned data
        with open(output_file, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(cleaned_airports)
        
        # Remove unnecessary files
        try:
            Path('flights/fixtures/countries.csv').unlink(missing_ok=True)
            Path('flights/fixtures/regions.csv').unlink(missing_ok=True)
            self.stdout.write(self.style.SUCCESS("Removed unnecessary CSV files"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not remove some files: {str(e)}"))
        
        # Print summary
        self.stdout.write(self.style.SUCCESS(
            f"\nData Cleaning Summary:"
            f"\n- Total airports processed: {total_read}"
            f"\n- Airports kept: {total_kept}"
            f"\n- Airports removed: {total_read - total_kept}"
            f"\n- Success rate: {(total_kept/total_read*100):.1f}%"
        ))
        
        # Show sample of cleaned data
        self.stdout.write("\nSample of cleaned data (first 5 entries):")
        for airport in cleaned_airports[:5]:
            self.stdout.write(
                f"- {airport['name']} ({airport['iata_code']}) - "
                f"{airport['city']}, {airport['country_name']} - "
                f"Type: {airport['type']}"
            ) 