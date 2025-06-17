from abc import ABC, abstractmethod
import re
import logging
from datetime import date, timedelta
import dateparser
import pycountry # Import pycountry for potential fuzzy matching
from typing import Optional, Dict, Union, List, Tuple
from dataclasses import dataclass
from enum import Enum, auto
import tempfile
import filetype
import unicodedata
import cv2
from passporteye import read_mrz
from pdf2image import convert_from_path
from PIL import Image
import os

logger = logging.getLogger(__name__)

class DocumentExtractionError(Exception):
    """Base exception for document extraction errors."""
    pass

class ValidationError(DocumentExtractionError):
    """Raised when document data validation fails."""
    pass

class MRZError(DocumentExtractionError):
    """Raised when there are issues with MRZ data."""
    pass

class DateParsingError(DocumentExtractionError):
    """Raised when date parsing fails."""
    pass

class CountryCodeError(DocumentExtractionError):
    """Raised when country code validation fails."""
    pass

class NumberValidationError(DocumentExtractionError):
    """Raised when document number validation fails."""
    pass

@dataclass
class ExtractionResult:
    """Result of document data extraction."""
    number: Optional[str]
    issued_country: Optional[str]
    expiration_date: Optional[date]
    confidence: float
    validation_errors: List[str]
    warnings: List[str]

    def is_complete(self) -> bool:
        """Check if all required fields are present."""
        return all([
            self.number is not None,
            self.issued_country is not None,
            self.expiration_date is not None
        ])

    def __str__(self) -> str:
        return f"ExtractionResult(number={self.number}, issued_country={self.issued_country}, expiration_date={self.expiration_date}, confidence={self.confidence})"

    def is_valid(self) -> bool:
        """Check if the extraction result is valid."""
        return len(self.validation_errors) == 0

    def add_error(self, error: str):
        """Add a validation error."""
        self.validation_errors.append(error)
        self.confidence = max(0.0, self.confidence - 0.2)  # Reduce confidence for each error

    def add_warning(self, warning: str):
        """Add a warning."""
        self.warnings.append(warning)
        self.confidence = max(0.0, self.confidence - 0.1)  # Reduce confidence less for warnings

@dataclass
class MRZData:
    """Standardized container for parsed MRZ data."""
    document_type: Optional[str] = None
    country_code: Optional[str] = None # Using country_code for consistency with MRZ specs
    number: Optional[str] = None
    expiration_date: Optional[date] = None
    expiration_date_str: Optional[str] = None # Keep original string for reference/re-parsing
    # Add other relevant MRZ fields here as needed

