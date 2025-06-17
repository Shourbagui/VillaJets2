print("Loading crm/models.py")

from django.db import models
from django.contrib.auth import get_user_model
import io, re, tempfile, mimetypes, logging
from datetime import date
from typing import Optional, Dict

import filetype
import dateparser
from PIL import Image
import pytesseract

try:
    from pdfminer.high_level import extract_text
except ImportError:
    extract_text = None

try:
    from pdf2image import convert_from_bytes
except ImportError:
    convert_from_bytes = None

try:
    from passporteye import read_mrz
except ImportError:
    read_mrz = None  # Optional dependency

# Configure logging for potential issues in extraction
logger = logging.getLogger(__name__)

# Helper functions

def _extract_mrz(content: bytes) -> Optional[Dict[str, object]]:
    """Extract data using passporteye MRZ."""
    if read_mrz is None:
        logger.warning("passporteye not installed. Cannot perform MRZ extraction.")
        return None
    try:
        mrz_data = read_mrz(content)
        if mrz_data and mrz_data.valid:
            return {
                "number": mrz_data.number,
                "issued_country": mrz_data.country,
                "expiration_date": dateparser.parse(mrz_data.date_of_expiry, settings={'DATE_ORDER': 'YMD'}).date() if mrz_data.date_of_expiry else None,
            }
    except Exception as e:
        logger.error(f"MRZ extraction failed: {e}")
    return None

def _extract_from_pdf(content: bytes) -> str:
    """Extract text from PDF, with OCR fallback."""
    text = ""
    if extract_text:
        try:
            text = extract_text(io.BytesIO(content))
        except Exception as e:
             logger.warning(f"PDFMiner text extraction failed: {e}")

    # Fallback to OCR if text is minimal or extraction failed
    if (not text or len(text.strip()) < 50) and convert_from_bytes:
        logger.info("Performing OCR on PDF.")
        try:
            with tempfile.TemporaryDirectory() as path:
                images = convert_from_bytes(content)
                for i, image in enumerate(images):
                    text += pytesseract.image_to_string(image)
        except Exception as e:
            logger.error(f"PDF OCR extraction failed: {e}")
    elif not convert_from_bytes:
         logger.warning("pdf2image not installed. Cannot perform PDF OCR fallback.")

    return text

def _extract_from_image(content: bytes) -> str:
    """Extract text from image using OCR."""
    try:
        img = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        logger.error(f"Image OCR extraction failed: {e}")
        return ""

def _postprocess(text: str) -> Optional[Dict[str, object]]:
    """Extract data from text using regex and parse date."""
    if not text:
        return None

    extracted_data = {}

    # Regex for Number (Passport/ID or DL) - adjust based on expected types
    number_match = re.search(r'\b([A-Z0-9]{6,12})\b', text, re.IGNORECASE)
    if number_match:
        extracted_data["number"] = number_match.group(1)

    # Regex for Country (ISO-3166 alpha-3 recommended) - adjust as needed
    country_match = re.search(r'\b(?:Country|Nationality)[:\s]*([A-Z]{3})\b', text, re.IGNORECASE)
    if country_match:
        extracted_data["issued_country"] = country_match.group(1).upper()

    # Regex for Expiration date
    expiration_match = re.search(r'(?:EXP(?:IRY|\.?)|Expires|Exp\.?)[:\s]*([0-3]?\d[\/\-][01]?\d[\/\-]\d{2,4})', text, re.IGNORECASE)
    if expiration_match:
        date_str = expiration_match.group(1)
        parsed_date = dateparser.parse(date_str)
        if parsed_date:
            extracted_data["expiration_date"] = parsed_date.date()

    return extracted_data if extracted_data else None

NUMBER_CLEAN_REGEX = re.compile(r'[^A-Za-z0-9]')

class Client(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=20, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return self.name
    
class DocumentTypes(models.TextChoices):
    PASSPORT = "passport"
    VISA = "visa"
    ID_CARD = "id_card"

class Document(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=10, choices=DocumentTypes.choices)
    number = models.CharField(max_length=100, null=True, blank=True)
    document_country = models.CharField(max_length=100, null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to="documents/", null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.number:
            self.number = NUMBER_CLEAN_REGEX.sub('', self.number)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.document_type.title()
    
    def is_valid_for_flight(self):
        return self.number and self.document_country and self.expiration_date and self.expiration_date >= date.today()

class LeadStatus(models.TextChoices):
    APPROACH = "approach"
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    LOST = "lost"
    CLOSED = "closed"

class Lead(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=LeadStatus.choices)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Lead for {self.client.name}"
    
class FlightTypes(models.TextChoices):
    INTRATERRITORY = "intraterritory"
    INTERNATIONAL = "international"


class FlightQuote(models.Model):
    client = models.OneToOneField(Client, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    flight_type = models.CharField(max_length=50, choices=FlightTypes.choices)
    waiting_area_required = models.BooleanField(default=False)
    special_requirements = models.TextField(blank=True)

class CustomerFeedbackType(models.TextChoices):
    CHANGE_REQUEST = "change_request"
    COMPLAINT = "complaint"
    SATISFACTION = "satisfaction"

class CustomerFeedback(models.Model):
    from flights.models import Flight
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE)
    feedback_type = models.CharField(max_length=15, choices=models.TextChoices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class Mail(models.Model):
    client = models.ForeignKey('Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='emails')
    sender = models.CharField(max_length=255)
    email = models.EmailField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    subject = models.CharField(max_length=255, db_index=True)
    content = models.TextField()
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Mail from {self.sender} ({self.email})"

class MailSettings(Mail):
    class Meta:
        proxy = True
        verbose_name = "Mail Credentials"
        verbose_name_plural = "Mail Credentials"
