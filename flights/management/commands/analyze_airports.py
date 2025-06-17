import csv
from collections import defaultdict
from django.core.management.base import BaseCommand
import pycountry

class Command(BaseCommand):
    help = "Analyze and clean airports data, removing heliports, closed airports, and identifying locations"

    def handle(self, *args, **options):
        airports_file = 'flights/fixtures/airports.csv'
        
        # Counters and storage
        total_rows = 0
        airport_types = defaultdict(int)
        countries = defaultdict(int)
        airports_with_iata = 0
        airports_without_municipality = 0
        
        # Store cleaned airports
        cleaned_airports = []
        
        # Valid airport types (excluding closed, heliports, etc.)
        valid_types = {'small_airport', 'medium_airport', 'large_airport'}
        
        with open(airports_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                total_rows += 1
                
                # Count airport types
                airport_type = row['type']
                airport_types[airport_type] += 1
                
                # Skip invalid types (closed, heliports, etc.)
                if airport_type not in valid_types:
                    continue
                
                # Count countries
                country_code = row['iso_country']
                countries[country_code] += 1
                
                # Check IATA codes
                if row['iata_code']:
                    airports_with_iata += 1
                
                # Check municipality
                if not row['municipality']:
                    airports_without_municipality += 1
                
                # Only keep airports with necessary data
                if (row['type'] in valid_types and 
                    row['municipality'] and 
                    row['iso_country']):
                    
                    # Try to get full country name
                    try:
                        country_name = pycountry.countries.get(alpha_2=row['iso_country']).name
                    except:
                        country_name = row['iso_country']
                    
                    cleaned_airports.append({
                        'name': row['name'],
                        'type': row['type'],
                        'iata': row['iata_code'] or 'N/A',
                        'city': row['municipality'],
                        'country': country_name,
                        'country_code': row['iso_country']
                    })
        
        # Print analysis
        self.stdout.write(self.style.SUCCESS(f"\nTotal rows in original dataset: {total_rows}"))
        
        self.stdout.write("\nAirport types distribution (before cleaning):")
        for type_name, count in airport_types.items():
            status = "✓ KEEP" if type_name in valid_types else "✗ REMOVE"
            self.stdout.write(f"- {type_name}: {count} ({status})")
        
        self.stdout.write(f"\nAirports with IATA codes: {airports_with_iata}")
        self.stdout.write(f"Airports missing city data: {airports_without_municipality}")
        
        # Sort all countries by airport count
        sorted_countries = sorted(countries.items(), key=lambda x: x[1], reverse=True)
        
        self.stdout.write(self.style.SUCCESS(f"\nTotal number of countries with airports: {len(countries)}"))
        
        self.stdout.write("\nAll countries by airport count (active airports only):")
        for country_code, count in sorted_countries:
            try:
                country_name = pycountry.countries.get(alpha_2=country_code).name
                self.stdout.write(f"- {country_name} ({country_code}): {count}")
            except:
                self.stdout.write(f"- Unknown ({country_code}): {count}")
        
        # Group countries by continent/region
        continents = defaultdict(int)
        for country_code, count in countries.items():
            try:
                country = pycountry.countries.get(alpha_2=country_code)
                # This is a simplified grouping - you might want to use a proper continent mapping
                region = country.name.split(',')[0]  # Simple region extraction
                continents[region] += count
            except:
                continents['Unknown'] += count
        
        self.stdout.write("\nRegional Distribution:")
        for region, count in sorted(continents.items(), key=lambda x: x[1], reverse=True):
            self.stdout.write(f"- {region}: {count}")
        
        total_removed = total_rows - len(cleaned_airports)
        self.stdout.write(self.style.SUCCESS(
            f"\nFinal Statistics:"
            f"\n- Original airport count: {total_rows}"
            f"\n- Airports removed: {total_removed}"
            f"\n- Final cleaned airports count: {len(cleaned_airports)}"
            f"\n- Total countries: {len(countries)}"
            f"\n- Percentage kept: {(len(cleaned_airports)/total_rows*100):.1f}%"
        )) 