class DocumentExtractionStrategy(ABC):
    """Abstract base class for document extraction strategies."""
    
    def __init__(self):
        self._validation_errors = []
        self._warnings = []
        self._confidence = 1.0
        self._fallback_strategy = None

    def add_fallback_strategy(self, strategy: 'DocumentExtractionStrategy') -> None:
        """Add a fallback strategy to use if this one fails."""
        self._fallback_strategy = strategy

    def chain_strategies(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        results = []
        strategy = self
        while strategy:
            result = strategy.extract(text, mrz_data, file_path=file_path)
            results.append(result)
            strategy = getattr(strategy, '_fallback_strategy', None)
        merged = results[0]
        for r in results[1:]:
            merged = self._merge_results(merged, r)
        return merged

    def _merge_results(self, primary: ExtractionResult, fallback: ExtractionResult) -> ExtractionResult:
        """Merge results from primary and fallback strategies."""
        return ExtractionResult(
            number=primary.number or fallback.number,
            issued_country=primary.issued_country or fallback.issued_country,
            expiration_date=primary.expiration_date or fallback.expiration_date,
            confidence=min(primary.confidence, fallback.confidence),
            validation_errors=primary.validation_errors + fallback.validation_errors,
            warnings=primary.warnings + fallback.warnings
        )

    def _validate_input(self, text: str, mrz_data: Optional[MRZData] = None) -> None:
        """Validate input parameters."""
        if not text or not isinstance(text, str):
            raise ValueError("text must be a non-empty string")
        if mrz_data and not isinstance(mrz_data, MRZData):
            raise ValueError("mrz_data must be an MRZData instance or None")

    def _validate_country_code(self, country_code: str) -> bool:
        """Validate country code."""
        try:
            if not country_code or not isinstance(country_code, str):
                self.add_error("Invalid country code type")
                return False
            if len(country_code) != 3:
                self.add_error(f"Invalid country code length: {len(country_code)}")
                return False
            if not country_code.isalpha():
                self.add_error(f"Country code contains non-letters: {country_code}")
                return False
            if not country_code.isupper():
                self.add_error(f"Country code not uppercase: {country_code}")
                return False
            return True
        except Exception as e:
            self.add_error(f"Error validating country code: {str(e)}")
            return False

    def _validate_document_number(self, number: str, doc_type: str) -> bool:
        """Validate document number."""
        try:
            if not number or not isinstance(number, str):
                self.add_error("Invalid document number type")
                return False
            if len(number) < 6:
                self.add_error(f"Document number too short: {len(number)}")
                return False
            if len(number) > 12:
                self.add_error(f"Document number too long: {len(number)}")
                return False
            return True
        except Exception as e:
            self.add_error(f"Error validating document number: {str(e)}")
            return False

    def _validate_date(self, date_obj: date, date_type: str = "expiration") -> bool:
        """Validate date object."""
        try:
            if not isinstance(date_obj, date):
                self.add_error(f"Invalid {date_type} date type: {type(date_obj)}")
                return False
            return True
        except Exception as e:
            self.add_error(f"Error validating {date_type} date {date_obj}: {str(e)}")
            return False

    def add_error(self, error: str):
        """Add a validation error."""
        self._validation_errors.append(error)
        self._confidence = max(0.0, self._confidence - 0.2)
        logger.error(f"Validation error: {error}")

    def add_warning(self, warning: str):
        """Add a warning."""
        self._warnings.append(warning)
        self._confidence = max(0.0, self._confidence - 0.1)
        logger.warning(f"Validation warning: {warning}")

    def _create_result(self, number: Optional[str], issued_country: Optional[str], 
                      expiration_date: Optional[date]) -> ExtractionResult:
        """Create an ExtractionResult with the given fields."""
        return ExtractionResult(
            number=number,
            issued_country=issued_country,
            expiration_date=expiration_date,
            confidence=self._confidence,
            validation_errors=self._validation_errors,
            warnings=self._warnings
        )
    
    @abstractmethod
    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        """Extract document data from text."""
        pass

    def _score_candidate(self, candidate, context_line, keyword, pattern_type, position, total_lines):
        """Score a candidate based on context, proximity, and pattern strictness."""
        score = 0
        # Proximity to keyword
        if keyword and keyword.lower() in context_line.lower():
            score += 5
        # Pattern strictness
        if pattern_type == 'strict':
            score += 3
        elif pattern_type == 'fuzzy':
            score += 1
        # Position (earlier in document is better)
        score += max(0, 2 - (position / max(1, total_lines)))
        # Penalize blacklisted contexts
        blacklist = ["date of birth", "place of birth"]
        if any(bad in context_line.lower() for bad in blacklist):
            score -= 5
        return score

    def _parse_date_with_pivot_and_validation(self, raw_date_str: str) -> Tuple[Optional[date], List[str], List[str]]:
        """
        Parse date string, apply pivot year, and reject past dates.
        Includes regex fallbacks if dateparser fails.
        
        Returns:
            Tuple of (parsed_date, errors, warnings)
        """
        errors = []
        warnings = []
        parsed_date = None
        
        if not raw_date_str or not isinstance(raw_date_str, str):
            errors.append(f"Invalid date string input: {raw_date_str}")
            return None, errors, warnings

        # --- Attempt 1: Use dateparser ---
        try:
            # Use dateparser for flexibility
            parsed_date_dt = dateparser.parse(raw_date_str, settings={
                'PREFER_LOCALE_DATE_ORDER': False,
                'PREFER_DAY_OF_MONTH': 'first'
            })

            if parsed_date_dt:
                 # Convert datetime to date
                 parsed_date = parsed_date_dt.date()
                 logger.debug(f"dateparser successfully parsed '{raw_date_str}' to {parsed_date}")

        except Exception as e:
            warnings.append(f"dateparser failed for '{raw_date_str}': {str(e)}")
            logger.warning(f"dateparser failed for '{raw_date_str}': {e}")
            parsed_date = None # Ensure parsed_date is None if dateparser throws an unexpected error

        # --- Attempt 2: Regex Fallbacks if dateparser failed ---
        if not parsed_date:
            logger.debug(f"dateparser failed or returned None for '{raw_date_str}'. Attempting regex fallbacks.")
            
            # Define common date regex patterns (DD/MM/YYYY, MM/DD/YYYY, YYYY/MM/DD, YYMMDD, DD MON YYYY)
            regex_patterns = [
                # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
                re.compile(r'^([0-3]?\d)[/\-\.]_?([01]?\d)[/\-\.]_?(\d{4})$'),
                # MM/DD/YYYY or MM-DD-YYYY or MM.DD.YYYY
                re.compile(r'^([01]?\d)[/\-\.]_?([0-3]?\d)[/\-\.]_?(\d{4})$'),
                # YYYY/MM/DD or YYYY-MM-DD or YYYY.MM.DD
                re.compile(r'^(\d{4})[/\-\.]_?([01]?\d)[/\-\.]_?([0-3]?\d)$'),
                # YYMMDD (common in MRZ)
                re.compile(r'^(\d{2})([01]\d)([0-3]\d)$'),
                # DD MON YYYY (e.g., 30 OCT 2032)
                re.compile(r'^([0-3]?\d)\s+([A-Za-z]{3,})\s+(\d{4})$') # Match 3+ letters for month
            ]

            # Month name to number mapping for DD MON YYYY pattern
            month_map = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }

            for i, pattern in enumerate(regex_patterns):
                match = pattern.match(raw_date_str) # Use match to ensure pattern covers the whole string
                if match:
                    logger.debug(f"Regex pattern {i+1} matched '{raw_date_str}'.")
                    try:
                        year, month, day = None, None, None

                        if i in [0, 1]: # DD/MM/YYYY or MM/DD/YYYY
                             # Need to guess the order based on common formats or document context
                             # For simplicity here, let's assume DD/MM/YYYY first, then MM/DD/YYYY if that fails
                             day_str, month_str, year_str = match.groups()
                             try:
                                  parsed_date = date(int(year_str), int(month_str), int(day_str))
                                  logger.debug(f"Parsed as DD/MM/YYYY: {parsed_date}")
                             except ValueError:
                                  logger.debug(f"Failed parsing {raw_date_str} as DD/MM/YYYY. Trying MM/DD/YYYY.")
                                  # Try MM/DD/YYYY
                                  month_str, day_str, year_str = match.groups()
                                  try:
                                       parsed_date = date(int(year_str), int(month_str), int(day_str))
                                       logger.debug(f"Parsed as MM/DD/YYYY: {parsed_date}")
                                  except ValueError:
                                       logger.debug(f"Failed parsing {raw_date_str} as MM/DD/YYYY too.")
                                       continue # Continue to next regex pattern

                        elif i == 2: # YYYY/MM/DD
                             year_str, month_str, day_str = match.groups()
                             parsed_date = date(int(year_str), int(month_str), int(day_str))
                             logger.debug(f"Parsed as YYYY/MM/DD: {parsed_date}")

                        elif i == 3: # YYMMDD
                             year_yy_str, month_str, day_str = match.groups()
                             # Need to apply pivot year logic here
                             current_year_yy = date.today().year % 100
                             century = date.today().year // 100
                             year_int = int(year_yy_str)
                             
                             # Apply a reasonable window for pivot year (e.g., ~20-30 years)
                             if year_int >= current_year_yy - 20:
                                 full_year = year_int + century * 100
                             else:
                                 full_year = year_int + (century + 1) * 100
                                 warnings.append(f"Applied pivot year rule to YYMMDD date '{raw_date_str}'")

                             parsed_date = date(full_year, int(month_str), int(day_str))
                             logger.debug(f"Parsed as YYMMDD with pivot: {parsed_date}")

                        elif i == 4: # DD MON YYYY
                             day_str, month_name_str, year_str = match.groups()
                             month_int = month_map.get(month_name_str.upper()) # Case-insensitive month lookup
                             if month_int is None:
                                 logger.debug(f"Could not map month name '{month_name_str}' to a number.")
                                 continue # Continue to next regex pattern
                             parsed_date = date(int(year_str), month_int, int(day_str))
                             logger.debug(f"Parsed as DD MON YYYY: {parsed_date}")

                        # If a date was successfully parsed by regex, break the regex loop
                        if parsed_date:
                            logger.debug(f"Successfully parsed '{raw_date_str}' using regex pattern {i+1}.")
                            break # Exit regex pattern loop

                    except ValueError as ve:
                         warnings.append(f"Regex matched '{raw_date_str}' (pattern {i+1}) but failed to create date object: {str(ve)}")
                         logger.warning(f"Regex matched '{raw_date_str}' (pattern {i+1}) but failed to create date object: {ve}")
                    except Exception as ex:
                         errors.append(f"Unexpected error parsing regex match '{raw_date_str}' (pattern {i+1}): {str(ex)}")
                         logger.error(f"Unexpected error parsing regex match '{raw_date_str}' (pattern {i+1}): {ex}")
                         # Don't break, try other patterns in case of unexpected error

        # --- Final Validation of Parsed Date (from dateparser or regex) ---
        if parsed_date:
            try:
                # Check for reasonable date ranges (reapply validation from original function)
                if parsed_date < date.today() - timedelta(days=1): # Allow today
                    errors.append(f"Date {parsed_date} is in the past")
                    logger.debug(f"Rejected date {parsed_date} as it's in the past.")
                    return None, errors, warnings # Return None if date is in the past
                
                if parsed_date > date.today() + timedelta(days=365*20):  # 20 years in future
                    warnings.append(f"Suspiciously far future date: {parsed_date}")
                    logger.warning(f"Suspiciously far future date: {parsed_date}")

                # If all validations pass
                return parsed_date, errors, warnings

            except Exception as e:
                errors.append(f"Error validating parsed date {parsed_date}: {str(e)}")
                logger.error(f"Error validating parsed date {parsed_date}: {e}")
                return None, errors, warnings # Return None if validation fails unexpectedly
        else:
            # If after all attempts, no date was parsed
            errors.append(f"Could not parse date from string '{raw_date_str}' using any method.")
            logger.warning(f"Could not parse date from string '{raw_date_str}' using any method.")
            return None, errors, warnings

