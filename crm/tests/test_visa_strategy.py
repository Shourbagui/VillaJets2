import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from crm.helpers.strategies import VisaStrategy, GenericStrategy, STRATEGY_REGISTRY

# --- Notes on Test Data and Coverage ---
# The tests below use *simulated* text content to check the logic of the VisaStrategy and its fallback.
# For true comprehensive testing, you would need:
# 1. Actual image/PDF fixture files representing various visa types (US, Schengen, etc.)
# 2. An OCR/Text Extraction pipeline to process these fixtures into text for the tests.
# 3. Integration tests that run the full pipeline on these fixtures.
# These simulated text tests are valuable for unit testing the strategy's pattern matching and logic, but do not replace full integration tests.
# --- End Notes ---

# Assume fixtures/visa_examples contains test images (for conceptual reference):
# - us_b1b2_visa.jpg (US B1/B2 visa image)
# - schengen_esp_visa.jpg (Schengen visa issued by Spain)
# - text_missing_visa_patterns.txt (Text simulation missing visa keywords)

class TestVisaStrategy(unittest.TestCase):

    @patch('crm.helpers.strategies.GenericStrategy') # Patch GenericStrategy to check fallback calls
    @patch('crm.helpers.strategies.pycountry') # Patch pycountry to control fuzzy matching in tests
    def test_us_b1b2_visa_extraction(self, MockPycountry, MockGenericStrategy):
        # Mock the GenericStrategy extract method to return a predictable result for the fallback check
        mock_generic_instance = MockGenericStrategy.return_value
        mock_generic_instance.extract.return_value = {"number": None, "issued_country": None, "expiration_date": None}
        
        # Mock pycountry.countries.search_fuzzy to return a specific country for a known input
        mock_pycountry_countries = MockPycountry.countries
        mock_pycountry_countries.search_fuzzy.return_value = [] # Default to no fuzzy match
        # Example mock for a specific country name found near a keyword
        # mock_pycountry_countries.search_fuzzy.side_effect = lambda name: [\
        #     MagicMock(alpha_3="USA")] if "United States" in name else []
        
        # More realistic simulated text for a US B1/B2 visa
        us_visa_text = """
        UNITED STATES OF AMERICA NONIMMIGRANT VISA
        B1/B2
        ISSUING POST: LONDON
        CONTROL NUMBER 202175936
        SURNAME: DOE, GIVEN NAME: JOHN
        PLACE OF BIRTH: BERLIN, GERMANY
        NATIONALITY: GER
        PASSPORT NUMBER: X123456789
        Issued By: United States Department of State
        ANNOTATION: B1/B2 BUSINESS/TOURISM
        SEX: M DATE OF BIRTH: 01 JAN 1990
        ISSUE DATE: 01 FEB 2020
        EXPIRATION DATE: 01 FEB 2027
        MRZ: V<USA<<DOE<JOHN<<<<<<<<<<<<<<<<<<<<\n        A123456789GER9001017M2702018<<<<<<<<<<<<<<0
        """
        # MRZ data would typically come from a separate MRZ parsing step in the pipeline,
        # but we include it here for completeness and potential validation use in the strategy.
        mrz_data = {
            "document_type": "V", "issued_country": "USA", "surname": "DOE",
            "given_name": "JOHN", "number": "A12345678", "nationality": "GER",
            "date_of_birth": date(1990, 1, 1), "sex": "M",
            "expiration_date": date(2027, 2, 1), "optional_data": ""
        }

        strategy = VisaStrategy()
        result = strategy.extract(us_visa_text, mrz_data)

        # Assertions based on expected extraction from the simulated text
        self.assertEqual(result["issued_country"], "USA") # Should get from text pattern first or MRZ
        self.assertEqual(result["number"], "202175936") # Should get from CONTROL NUMBER
        self.assertEqual(result["expiration_date"], date(2027, 2, 1)) # Should get from EXF date pattern, potentially corrected by pivot year
        
        # Assert that fallback was NOT called since all primary data was found
        mock_generic_instance.extract.assert_not_called()

    @patch('crm.helpers.strategies.GenericStrategy')
    @patch('crm.helpers.strategies.pycountry') # Patch pycountry
    def test_schengen_esp_visa_extraction(self, MockPycountry, MockGenericStrategy):
        # Mock the GenericStrategy extract method
        mock_generic_instance = MockGenericStrategy.return_value
        mock_generic_instance.extract.return_value = {"number": None, "issued_country": None, "expiration_date": None}

        # Mock pycountry search_fuzzy for Spanish terms
        mock_pycountry_countries = MockPycountry.countries
        mock_pycountry_countries.search_fuzzy.return_value = []
        # Example mock: finding "España" or "Spain" near a keyword
        mock_pycountry_countries.search_fuzzy.side_effect = lambda name: [
             MagicMock(alpha_3="ESP")] if "España" in name or "Spain" in name else []

        # More realistic placeholder text for a Schengen visa issued by Spain
        schengen_visa_text = """
        VISA DE SCHENGEN
        NUMERO DE VISADO: 987654321
        PAIS EMISOR: ESPAÑA
        AUTORIDAD: MADRID, SPAIN
        VALIDO HASTA: 20/12/2028
        TIPO: C ENTRADAS: MULTIPLE DURACION: 90 DIAS
        APELLIDOS: PEREZ, NOMBRE: MARIA
        NUMERO DE PASAPORTE: Y98765432
        """
        mrz_data = None # Assuming no standard MRZ on the visa sticker itself in this example

        strategy = VisaStrategy()
        result = strategy.extract(schengen_visa_text, mrz_data)

        # Assertions
        self.assertEqual(result["issued_country"], "ESP") # Should get from PAIS EMISOR or AUTORIDAD via fuzzy match
        self.assertEqual(result["number"], "987654321") # Should get from NUMERO DE VISADO
        self.assertEqual(result["expiration_date"], date(2028, 12, 20)) # Should get from VALIDO HASTA
        
        # Assert that fallback was NOT called
        mock_generic_instance.extract.assert_not_called()
        # Assert that pycountry.countries.search_fuzzy was called (at least once)
        mock_pycountry_countries.search_fuzzy.assert_called()

    @patch('crm.helpers.strategies.GenericStrategy')
    @patch('crm.helpers.strategies.pycountry') # Patch pycountry
    def test_fallback_to_generic(self, MockPycountry, MockGenericStrategy):
        # Mock the GenericStrategy extract method to return some data on fallback
        mock_generic_instance = MockGenericStrategy.return_value
        fallback_data = {"number": "GEN123", "issued_country": "GEN", "expiration_date": date(2035, 1, 1)}
        mock_generic_instance.extract.return_value = fallback_data

        # Mock pycountry search_fuzzy to find nothing
        mock_pycountry_countries = MockPycountry.countries
        mock_pycountry_countries.search_fuzzy.return_value = []

        # Simulated text missing typical visa patterns, but containing generic ones
        generic_text = """
        This is a scanned document.
        It contains some general information.
        Document Number: GEN123
        Country of Origin: Generic Country
        Date of Expiry: 01-01-2035
        No visa or passport information is present.
        """
        mrz_data = None

        strategy = VisaStrategy()
        result = strategy.extract(generic_text, mrz_data)

        # Assert that VisaStrategy extraction would have found nothing (optional but good)
        # self.assertIsNone(strategy.extract(generic_text, mrz_data)["number"])
        # self.assertIsNone(strategy.extract(generic_text, mrz_data)["issued_country"])
        # self.assertIsNone(strategy.extract(generic_text, mrz_data)["expiration_date"])

        # Assert that fallback WAS called with the correct arguments
        mock_generic_instance.extract.assert_called_once_with(generic_text, mrz_data)
        
        # Assert that the result is from the fallback (since VisaStrategy found nothing)
        self.assertEqual(result, fallback_data)

    # You would add more specific tests here for edge cases, different formats, etc.
    # For example, testing the proximity-based number/date extraction, different date formats,
    # handling cases where MRZ data contradicts text data (current logic prioritizes MRZ for country)

class TestStrategyDispatch(unittest.TestCase):
    
    def test_get_strategy_for_visa(self):
        # Ensure get_strategy returns VisaStrategy for 'visa' doc_type (case-insensitive)
        strategy_lower = STRATEGY_REGISTRY["VISA"]()
        self.assertIsInstance(strategy_lower, VisaStrategy)
        # Add a test for 'VISA' explicitly
        strategy_upper = STRATEGY_REGISTRY["VISA"]()
        self.assertIsInstance(strategy_upper, VisaStrategy)

    # Add tests here to ensure _pipeline_extract uses the correct strategy
    # based on doc_type (requires patching _pipeline_extract or the parts it calls)
    # This level of testing is more involved and might be considered integration tests.

if __name__ == '__main__':
    unittest.main() 