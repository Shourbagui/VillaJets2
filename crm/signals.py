import io, re, tempfile, mimetypes, logging, os
from datetime import date, datetime
from typing import Optional, Dict
from django.db.models.signals import pre_save
from django.dispatch import receiver

import filetype
import dateparser
from PIL import Image
import pytesseract

try:
    from pdfminer.high_level import extract_text
except ImportError:
    extract_text = None

try:
    from pdf2image import convert_from_bytes, convert_from_path
except ImportError:
    convert_from_bytes = None

try:
    from passporteye import read_mrz
except ImportError:
    read_mrz = None  # Optional dependency

from .models import Document, NUMBER_CLEAN_REGEX # Import Document model and regex


# Import the new pipeline function
from .helpers.doc_extract import extract_document_data_with_mrz

# Configure logging for potential issues in extraction
logger = logging.getLogger(__name__)

def extract_document_data(document_instance: Document) -> Optional[Dict[str, object]]:
    """Inspect Document instance, extract number / issued_country / expiration_date using the pipeline."""
    logger.debug(f"extract_document_data called for Document pk: {document_instance.pk}, doc_type: {document_instance.document_type}")
    if not document_instance.file:
        logger.debug("extract_document_data: No file on instance.")
        return None # No file to process

    extracted_data = {
        "number": None,
        "issued_country": None,
        "expiration_date": None
    }
    
    try:
        # Read the file content
        # Ensure we are at the beginning of the file
        document_instance.file.seek(0)
        file_content = document_instance.file.read()
        logger.debug(f"Read {len(file_content)} bytes from file.")
        logger.debug(f"[SIGNAL] Calling extract_document_data_with_mrz with doc_type={document_instance.document_type}, file_content_len={len(file_content)}")
        
        # Call the new extraction function (uses both OCR and MRZ)
        pipeline_data = extract_document_data_with_mrz(file_content, document_instance.document_type)
        if pipeline_data:
            extracted_data.update(pipeline_data)

        logger.debug(f"extract_document_data: Pipeline returned: {extracted_data}")
        return extracted_data

    except Exception as e:
        logger.error(f"Error during document extraction process: {e}")
        logger.debug(f"extract_document_data: Error during extraction: {e}")
        # Return partial data if we have any
        if any(extracted_data.values()):
            return extracted_data
        return None

@receiver(pre_save, sender=Document)
def pre_save_document_extract_data(sender, instance, **kwargs):
    """Signal receiver to extract data from document before saving."""
    logger.debug(f"pre_save_document_extract_data signal received for Document pk: {instance.pk}")
    if instance.file and not isinstance(instance.file, bool): # Check if file exists and is not being cleared
         logger.debug("pre_save_document_extract_data: File found on instance.")
         # Check if it's a new object or file has changed - simplified check
         # We should also re-extract if key fields are empty, even if file hasn't changed
         needs_extraction = (
             instance.pk is None or 
             (instance.pk is not None and hasattr(instance, '_original_file') and instance.file != instance._original_file) or
             not instance.number or not instance.document_country or not instance.expiration_date
         )
         
         if needs_extraction:
              logger.debug("pre_save_document_extract_data: New object, file changed, or key fields empty. Attempting extraction.")
              extracted_data = extract_document_data(instance)
              if extracted_data:
                  logger.debug(f"pre_save_document_extract_data: Extraction successful, populating fields: {extracted_data}")
                  # Only update if a value was extracted, to avoid clearing existing manual data
                  if extracted_data.get('number') is not None:
                      instance.number = extracted_data['number']
                  if extracted_data.get('document_country') is not None:
                      instance.document_country = extracted_data['document_country']
                  if extracted_data.get('expiration_date') is not None:
                      instance.expiration_date = extracted_data['expiration_date']
              else:
                  logger.debug("pre_save_document_extract_data: Extraction returned no data.")
         else:
              logger.debug("pre_save_document_extract_data: Existing object, file not changed, extraction fields populated. Skipping extraction.")
    else:
        logger.debug("pre_save_document_extract_data: No file on instance or file being cleared, skipping extraction.")

@receiver(pre_save, sender=Document)
def clean_document_number(sender, instance, **kwargs):
    if instance.number:
        instance.number = NUMBER_CLEAN_REGEX.sub('', instance.number)

# Need to ensure signals are imported and connected. Typically done in apps.py ready method.
# See crm/apps.py where this will be handled next. 