# Helper function to validate document numbers (basic check)
def _looks_valid_number(number: str, doc_type: str) -> Tuple[bool, List[str], List[str]]:
    """
    Validate document number with detailed error reporting.
            
        Returns:
        Tuple of (is_valid, errors, warnings)
    """
    errors = []
    warnings = []
    
    try:
        if not number or not isinstance(number, str):
            errors.append(f"Invalid number: {number}")
            return False, errors, warnings

        # Basic format validation
        if not number.strip():
            errors.append("Number is empty or whitespace")
            return False, errors, warnings

        # Check for common invalid patterns
        if len(number) > 2 and len(set(number)) == 1 and number.isdigit():
            errors.append(f"Number contains all same digits: {number}")
            return False, errors, warnings

        # Add more specific validation based on doc_type
        if doc_type == "passport":
            if not re.match(r'^[A-Z0-9]{6,10}$', number):
                errors.append(f"Invalid passport number format: {number}")
                return False, errors, warnings
        elif doc_type == "id_card":
            if not re.match(r'^[A-Z0-9]{6,12}$', number):
                errors.append(f"Invalid ID card number format: {number}")
                return False, errors, warnings
        elif doc_type == "visa":
            if not re.match(r'^[0-9]{8,9}$', number):
                errors.append(f"Invalid visa number format: {number}")
                return False, errors, warnings
        elif doc_type == "generic":
            if not re.match(r'^[A-Z0-9]{6,12}$', number):
                warnings.append(f"Number format may be invalid: {number}")

        return True, errors, warnings

    except Exception as e:
        errors.append(f"Error validating number {number}: {str(e)}")
        return False, errors, warnings

def clean_mrz_lines(text):
    """
    Clean up OCR noise from MRZ lines.
    - Remove leading/trailing non-alphanumeric characters (except <)
    - Remove spaces, dashes, underscores
    - Normalize similar-looking characters
    """
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        # Remove leading/trailing non-alphanum (but keep <)
        line = re.sub(r'^[^A-Z0-9<]+|[^A-Z0-9<]+$', '', line, flags=re.IGNORECASE)
        # Replace common OCR errors
        line = line.replace('—', '').replace('_', '').replace(' ', '')
        cleaned.append(line)
    return '\n'.join(cleaned)

class MRZStrategy(DocumentExtractionStrategy):
    """Strategy for extracting data from MRZ lines using passporteye if possible."""
    
    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        self._validate_input(text, mrz_data)
        logger.debug("MRZStrategy: Starting extraction.")
        number = None
        issued_country = None
        expiration_date = None
        mrz_dict = None

        # Use passporteye if file_path is provided
        if file_path:
            logger.debug(f"MRZStrategy: Using file_path: {file_path}")
            if not os.path.exists(file_path):
                logger.error(f"MRZStrategy: File does not exist: {file_path}")
            else:
                logger.debug(f"MRZStrategy: File exists: {file_path}")
                try:
                    from passporteye import read_mrz
                    logger.debug(f"MRZStrategy: Calling passporteye.read_mrz on {file_path}")
                    mrz = read_mrz(file_path)
                    if mrz:
                        logger.debug(f"MRZStrategy: passporteye.read_mrz result: {mrz}")
                        mrz_dict = mrz.to_dict()
                        logger.debug(f"MRZStrategy: passporteye MRZ extraction successful: {mrz_dict}")
                        
                        # Validate MRZ data
                        if mrz_dict.get('valid_score', 0) < 50:
                            logger.warning(f"MRZStrategy: Low confidence MRZ extraction (score: {mrz_dict.get('valid_score')})")
                            return self._create_result(None, None, None)
                            
                        number = mrz_dict.get('number')
                        issued_country = mrz_dict.get('country')
                        
                        # Validate country code
                        if issued_country and not self._validate_country_code(issued_country):
                            logger.warning(f"MRZStrategy: Invalid country code from MRZ: {issued_country}")
                            issued_country = None
                            
                        exp_str = mrz_dict.get('expiration_date')
                        if exp_str:
                            try:
                                # Handle YYMMDD format
                                year = int(exp_str[:2])
                                month = int(exp_str[2:4])
                                day = int(exp_str[4:6])
                                # Add 2000 to year if it's less than 50 (assuming 20xx), otherwise 19xx
                                year += 2000 if year < 50 else 1900
                                expiration_date = date(year, month, day)
                                logger.debug(f"MRZStrategy: Parsed expiration date: {expiration_date}")
                                
                                # Validate expiration date
                                if not self._validate_date(expiration_date):
                                    logger.warning(f"MRZStrategy: Invalid expiration date: {expiration_date}")
                                    expiration_date = None
                            except Exception as e:
                                logger.warning(f"MRZStrategy: Failed to parse expiration date {exp_str}: {e}")
                                expiration_date = None
                    else:
                        logger.warning("MRZStrategy: passporteye.read_mrz returned None (no MRZ found)")
                except Exception as e:
                    logger.error(f"MRZStrategy: Error during MRZ extraction: {e}")
                    return self._create_result(None, None, None)

        # If we have valid data from MRZ, return it
        if number and issued_country and expiration_date:
            return self._create_result(number, issued_country, expiration_date)
            
        # If we have partial data, try to extract more from text
        if not number or not issued_country or not expiration_date:
            logger.debug("Using GenericStrategy for extraction (no validation, no sanitization, collect all candidates, pick best)")
            generic = GenericStrategy()
            generic_result = generic.extract(text, mrz_data)
            
            # Merge results, preferring MRZ data when available
            if number is None:
                number = generic_result.number
            if issued_country is None:
                issued_country = generic_result.issued_country
            if expiration_date is None:
                expiration_date = generic_result.expiration_date
                
            return self._create_result(number, issued_country, expiration_date)

        return self._create_result(None, None, None)

