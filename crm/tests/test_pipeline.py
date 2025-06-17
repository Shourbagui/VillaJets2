import unittest
from datetime import date
from unittest.mock import MagicMock, patch

# Assuming the refactored functions are now in crm.helpers.doc_extract
# We might need to adjust the import path based on how the files are structured
# For now, assuming crm.helpers.doc_extract is correct
from crm.helpers.doc_extract import (
    _find_issued_country,
    _find_number,
    _find_expiration_date,
    _pipeline_extract,
    _parse_date, # Keep for testing parse_date directly
    _normalize_mrz_date, # Keep for testing normalize_mrz_date directly
    # Import pattern dictionaries if needed for direct testing of patterns
    NUMBER_PATTERNS,
    EXPIRY_PATTERNS,
    EU_CODES
)

class TestExtractionPipeline(unittest.TestCase):

    # Test cases for _parse_date (can reuse from old test_expiry if applicable)
    def test_parse_date_dmy(self):
        self.assertEqual(_parse_date("15/03/2025"), date(2025, 3, 15))
        self.assertEqual(_parse_date("01.11.2028"), date(2028, 11, 1))
        self.assertEqual(_parse_date("25-12-2030"), date(2030, 12, 25))

    def test_parse_date_mdy(self):
        # dateparser defaults to DMY, but test some MDY if it might be encountered
        # Depending on strictness, we might want to disallow ambiguous formats
        pass # Add MDY tests if necessary

    def test_parse_date_ymd(self):
         self.assertEqual(_parse_date("2025-03-15"), date(2025, 3, 15))

    def test_parse_date_2digit_year_pivot(self):
        # Assuming current year makes 42 -> 1942 and 41 -> 2041
        # This is dependent on the specific pivoting logic in _parse_date
        # Let's test with dates that fall into different pivot ranges based on the current year
        current_year = date.today().year
        pivot_threshold = (current_year % 100) + 20 # Example pivot threshold from the code

        # Test a year below the threshold (should be 20xx)
        year_20xx = pivot_threshold
        date_str_20xx = f"01/01/{year_20xx:02d}"
        expected_date_20xx = date(2000 + year_20xx, 1, 1)
        self.assertEqual(_parse_date(date_str_20xx), expected_date_20xx, f"Failed 20xx pivot for {date_str_20xx}")

        # Test a year above the threshold (should be 19xx)
        year_19xx = pivot_threshold + 1
        date_str_19xx = f"01/01/{year_19xx:02d}"
        expected_date_19xx = date(1900 + year_19xx, 1, 1)
        self.assertEqual(_parse_date(date_str_19xx), expected_date_19xx, f"Failed 19xx pivot for {date_str_19xx}")

        # Test years around the standard ICAO pivot (41/42)
        self.assertEqual(_parse_date("01/01/41"), date(2041, 1, 1))
        self.assertEqual(_parse_date("01/01/42"), date(1942, 1, 1))

    def test_parse_date_invalid(self):
        self.assertIsNone(_parse_date("not a date"))
        self.assertIsNone(_parse_date("99/99/9999")) # Invalid date values

    # Test cases for _normalize_mrz_date (can reuse from old test_expiry if applicable)
    def test_normalize_mrz_date_valid(self):
        self.assertEqual(_normalize_mrz_date("880118"), date(1988, 1, 18))
        self.assertEqual(_normalize_mrz_date("050118"), date(2005, 1, 18))
        self.assertEqual(_normalize_mrz_date("951231"), date(1995, 12, 31))
        self.assertEqual(_normalize_mrz_date("000101"), date(2000, 1, 1))

    def test_normalize_mrz_date_invalid(self):
        self.assertIsNone(_normalize_mrz_date("123")) # Too short
        self.assertIsNone(_normalize_mrz_date("1234567")) # Too long
        self.assertIsNone(_normalize_mrz_date("ABCDEF")) # Non-numeric
        self.assertIsNone(_normalize_mrz_date("999999")) # Invalid date values

    # Test cases for the full pipeline with specific country examples

    @patch('crm.helpers.doc_extract._get_text_and_mrz') # Mock the text/mrz extraction
    def test_pipeline_spanish_dni(self, mock_get_text_and_mrz):
        # Simulate text and no MRZ for a Spanish DNI
        spanish_dni_text = """
REINO DE ESPAÑA
DOCUMENTO NACIONAL DE IDENTIDAD
N° 12345678Z
APELLIDOS GARCIA
NOMBRE MARIA
NACIONALIDAD ESPAÑOLA
VALIDEZ 01/01/2030
"""
        mock_get_text_and_mrz.return_value = (spanish_dni_text, None)

        extracted_data = _pipeline_extract(b"dummy_content", "id_card")

        self.assertIsNotNone(extracted_data)
        self.assertEqual(extracted_data.get("issued_country"), "ESP")
        self.assertEqual(extracted_data.get("number"), "12345678Z")
        self.assertEqual(extracted_data.get("expiration_date"), date(2030, 1, 1))

    @patch('crm.helpers.doc_extract._get_text_and_mrz') # Mock the text/mrz extraction
    def test_pipeline_mexican_passport(self, mock_get_text_and_mrz):
        # Simulate text and MRZ data for a Mexican passport
        mexican_passport_text = """
PASAPORTE
ESTADOS UNIDOS MEXICANOS
No. G12345678
APELLIDOS LOPEZ
NOMBRE JUAN
NACIONALIDAD MEXICANA
FECHA DE VIGENCIA 31/12/2028
"""
        # Simulate MRZ data, even if some fields are None initially
        simulated_mrz = {"number": "G12345678", "issued_country": "MEX", "expiration_date": date(2028, 12, 31)} # Simulate successful MRZ parse
        mock_get_text_and_mrz.return_value = (mexican_passport_text, simulated_mrz)

        extracted_data = _pipeline_extract(b"dummy_content", "passport")

        self.assertIsNotNone(extracted_data)
        self.assertEqual(extracted_data.get("issued_country"), "MEX")
        self.assertEqual(extracted_data.get("number"), "G12345678")
        # Expiry date should ideally come from MRZ if valid, otherwise text
        self.assertEqual(extracted_data.get("expiration_date"), date(2028, 12, 31))

    @patch('crm.helpers.doc_extract._get_text_and_mrz') # Mock the text/mrz extraction
    def test_pipeline_us_visa(self, mock_get_text_and_mrz):
        # Simulate text for a US visa (often minimal MRZ or different format)
        us_visa_text = """
VISA
UNITED STATES OF AMERICA
VISA NUMBER 123456789
EXPIRATION DATE 05/20/2027
"""
        mock_get_text_and_mrz.return_value = (us_visa_text, None)

        extracted_data = _pipeline_extract(b"dummy_content", "visa")

        self.assertIsNotNone(extracted_data)
        self.assertEqual(extracted_data.get("issued_country"), "USA") # Assuming country extraction works from text
        self.assertEqual(extracted_data.get("number"), "123456789") # Assuming number pattern works
        self.assertEqual(extracted_data.get("expiration_date"), date(2027, 5, 20)) # Assuming expiry pattern works

    @patch('crm.helpers.doc_extract._get_text_and_mrz') # Mock the text/mrz extraction
    def test_pipeline_german_id_eu_fallback(self, mock_get_text_and_mrz):
        # Simulate text for a German ID card (should hit EU generic fallback)
        german_id_text = """
BUNDESREPUBLIK DEUTSCHLAND
IDENTITÄTSKARTE
Nummer C01234567
NATIONALITÄT DEUTSCH
Gültig bis 10.10.2029
"""
        mock_get_text_and_mrz.return_value = (german_id_text, None)

        extracted_data = _pipeline_extract(b"dummy_content", "id_card")

        self.assertIsNotNone(extracted_data)
        self.assertEqual(extracted_data.get("issued_country"), "DEU") # Should find country
        self.assertEqual(extracted_data.get("number"), "C01234567") # Should match EU generic pattern
        self.assertEqual(extracted_data.get("expiration_date"), date(2029, 10, 10)) # Should match EU expiry pattern

    @patch('crm.helpers.doc_extract._get_text_and_mrz') # Mock the text/mrz extraction
    def test_pipeline_generic_fallback(self, mock_get_text_and_mrz):
        # Simulate text for an unknown country document, should hit generic fallback
        generic_text = """
Some Document
Doc No: ABC123XYZ789
Issued By: UNKNOWN COUNTRY
Expiry: 11/20/2026
"""
        mock_get_text_and_mrz.return_value = (generic_text, None)

        extracted_data = _pipeline_extract(b"dummy_content", "other")

        self.assertIsNotNone(extracted_data)
        self.assertIsNone(extracted_data.get("issued_country")) # Should not find a specific country
        self.assertEqual(extracted_data.get("number"), "ABC123XYZ789") # Should match generic number pattern
        self.assertEqual(extracted_data.get("expiration_date"), date(2026, 11, 20)) # Should match generic expiry pattern


# Keep existing tests for helper functions if they were in separate files before
# class TestParseDate(...):
#    ...

# class TestNormalizeMrzDate(...):
#    ...