class ESPassportStrategy(DocumentExtractionStrategy):
    """Strategy for Spanish passports."""
    
    _NUM_RE = re.compile(r'\b[A-Z]\d{7}[A-Z]\b')
    _EXP_RE = re.compile(r'(?:Valido\s+hasta|VALIDEZ)[:\s]*([0-3]?\d[/\-\.]\d{1,2}[/\-\.]\d{2,4})', re.IGNORECASE)
    
    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        self._validate_input(text, mrz_data)
        number = None
        expiration_date = None
        if mrz_data and mrz_data.number:
            sanitized_number = mrz_data.number
            is_valid, errors, warnings = _looks_valid_number(sanitized_number, "passport")
            for err in errors: self.add_error(err)
            for warn in warnings: self.add_warning(warn)
            if is_valid:
                number = sanitized_number
                logger.debug(f"Using number from MRZ: {number}")
            else:
                logger.debug(f"Rejected number from MRZ after validation: {sanitized_number}")
        else:
            num_match = self._NUM_RE.search(text)
            if num_match:
                candidate_number = num_match.group(0)
                sanitized_number = candidate_number
                is_valid, errors, warnings = _looks_valid_number(sanitized_number, "passport")
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if is_valid:
                    number = sanitized_number
                    logger.debug(f"Found number via regex: {number}")
                else:
                    logger.debug(f"Rejected number via regex after validation: {sanitized_number}")

        if mrz_data and mrz_data.expiration_date and isinstance(mrz_data.expiration_date, date):
            expiration_date = mrz_data.expiration_date
            logger.debug(f"Using expiration date from MRZ: {expiration_date}")
            # Validate date from MRZ (if it was a date object)
            self._validate_date(expiration_date)
        elif mrz_data and mrz_data.expiration_date_str:
            # Parse and validate date from MRZ string
            parsed_date, errors, warnings = self._parse_date_with_pivot_and_validation(mrz_data.expiration_date_str)
            for err in errors: self.add_error(err)
            for warn in warnings: self.add_warning(warn)
            if parsed_date:
                expiration_date = parsed_date
                logger.debug(f"Found expiration date from MRZ string: {expiration_date}")
            else:
                logger.debug(f"Failed to parse expiration date from MRZ string: {mrz_data.expiration_date_str}")

        # Issued country is fixed for this strategy, but validate it
        issued_country = "ESP"
        self._validate_country_code(issued_country)

        return self._create_result(number, issued_country, expiration_date)

class EGYPassportStrategy(DocumentExtractionStrategy):
    """Strategy for Egyptian passports."""
    
    # More precise patterns for Egyptian passports
    _NUM_RE = re.compile(r'\b[A-Z]\d{8}\b')  # Matches A25886431
    _EXP_RE = re.compile(r'\d([A-Z]{3})\d{7}(\d{2})(\d{2})(\d{2})')  # Matches 5EGY0501183
    _MRZ_LINE_RE = re.compile(r'P<EGY.*?<<.*?<<.*?$', re.MULTILINE)  # Matches MRZ line with EGY
    
    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        self._validate_input(text, mrz_data)
        logger.debug("Using EGYPassportStrategy for extraction")
        
        number = None
        expiration_date = None

        # First try MRZ data if available and valid
        if mrz_data:
            if mrz_data.number:
                sanitized_number = mrz_data.number
                is_valid, errors, warnings = _looks_valid_number(sanitized_number, "passport")
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if is_valid:
                    number = sanitized_number
                    logger.debug(f"Using number from MRZ: {number}")
                else:
                    logger.debug(f"Rejected number from MRZ after validation: {sanitized_number}")

            if mrz_data.expiration_date and isinstance(mrz_data.expiration_date, date):
                expiration_date = mrz_data.expiration_date
                logger.debug(f"Using expiration date from MRZ: {expiration_date}")
                # Validate date from MRZ (if it was a date object)
                self._validate_date(expiration_date)
            elif mrz_data.expiration_date_str:
                # Parse and validate date from MRZ string
                parsed_date, errors, warnings = self._parse_date_with_pivot_and_validation(mrz_data.expiration_date_str)
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if parsed_date:
                    expiration_date = parsed_date
                    logger.debug(f"Found expiration date from MRZ string: {expiration_date}")

        # If number not found from MRZ, try text extraction
        if not number:
            # Look for MRZ line pattern first
            mrz_match = self._MRZ_LINE_RE.search(text)
            if mrz_match:
                logger.debug("Found Egyptian MRZ line pattern")
                # Extract number from the line after MRZ
                next_line = text[mrz_match.end():].split('\n')[0]
                num_match = self._NUM_RE.search(next_line)
                if num_match:
                    candidate_number = num_match.group(0)
                    sanitized_number = candidate_number
                    is_valid, errors, warnings = _looks_valid_number(sanitized_number, "passport")
                    for err in errors: self.add_error(err)
                    for warn in warnings: self.add_warning(warn)
                    if is_valid:
                        number = sanitized_number
                        logger.debug(f"Found Egyptian passport number: {number}")
                    else:
                        logger.debug(f"Rejected Egyptian passport number after validation: {sanitized_number}")
            # If no MRZ line found or number not extracted from it, try direct number match
            if not number:
                num_match = self._NUM_RE.search(text)
                if num_match:
                    candidate_number = num_match.group(0)
                    sanitized_number = candidate_number
                    is_valid, errors, warnings = _looks_valid_number(sanitized_number, "passport")
                    for err in errors: self.add_error(err)
                    for warn in warnings: self.add_warning(warn)
                    if is_valid:
                        number = sanitized_number
                        logger.debug(f"Found Egyptian passport number without MRZ: {number}")
                    else:
                        logger.debug(f"Rejected Egyptian passport number without MRZ after validation: {sanitized_number}")

        # If expiration date not found from MRZ, try text extraction
        if not expiration_date:
            exp_match = self._EXP_RE.search(text)
            if exp_match:
                # Reuse the common date parsing helper
                raw_date_str = exp_match.group(1)
                # Parse and validate date from regex
                parsed_date, errors, warnings = self._parse_date_with_pivot_and_validation(raw_date_str)
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if parsed_date:
                    expiration_date = parsed_date
                    logger.debug(f"Found Egyptian passport expiration date: {expiration_date}")
                else:
                    logger.debug(f"Failed to parse Egyptian passport expiration date: {raw_date_str}")

        # Issued country is fixed for this strategy, but validate it
        issued_country = "EGY"
        self._validate_country_code(issued_country)

        return self._create_result(number, issued_country, expiration_date)

class USPassportStrategy(DocumentExtractionStrategy):
    """Strategy for US passports."""
    
    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        self._validate_input(text, mrz_data)
        logger.debug("Using USPassportStrategy for extraction")
        
        number = None
        expiration_date = None

        # 1. Prefer MRZ if available
        if mrz_data:
            if mrz_data.number:
                sanitized_number = mrz_data.number
                is_valid, errors, warnings = _looks_valid_number(sanitized_number, "passport")
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if is_valid:
                    number = sanitized_number
                    logger.debug(f"Using number from MRZ: {number}")
                else:
                    logger.debug(f"Rejected number from MRZ after validation: {sanitized_number}")

            if isinstance(mrz_data.expiration_date, date):
                expiration_date = mrz_data.expiration_date
                logger.debug(f"Using expiration date from MRZ: {expiration_date}")
                self._validate_date(expiration_date)

            elif mrz_data.expiration_date_str:
                parsed_date, errors, warnings = self._parse_date_with_pivot_and_validation(mrz_data.expiration_date_str)
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if parsed_date:
                    expiration_date = parsed_date
                    logger.debug(f"Found expiration date from MRZ string: {expiration_date}")

        # 2. Fallback: try text-based MRZ parsing
        if not number or not expiration_date:
            mrz_match = re.search(r'P<USA.*?<<.*?<<.*?$', text, re.MULTILINE)
            if mrz_match:
                logger.debug("Found US passport MRZ line in text")
                lines = text[mrz_match.end():].splitlines()
                next_line = lines[0].strip() if lines else ""
            
                # Try to extract number
                num_match = re.search(r'\b[A-Z]\d{8}\b', next_line)
                if num_match:
                    candidate_number = num_match.group(0)
                    is_valid, errors, warnings = _looks_valid_number(candidate_number, "passport")
                    for err in errors: self.add_error(err)
                    for warn in warnings: self.add_warning(warn)
                    if is_valid:
                        number = candidate_number
                        logger.debug(f"Found US passport number from text MRZ: {number}")
                    else:
                        logger.debug(f"Rejected US passport number from text MRZ after validation: {candidate_number}")
                else:
                    logger.debug("No US passport number found in text MRZ")
            
                # Try to extract expiration date
                if not expiration_date:
                    exp_match = re.search(r'\d{2}(\d{2})(\d{2})(\d{2})', next_line)
                    if exp_match:
                        raw_date_str = ''.join(exp_match.groups())
                        parsed_date, errors, warnings = self._parse_date_with_pivot_and_validation(raw_date_str)
                        for err in errors: self.add_error(err)
                        for warn in warnings: self.add_warning(warn)
                        if parsed_date:
                            expiration_date = parsed_date
                            logger.debug(f"Found US passport expiration date from text MRZ: {expiration_date}")
                        else:
                            logger.warning(f"Failed to parse US passport expiration date from text MRZ: {raw_date_str}")
                    else:
                        logger.debug("No US passport expiration date found in text MRZ")
                else:
                    logger.debug("No US passport MRZ line found in text")

        # 3. Fixed issued country
        issued_country = "USA"
        self._validate_country_code(issued_country)

        return ExtractionResult(
            number=number,
            expiration_date=expiration_date,
            issued_country=issued_country,
            errors=self.errors,
            warnings=self.warnings,
        )

class VisaStrategy(DocumentExtractionStrategy):
    """
    Extracts number, issued_country, and expiration_date from visa stickers.
    Falls back to GenericStrategy if any field remains None after visa-specific logic.
    """

    # Field-extraction rules (visa-specific)
    
    # a. Issued country regex patterns
    _COUNTRY_PATTERNS = [
        re.compile(r'(?:Issuing\s*(?:Country|Post)|Authority)[:\s]*([A-Z]{3})'),
        re.compile(r'Issued\s*By[:\s]*([A-Z]{3})'),
    ]

    # Keywords to look near for fuzzy country name matching
    _FUZZY_COUNTRY_KEYWORDS = ["Country", "Authority", "Post", "Issued By"]

    # b. Visa number regex cascade
    _NUMBER_PATTERNS = [
        re.compile(r'(?:Control\s*No\.?|Visa\s*(?:No\.?|Number)|Red\s*Number)[:\s#]*([0-9]{8,9})'),
    ]

    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        self._validate_input(text, mrz_data)
        logger.debug("Using VisaStrategy for extraction")
        
        number = None
        issued_country = None
        expiration_date = None

        # Convert MRZData to dict for _find_expiration_date
        mrz_dict = None
        if mrz_data:
            mrz_dict = {
                'expiration_date': mrz_data.expiration_date_str or 
                                 (mrz_data.expiration_date.strftime('%y%m%d') if mrz_data.expiration_date else None)
            }

        # Use the new _find_expiration_date function
        expiration_date = _find_expiration_date(text, "visa", mrz_dict)
        if isinstance(expiration_date, int):  # If only year found, convert to date
            expiration_date = date(expiration_date, 12, 31)

        # Extract number from MRZ if available
        if mrz_data and mrz_data.number:
            number = mrz_data.number
            logger.debug(f"Using number from MRZ: {number}")

        # Extract country from MRZ if available
        if mrz_data and mrz_data.country_code:
            issued_country = mrz_data.country_code
            logger.debug(f"Using country from MRZ: {issued_country}")

        # If any field is missing, try fallback
        if None in (number, issued_country, expiration_date):
            logger.debug("VisaStrategy missing data, attempting fallback to GenericStrategy")
            generic_result = GenericStrategy().extract(text, mrz_data, file_path=file_path)
            return self._merge_results(
                self._create_result(number, issued_country, expiration_date),
                generic_result
            )

        return self._create_result(number, issued_country, expiration_date)

class EUGenericStrategy(DocumentExtractionStrategy):
    """Generic strategy for EU documents."""
    
    _NUM_RE = re.compile(r'[CDEFGL][0-9A-Z]{8}')
    _EXP_RE = re.compile(r'(?:Gültig\s+bis|Valable\s+jusqu\'au|Valido\s+Hasta)[:\s]*([0-3]?\d[\./][01]?\d[\./]\d{2,4})', re.IGNORECASE)
    
    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        self._validate_input(text, mrz_data)
        logger.debug("Using EUGenericStrategy for extraction")

        number = None
        expiration_date = None

        # Consider using MRZ data if available and valid
        if mrz_data:
            # For EU documents, MRZ might be TD1 or TD2. Check number format against generic or ID card pattern.
            if mrz_data.number:
                sanitized_number = mrz_data.number
                is_valid, errors, warnings = _looks_valid_number(sanitized_number, "id_card") # Use id_card validation for EU generic
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if is_valid:
                    number = sanitized_number
                    logger.debug(f"Using number from MRZ: {number}")
                else:
                    logger.debug(f"Rejected number from MRZ after validation: {sanitized_number}")

            if mrz_data.expiration_date and isinstance(mrz_data.expiration_date, date):
                expiration_date = mrz_data.expiration_date
                logger.debug(f"Using expiration date from MRZ: {expiration_date}")
                # Validate date from MRZ (if it was a date object)
                self._validate_date(expiration_date)
            elif mrz_data.expiration_date_str:
                # Parse and validate date from MRZ string
                parsed_date, errors, warnings = self._parse_date_with_pivot_and_validation(mrz_data.expiration_date_str)
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if parsed_date:
                    expiration_date = parsed_date
                    logger.debug(f"Found expiration date from MRZ string: {expiration_date}")

        # If number not found from MRZ, try text extraction
        if not number:
            num_match = self._NUM_RE.search(text)
            if num_match:
                sanitized_number = num_match.group(0)
                is_valid, errors, warnings = _looks_valid_number(sanitized_number, "id_card")
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if is_valid:
                    number = sanitized_number
                    logger.debug(f"Found number via regex: {number}")
                else:
                    logger.debug(f"Rejected number via regex after validation: {sanitized_number}")

        # If expiration date not found from MRZ, try text extraction
        if not expiration_date:
            exp_match = self._EXP_RE.search(text)
            if exp_match:
                raw_date_str = exp_match.group(1)
                # Parse and validate date from regex
                parsed_date, errors, warnings = self._parse_date_with_pivot_and_validation(raw_date_str)
                for err in errors: self.add_error(err)
                for warn in warnings: self.add_warning(warn)
                if parsed_date:
                    expiration_date = parsed_date
                    logger.debug(f"Found expiration date via regex: {expiration_date}")
                else:
                    logger.debug(f"Failed to parse expiration date via regex: {raw_date_str}")

        # Issued country is not fixed, leave it as None for now or try to infer? (Out of scope for this fix)
        issued_country = None # Assume country determination is handled elsewhere if not in MRZ
        if mrz_data and mrz_data.country_code:
            sanitized_country = mrz_data.country_code
            issued_country = sanitized_country
            self._validate_country_code(issued_country)
            logger.debug(f"Using issued country from MRZ: {issued_country}")

        return self._create_result(number, issued_country, expiration_date)

class GenericStrategy(DocumentExtractionStrategy):
    """Fallback strategy with robust patterns for all passport types."""
    
    _NUM_PATTERNS = [
        # MRZ line patterns - updated to better handle the format
        r'([A-Z0-9]{6,10})<7[A-Z]{3}\d{7}',  # Number before MRZ date (e.g., RA052146<7DMA...)
        r'(?:P<[A-Z]{3}.*?<<.*?<<.*?)\n([A-Z0-9]{6,10})',  # Number after MRZ line
        r'([A-Z0-9]{6,10})\s+\d[A-Z]{3}\d{7}\d{2}\d{2}\d{2}',  # Number before MRZ date
        
        # Document number patterns with context
        r'(?:PASSPORT\s+ND/N\.\s+PASSEPORT|PASSPORT\s+NUMBER|PASSPORT\s+NO|PASAPORTE\s+No)[:\s]*([A-Z0-9]{6,10})',
        r'P\s+[A-Z]{3}\s+([A-Z0-9]{6,10})',  # After P and country code
        r'(?:ID|ID\s+CARD|TARJETA|PERMISO)[:\s]*([A-Z0-9]{6,10})',  # ID card numbers
        
        # Specific formats with context
        r'(?:PASSPORT|PASZPORT)\s+[A-Z0-9]{1,2}\s+([A-Z0-9]{6,10})',  # After PASSPORT/PASZPORT
        r'(?:TYPE|CODE)\s+[A-Z0-9]{1,2}\s+([A-Z0-9]{6,10})',  # After TYPE/CODE

        # Specific formats without context (lower priority)
        r'\b[A-Z]\d{8}\b',  # Egyptian format (e.g., A25886431)
        r'\b[A-Z]\d{7}\b',  # Common format (e.g., A1234567)
        r'\b[A-Z]\d{8}\b',  # Longer format (e.g., A12345678)
        r'\b[A-Z]\d{7}[A-Z]\b',  # Format with check digit (e.g., A1234567B)
        r'\b[A-Z]{2}\d{7}\b',  # Two-letter prefix (e.g., AB1234567)
        r'\b[A-Z]{3}\d{6}\b',  # Three-letter prefix (e.g., ABC123456)
        r'\b[A-Z]\d{6}\b',     # Six digits (e.g., A123456)
    ]
    
    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        self._validate_input(text, mrz_data)
        logger.debug("Using GenericStrategy for extraction (no validation, no sanitization, collect all candidates, pick best)")
        
        number = None
        issued_country = None
        expiration_date = None

        # Convert MRZData to dict for _find_expiration_date
        mrz_dict = None
        if mrz_data:
            mrz_dict = {
                'expiration_date': mrz_data.expiration_date_str or 
                                 (mrz_data.expiration_date.strftime('%y%m%d') if mrz_data.expiration_date else None)
            }

        # Use the new _find_expiration_date function
        expiration_date = _find_expiration_date(text, "passport", mrz_dict)
        if isinstance(expiration_date, int):  # If only year found, convert to date
            expiration_date = date(expiration_date, 12, 31)

        # --- Number extraction logic ---
        candidates = []
        if mrz_data and mrz_data.number:
            candidates.append((mrz_data.number, 10.0, "MRZ"))
            logger.debug(f"Found number from MRZ line: {mrz_data.number}")
        # Collect all regex candidates
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for pat in self._NUM_PATTERNS:
                for m in re.finditer(pat, line):
                    candidate = m.group(1) if m.lastindex else m.group(0)
                    score = self._score_candidate(candidate, line, None, "strict", i, len(lines))
                    candidates.append((candidate, score, line))
                    logger.debug(f"Found candidate number: {candidate} in line: {line}")
        # Pick best
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            number = candidates[0][0]
            logger.debug(f"Selected number: {number} (score: {candidates[0][1]})")
        else:
            logger.debug("No number candidates found.")

        # --- Country extraction logic ---
        country_candidates = []
        
        # 1. MRZ Data (highest priority)
        if mrz_data and mrz_data.country_code:
            country_candidates.append((mrz_data.country_code, 10.0, "MRZ"))
            logger.debug(f"Found country code from MRZ data: {mrz_data.country_code}")

        # 2. MRZ Line Pattern (high priority)
        mrz_patterns = [
            re.compile(r'P<([A-Z]{3})'),  # Standard MRZ format
            re.compile(r'([A-Z]{3})<'),   # Alternative MRZ format
            re.compile(r'([A-Z]{3})\d{9}') # MRZ with country code followed by numbers
        ]
        
        for line in lines:
            for pattern in mrz_patterns:
                mrz_match = pattern.search(line)
                if mrz_match:
                    country_code = mrz_match.group(1)
                    if self._validate_country_code(country_code):
                        country_candidates.append((country_code, 9.0, "MRZ"))
                        logger.debug(f"Found valid country code in MRZ line: {country_code}")
                    break

        # 3. Document Header Patterns (fixed score, check all lines)
        header_patterns = [
            re.compile(r'(?:PASSPORT|ID\s+CARD|DOCUMENT)\s+OF\s+([A-Z]{3})', re.IGNORECASE),
            re.compile(r'([A-Z]{3})\s+(?:PASSPORT|ID\s+CARD|DOCUMENT)', re.IGNORECASE),
            re.compile(r'ISSUED\s+BY\s+([A-Z]{3})', re.IGNORECASE)
        ]
        
        for i, line in enumerate(lines):
            for pattern in header_patterns:
                match = pattern.search(line)
                if match:
                    country_code = match.group(1)
                    if self._validate_country_code(country_code):
                        score = 8.0  # Fixed score for header matches
                        country_candidates.append((country_code, score, "Header"))
                        logger.debug(f"Found country code in header: {country_code}")
                    break

        # 4. Context-aware country code detection (medium priority)
        country_keywords = [
            "ISSUING COUNTRY", "COUNTRY OF ISSUE", "NATIONALITY", "COUNTRY",
            "STATE", "ISSUED BY", "AUTHORITY", "ISSUING AUTHORITY"
        ]
        country_re = re.compile(
            r'(?:' + '|'.join(country_keywords) + r')\s*[:\s]*([A-Z]{3})',
            re.IGNORECASE
        )
        
        for i, line in enumerate(lines):
            for match in country_re.finditer(line):
                country_code = match.group(1)
                if self._validate_country_code(country_code):
                    score = self._score_candidate(country_code, line, None, "strict", i, len(lines))
                    country_candidates.append((country_code, score, "Context"))
                    logger.debug(f"Found country code in context: {country_code}")

        # 5. Generic country code detection (lowest priority)
        generic_re = re.compile(r'\b([A-Z]{3})\b')
        for i, line in enumerate(lines):
            for match in generic_re.finditer(line):
                country_code = match.group(1)
                if self._validate_country_code(country_code):
                    score = self._score_candidate(country_code, line, None, "fuzzy", i, len(lines))
                    country_candidates.append((country_code, score, "Generic"))
                    logger.debug(f"Found generic country code: {country_code}")

        # Select the best country code
        if country_candidates:
            # Sort by score and source priority
            country_candidates.sort(key=lambda x: (x[1], x[2] != "MRZ", x[2] != "Header", x[2] != "Context"), reverse=True)
            issued_country = country_candidates[0][0]
            logger.debug(f"Selected issued_country: {issued_country} (score: {country_candidates[0][1]}, source: {country_candidates[0][2]})")
        else:
            logger.debug("No valid country candidates found.")

        return self._create_result(number, issued_country, expiration_date)

    def _validate_country_code(self, country_code: str) -> bool:
        """Validate if a country code is likely to be valid."""
        if not country_code or not isinstance(country_code, str):
            return False
            
        # Must be exactly 3 uppercase letters
        if not re.match(r'^[A-Z]{3}$', country_code):
            return False
            
        # Check against known invalid codes
        invalid_codes = {'XXX', 'ZZZ', 'UNK', 'N/A', 'NA', 'TBD'}
        if country_code in invalid_codes:
            return False
            
        # Check if it's a known ISO country code
        try:
            country = pycountry.countries.get(alpha_3=country_code)
            return country is not None
        except Exception:
            return False

class IDCardStrategy(DocumentExtractionStrategy):
    """
    Extracts number, issued_country, and expiration_date from national ID cards.
    Falls back to GenericStrategy if any of the three fields stay None.
    """

    # Field-extraction rules (ID-card specific)

    # a. Issued country regex patterns (including multilingual)
    _COUNTRY_PATTERNS = [
        re.compile(r'(?:Issuing|Issued\s+by|Authority)[:\s]*([A-Z]{3})'),
        re.compile(r'\bNationality[:\s]*([A-Z]{3})'),
        # Multilingual:
        re.compile(r'País\s+de\s+expedición[:\s]*([A-Z]{3})'), # Spanish
        re.compile(r'Staat\s+der\s+Ausstellung[:\s]*([A-Z]{3})'), # German
    ]
    
    # Keywords to look near for fuzzy country name matching
    _FUZZY_COUNTRY_KEYWORDS = ["Country", "Authority", "Issued By", "Nationality", "País", "Staat"]

    # b. Document / card number regex cascade (country-specific and fallback)
    _NUMBER_PATTERNS_COUNTRY_SPECIFIC = {
        "ESP": re.compile(r'\b\d{8}[A-Z]\b'), # Spanish DNI
        "DEU": re.compile(r'\b[CDEFGL][0-9A-Z]{8}\b'), # German Personalausweis
    }

    _NUMBER_FALLBACK_PATTERN = re.compile(r'\b[A-Z0-9]{6,12}\b')

    def extract(self, text: str, mrz_data: Optional[MRZData] = None, file_path: Optional[str] = None) -> ExtractionResult:
        self._validate_input(text, mrz_data)
        logger.debug("Using IDCardStrategy for extraction")
        
        number = None
        issued_country = None
        expiration_date = None

        # Convert MRZData to dict for _find_expiration_date
        mrz_dict = None
        if mrz_data:
            mrz_dict = {
                'expiration_date': mrz_data.expiration_date_str or 
                                 (mrz_data.expiration_date.strftime('%y%m%d') if mrz_data.expiration_date else None)
            }

        # Use the new _find_expiration_date function
        expiration_date = _find_expiration_date(text, "id_card", mrz_dict)
        if isinstance(expiration_date, int):  # If only year found, convert to date
            expiration_date = date(expiration_date, 12, 31)

        # Extract number from MRZ if available
        if mrz_data and mrz_data.number:
            number = mrz_data.number
            logger.debug(f"Using number from MRZ: {number}")

        # Extract country from MRZ if available
        if mrz_data and mrz_data.country_code:
            issued_country = mrz_data.country_code
            logger.debug(f"Using country from MRZ: {issued_country}")

        # If any field is missing, try fallback
        if None in (number, issued_country, expiration_date):
            logger.debug("IDCardStrategy missing data, attempting fallback to GenericStrategy")
            generic_result = GenericStrategy().extract(text, mrz_data, file_path=file_path)
            return self._merge_results(
                self._create_result(number, issued_country, expiration_date),
                generic_result
            )

        return self._create_result(number, issued_country, expiration_date)

# Strategy registry
STRATEGY_REGISTRY: Dict[str, type[DocumentExtractionStrategy]] = {
    "MRZ": MRZStrategy,
    "ESP": ESPassportStrategy,
    "EGY": EGYPassportStrategy,
    "EU": EUGenericStrategy,
    "USA": USPassportStrategy,
    "GEN": GenericStrategy,
    "VISA": VisaStrategy,
    "ID": IDCardStrategy # Add the new IDCardStrategy
}

def get_strategy(doc_type: str) -> DocumentExtractionStrategy:
    """
    Get the appropriate strategy based on document type.
    
    Args:
        doc_type: The type of document (e.g., 'passport', 'id_card', 'visa')
        
    Returns:
        An instance of the appropriate strategy, defaulting to GenericStrategy.
    """
    doc_type_lower = doc_type.lower()

    # Passport: chain MRZ -> country-specific -> generic
    if doc_type_lower == "passport":
        mrz = MRZStrategy()
        mrz.add_fallback_strategy(ESPassportStrategy())
        mrz.add_fallback_strategy(EGYPassportStrategy())
        mrz.add_fallback_strategy(EUGenericStrategy())
        mrz.add_fallback_strategy(USPassportStrategy())
        mrz.add_fallback_strategy(GenericStrategy())
        return mrz

    # Check for specific document types first
    if doc_type_lower == "visa":
        logger.debug("get_strategy: Document type is visa, returning VisaStrategy.")
        return STRATEGY_REGISTRY["VISA"]()
    
    # Check for ID card / Drivers License types
    elif doc_type_lower in {"id", "id_card", "drivers_license"}:
         logger.debug(f"get_strategy: Document type is {doc_type_lower}, returning IDCardStrategy.")
         return STRATEGY_REGISTRY["ID"]()

    # Add checks for other specific types here as they are implemented
    # elif doc_type_lower == "passport": # Passport handled by specific country strategies or GEN
    #     pass # Passports currently rely on MRZ/Generic or specific country strategies mapped directly by name

    # Check if a strategy with the exact (case-sensitive) doc_type name exists in the registry
    if doc_type in STRATEGY_REGISTRY:
         logger.debug(f"get_strategy: Found strategy for specific type '{doc_type}'.")
         return STRATEGY_REGISTRY[doc_type]()

    # Default to generic strategy if no specific strategy is found
    logger.debug(f"get_strategy: No specific strategy for '{doc_type}', defaulting to GenericStrategy.")
    return STRATEGY_REGISTRY["GEN"]() 

def _find_expiration_date(text: str,
                         doc_type: str,
                         mrz: dict | None = None,
                         today: date | None = None
) -> int | date | None:
    """
    Find expiration date from document text using a robust multi-stage approach.
    Now, if any date in the future is detected anywhere in the text, it is automatically returned as the expiration date, regardless of proximity to keywords.
    """
    # 1. Month-name table
    MONTH_MAP = {
        # English
        "JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
        "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12,
        # Spanish
        "ENE":1,"ABR":4,"AGO":8,"DIC":12,
        # German
        "MÄR":3,"MAER":3,"OKT":10,"DEZ":12,
        # French (short)
        "JANV":1,"FÉV":2,"FEV":2,"AVR":4,"JUIL":7,"AOÛ":8,"AOUT":8,
    }

    # 2. Regex patterns (compile once)
    FULL_NUM = re.compile(r'(?P<d>[0-3]?\d)[\s\./\-](?P<m>[01]?\d)[\s\./\-](?P<y>\d{2,4})', re.I)
    NAME_MID = re.compile(r'(?P<d>[0-3]?\d)?[\s\-\/\.]?(?P<mname>[A-Z]{3,5})[\s\-\/\.]?(?P<y>\d{2,4})', re.I)
    YEAR_ONLY = re.compile(r'\b(20\d{2})\b')
    # Add specific pattern for DD MON YYYY format
    DD_MON_YYYY = re.compile(r'(?P<d>[0-3]?\d)\s+(?P<mname>[A-Z]{3,5})\s+(?P<y>\d{4})', re.I)

    KEYWORDS = (
        "EXP", "EXPIRES", "EXPIRY", "EXPIRATION",
        "VALID UNTIL", "VALID THRU",
        "VÁLIDO HASTA", "GÜLTIG BIS", "VIGENCIA"
    )
    KEYWORD_RE = re.compile("|".join(re.escape(k) for k in KEYWORDS), re.I)

    # Helper functions
    def _clean(text: str) -> str:
        """Collapse whitespace, strip duplicate separators."""
        return re.sub(r'\s+', ' ', text)

    def _normalize_month_name(s: str) -> int | None:
        """Normalize month name to number using MONTH_MAP."""
        key = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().upper()
        return MONTH_MAP.get(key)

    def _build_date(d: int, m: int, y: int, today: date) -> date | None:
        try:
            if y < 100:  # pivot YY → YYYY
                y += 2000 if y <= (today.year % 100) + 10 else 1900
            dt = date(y, m, d)
            return dt if dt > today else None
        except ValueError:
            return None

    # 1. Set reference date
    today = today or date.today()

    # 2. Check MRZ if present
    if mrz and 'expiration_date' in mrz:
        mrz_date = mrz['expiration_date']
        if isinstance(mrz_date, str) and len(mrz_date) == 6:  # YYMMDD format
            try:
                y = int(mrz_date[:2])
                m = int(mrz_date[2:4])
                d = int(mrz_date[4:6])
                dt = _build_date(d, m, y, today)
                if dt:
                    logger.debug(f"Found valid MRZ expiration date: {dt}")
                    return dt
            except (ValueError, IndexError):
                pass

    # 3. First try to find DD MON YYYY format anywhere in text
    for match in DD_MON_YYYY.finditer(text):
        d = int(match.group('d'))
        mname = match.group('mname')
        y = int(match.group('y'))
        m = _normalize_month_name(mname)
        if m:
            dt = _build_date(d, m, y, today)
            if dt:
                logger.debug(f"Found expiration date via DD_MON_YYYY: {dt}")
                return dt

    # 4. Line-window scan for other formats
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if KEYWORD_RE.search(line):
            # Build block from keyword line plus up to 3 following lines
            block = "\n".join(lines[i:i+4])
            block = _clean(block)
            
            # Try FULL_NUM pattern
            match = FULL_NUM.search(block)
            if match:
                d = int(match.group('d'))
                m = int(match.group('m'))
                y = int(match.group('y'))
                dt = _build_date(d, m, y, today)
                if dt:
                    logger.debug(f"Found expiration date via FULL_NUM: {dt}")
                    return dt

            # Try NAME_MID pattern
            match = NAME_MID.search(block)
            if match:
                d = int(match.group('d') or 1)  # Default to 1st if day not specified
                mname = match.group('mname')
                y = int(match.group('y'))
                m = _normalize_month_name(mname)
                if m:
                    dt = _build_date(d, m, y, today)
                    if dt:
                        logger.debug(f"Found expiration date via NAME_MID: {dt}")
                        return dt

            # Try YEAR_ONLY pattern
            match = YEAR_ONLY.search(block)
            if match:
                y = int(match.group(1))
                if today.year < y <= today.year + 20:
                    logger.debug(f"Found expiration year: {y}")
                    return y

    # 5. Fallback to dateparser only if no specific format was found
    import dateparser
    from datetime import timedelta
    date_candidates = set()
    # Find all substrings that look like dates (very permissive regex)
    date_like_re = re.compile(r'\b(\d{1,2}[\s\./-][A-Za-z]{3,}|\d{1,2}[\s\./-]\d{1,2}[\s\./-]\d{2,4}|[A-Za-z]{3,}\s+\d{4}|\d{4})\b')
    for match in date_like_re.finditer(text):
        raw = match.group(0)
        parsed = dateparser.parse(raw, settings={'PREFER_DAY_OF_MONTH': 'first'})
        if parsed:
            dt = parsed.date()
            if dt > today:
                date_candidates.add(dt)
    # Also look for YYYY (year only) in the future
    for match in re.finditer(r'\b(20\d{2})\b', text):
        y = int(match.group(1))
        if today.year < y <= today.year + 20:
            # Only use December 31st if we haven't found a more specific date
            if not date_candidates:
                date_candidates.add(date(y, 12, 31))
    if date_candidates:
        furthest = max(date_candidates)  # Get the furthest future date instead of the soonest
        logger.debug(f"Found future date anywhere in text: {furthest}")
        return furthest

    logger.debug("No valid expiration date found")
    return None

def extract_with_country_overwrite(text: str, mrz_data: Optional[MRZData] = None) -> ExtractionResult:
    """
    Extraction pipeline: MRZ -> Generic -> Country-specific (with overwrite).
    1. Run MRZStrategy.
    2. Run GenericStrategy to fill in missing fields.
    3. If country is known, run the country-specific strategy and allow it to overwrite any field.
    """
    # 1. MRZ
    mrz_result = MRZStrategy().extract(text, mrz_data)
    # 2. Generic (fills in missing fields)
    generic_result = GenericStrategy().extract(text, mrz_data)
    # Merge: prefer MRZ, then generic
    merged = ExtractionResult(
        number=mrz_result.number or generic_result.number,
        issued_country=mrz_result.issued_country or generic_result.issued_country,
        expiration_date=mrz_result.expiration_date or generic_result.expiration_date,
        confidence=min(mrz_result.confidence, generic_result.confidence),
        validation_errors=mrz_result.validation_errors + generic_result.validation_errors,
        warnings=mrz_result.warnings + generic_result.warnings,
    )
    # 3. Country-specific (overwrite any field)
    country = merged.issued_country
    country_strategies = {
        "EGY": EGYPassportStrategy(),
        "ESP": ESPassportStrategy(),
        "USA": USPassportStrategy(),
        # Add more as needed
    }
    if country in country_strategies:
        country_result = country_strategies[country].extract(text, mrz_data)
        # Overwrite any field if country-specific result has it
        merged.number = country_result.number or merged.number
        merged.issued_country = country_result.issued_country or merged.issued_country
        merged.expiration_date = country_result.expiration_date or merged.expiration_date
        merged.confidence = min(merged.confidence, country_result.confidence)
        merged.validation_errors += country_result.validation_errors
        merged.warnings += country_result.warnings
    return merged

# Recommend using extract_with_country_overwrite for passport extraction.

print(cv2.__version__)
print(hasattr(cv2, 'fastNlMeansDenoising'))