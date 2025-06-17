import re
import logging
import tempfile
import os
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List, Pattern
import dateparser
import pycountry
import unicodedata
import filetype
from PIL import Image
import pytesseract
from pdfminer.high_level import extract_text
from pdf2image import convert_from_path
from .strategies import (
    get_strategy, 
    GenericStrategy, 
    MRZData,
    MRZStrategy,
    VisaStrategy
)
import cv2
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)

# --- Country Extraction Logic (Moved from crm/document_country.py) ---

# Keywords for identifying issuing country lines (whitelist)
COUNTRY_KEYWORDS = ("ISSUING COUNTRY", "COUNTRY OF ISSUE", "NATIONALITY", "COUNTRY", "STATE")

# Keywords for identifying non-country lines (blacklist)
NON_COUNTRY_KEYWORDS = ("PLACE OF BIRTH", "DATE OF BIRTH", "PLACE OF ISSUE", "DATE OF ISSUE") # Added common variations

# High-confidence regex for 3-letter country codes near country keywords
COUNTRY_RE = re.compile(r'(?:' + '|'.join(COUNTRY_KEYWORDS) + r')\s*[:\s]*([A-Z]{3})', re.IGNORECASE)

# Generic regex for any 3-letter sequence that might be a country code
GENERIC_COUNTRY_RE = re.compile(r'\b([A-Z]{3})\b')

# Set of all valid country codes (ISO-3)
COUNTRY_CODES = {
    "USA", "GBR", "FRA", "DEU", "ITA", "ESP", "POL", "NLD", "BEL", "CHE",
    "AUT", "SWE", "NOR", "DNK", "FIN", "PRT", "GRC", "IRL", "LUX", "ISL",
    "MLT", "CYP", "EST", "LVA", "LTU", "SVK", "SVN", "HRV", "ROU", "BGR",
    "HUN", "CZE", "MEX", "CAN", "AUS", "NZL", "JPN", "KOR", "CHN", "IND",
    "BRA", "ZAF", "RUS", "TUR", "SAU", "ARE", "QAT", "KWT", "BHR", "OMN"
}

def preprocess_image_for_ocr(pil_img: Image.Image) -> Image.Image:
    """
    Preprocess a PIL image for OCR: denoise, binarize, deskew, resize, sharpen, and remove borders.
    Returns a new PIL Image.
    """
    img = np.array(pil_img.convert('L'))  # Convert to grayscale

    # 1. Denoising
    img = cv2.fastNlMeansDenoising(img, None, 30, 7, 21)

    # 2. Binarization (Otsu's thresholding)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 3. Deskewing
    coords = np.column_stack(np.where(img < 255))
    if coords.size > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        (h, w) = img.shape
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # 4. Resize (upscale if small)
    h, w = img.shape
    if min(h, w) < 800:
        scale = 800.0 / min(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # 5. Sharpening
    kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
    img = cv2.filter2D(img, -1, kernel)

    # 6. Border removal (find largest contour and crop)
    contours, _ = cv2.findContours(255 - img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        c = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(c)
        img = img[y:y+h, x:x+w]

    return Image.fromarray(img)

def _extract_from_image(file_path: str) -> str:
    """Extract text from image file path using Tesseract (no advanced preprocessing)."""
    try:
        img = Image.open(file_path)
        logger.debug(f"Opened image file: {file_path}")

        # Use Tesseract with optimized settings (no preprocessing)
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, config=custom_config)
        logger.debug(f"Tesseract extracted text (length: {len(text)}): {text}")
        return text
    except Exception as e:
        logger.error(f"Tesseract OCR extraction failed for file {file_path}: {e}")
        return ""

def _extract_from_pdf(file_path: str) -> str:
    """Extract text from PDF file path, with OCR fallback."""
    text = ""
    if extract_text:
        try:
            text = extract_text(file_path)
            logger.debug(f"PDFMiner extracted text (length: {len(text)}): {text[:500]}...")
        except Exception as e:
            logger.warning(f"PDFMiner text extraction failed for file {file_path}: {e}")

    # Fallback to OCR if text is minimal or extraction failed, or if PDFMiner is not available
    if (not text or len(text.strip()) < 50 or extract_text is None) and convert_from_path:
        logger.info("Performing OCR on PDF from file path.")
        try:
            images = convert_from_path(file_path)
            ocr_text_parts = []
            for i, image in enumerate(images):
                logger.debug(f"Processing image from PDF page {i+1}")
                # Save image to temp file for OCR
                temp_img_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                image.save(temp_img_file.name, 'PNG')
                temp_img_file.close()
                
                try:
                    ocr_text = _extract_from_image(temp_img_file.name)
                    ocr_text_parts.append(ocr_text)
                    logger.debug(f"Raw OCR text from PDF page {i+1} (length: {len(ocr_text)}): {ocr_text[:500]}...")
                finally:
                    if os.path.exists(temp_img_file.name):
                        os.unlink(temp_img_file.name)
                        
            text = "\n".join(ocr_text_parts) # Join text from multiple pages
        except Exception as e:
            logger.error(f"PDF to image conversion or OCR failed for file {file_path}: {e}")
    elif not convert_from_path:
         logger.warning("pdf2image not installed or convert_from_path not available. Cannot perform PDF OCR fallback from path.")

    return text 

def _extract_text(file_content: bytes) -> str:
    """Extract text from image or PDF bytes using the appropriate method."""
    kind = filetype.guess(file_content)
    if not kind:
        return ""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(file_content)
        temp_file_path = temp_file.name
    try:
        if kind.mime.startswith('image/'):
            return _extract_from_image(temp_file_path)
        elif kind.mime == 'application/pdf':
            return _extract_from_pdf(temp_file_path)
        else:
            return ""
    finally:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

def _pipeline_extract(file_content: bytes, doc_type: str, raw_mrz_data: Optional[Dict] = None) -> Optional[Dict[str, object]]:
    """Extract document data using the pipeline approach."""
    try:
        # 1. OCR text extraction
        text = _extract_text(file_content)
        if not text:
            logger.error("OCR text extraction failed")
            return None

        # 2. MRZ data standardization (if available)
        mrz_data_obj = None
        if raw_mrz_data and isinstance(raw_mrz_data, Dict):
             try:
                  mrz_data_obj = MRZData(
                       document_type=raw_mrz_data.get("document_type"),
                       country_code=raw_mrz_data.get("issuing_state"), # Map issuing_state to country_code
                       number=raw_mrz_data.get("number"),
                       expiration_date=raw_mrz_data.get("expiration_date"),
                       expiration_date_str=raw_mrz_data.get("expiration_date_str")
                       # Add mapping for other relevant MRZ fields here
                  )
                  logger.debug("Successfully created standardized MRZData object.")
             except Exception as e:
                  logger.error(f"Failed to create MRZData object from raw dictionary: {e}")
                  # Continue with extraction but without standardized MRZ data
                  mrz_data_obj = None
        elif raw_mrz_data is not None:
             logger.warning(f"Expected raw_mrz_data to be a dictionary, but received {type(raw_mrz_data)}.")

        # 3. Strategy selection and chaining
        primary_strategy = get_strategy(doc_type)
        if not primary_strategy:
             logger.warning(f"get_strategy returned None for doc_type: {doc_type}. Falling back to Generic.")
             primary_strategy = GenericStrategy()

        # Set up fallback hierarchy based on document type
        file_path = None
        temp_file = None

        # Detect file type and create appropriate temp file
        kind = filetype.guess(file_content)
        if kind:
            if kind.mime.startswith('image/'):
                # For images, save as jpg
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                    tmp.write(file_content)
                    file_path = tmp.name
                    temp_file = tmp.name
                    logger.debug(f"[PIPELINE] Created temp image file for {doc_type}: {file_path}")
            elif kind.mime == 'application/pdf':
                # For PDFs, convert first page to image
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as pdf_tmp:
                        pdf_tmp.write(file_content)
                        pdf_path = pdf_tmp.name
                    
                    # Convert first page to image
                    images = convert_from_path(pdf_path)
                    if images:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as img_tmp:
                            images[0].save(img_tmp.name, 'JPEG')
                            file_path = img_tmp.name
                            temp_file = img_tmp.name
                            logger.debug(f"[PIPELINE] Converted PDF to image for {doc_type}: {file_path}")
                    
                    # Clean up PDF temp file
                    try:
                        os.remove(pdf_path)
                    except Exception as e:
                        logger.warning(f"[PIPELINE] Failed to clean up PDF temp file {pdf_path}: {e}")
                except Exception as e:
                    logger.error(f"[PIPELINE] Failed to convert PDF to image: {e}")
            else:
                logger.warning(f"[PIPELINE] Unsupported file type: {kind.mime}")
        else:
            logger.warning("[PIPELINE] Could not detect file type")

        if doc_type == "PASSPORT":
            logger.debug(f"[PIPELINE] PASSPORT: file_path={file_path}, doc_type={doc_type}")
            mrz_strategy = MRZStrategy()
            generic_strategy = GenericStrategy()
            if mrz_data_obj and mrz_data_obj.country_code:
                country_strategy = get_strategy(f"PASSPORT_{mrz_data_obj.country_code}")
                if country_strategy:
                    mrz_strategy.add_fallback_strategy(country_strategy)
            mrz_strategy.add_fallback_strategy(generic_strategy)
            primary_strategy = mrz_strategy
            result = primary_strategy.chain_strategies(text, mrz_data_obj, file_path=file_path)
        elif doc_type == "ID_CARD":
            logger.debug(f"[PIPELINE] ID_CARD: file_path={file_path}, doc_type={doc_type}")
            if mrz_data_obj and mrz_data_obj.country_code:
                country_strategy = get_strategy(f"ID_{mrz_data_obj.country_code}")
                if country_strategy:
                    mrz_strategy = MRZStrategy()
                    generic_strategy = GenericStrategy()
                    country_strategy.add_fallback_strategy(mrz_strategy)
                    country_strategy.add_fallback_strategy(generic_strategy)
                    primary_strategy = country_strategy
            result = primary_strategy.chain_strategies(text, mrz_data_obj, file_path=file_path)
        elif doc_type == "VISA":
            logger.debug(f"[PIPELINE] VISA: file_path={file_path}, doc_type={doc_type}")
            visa_strategy = VisaStrategy()
            mrz_strategy = MRZStrategy()
            generic_strategy = GenericStrategy()
            visa_strategy.add_fallback_strategy(mrz_strategy)
            visa_strategy.add_fallback_strategy(generic_strategy)
            primary_strategy = visa_strategy
            result = primary_strategy.chain_strategies(text, mrz_data_obj, file_path=file_path)
        else:
            result = primary_strategy.chain_strategies(text, mrz_data_obj, file_path=file_path)

        # Clean up temp file after all strategies are done
        if temp_file:
            try:
                os.remove(temp_file)
                logger.debug(f"[PIPELINE] Cleaned up temp file: {temp_file}")
            except Exception as e:
                logger.warning(f"[PIPELINE] Failed to clean up temp file {temp_file}: {e}")

        logger.debug(f"Strategy chain completed with result: {result}")

        # 5. Convert result to dictionary
        extracted_data = {
            "number": result.number,
            "document_country": getattr(result, 'document_country', None) or getattr(result, 'issued_country', None) or getattr(result, 'country', None),
            "expiration_date": result.expiration_date,
            "confidence": getattr(result, 'confidence', None),
            "validation_errors": getattr(result, 'validation_errors', []),
            "warnings": getattr(result, 'warnings', []),
        }

        return extracted_data

    except Exception as e:
        logger.error(f"Error in _pipeline_extract: {str(e)}")
        return None

def extract_document_data_with_mrz(file_content: bytes, doc_type: str) -> Optional[Dict[str, object]]:
    """
    Extract document data using OCR, MRZ extraction (if possible), and the pipeline.
    This function ensures MRZStrategy receives a parsed MRZ object, while other strategies use the raw OCR text.
    """
    # 1. Extract OCR text
    ocr_text = _extract_text(file_content)

    # 2. Extract MRZ lines from OCR text
    def extract_mrz_lines_from_text(text: str):
        # Heuristic: lines with lots of '<' and length ~30-50
        lines = text.splitlines()
        mrz_lines = [line for line in lines if line.count('<') > 10 and 30 <= len(line) <= 50]
        return mrz_lines

    mrz_lines = extract_mrz_lines_from_text(ocr_text)

    # 3. Parse MRZ using passporteye (if available)
    raw_mrz_data = None
    try:
        from passporteye import read_mrz
        if mrz_lines:
            mrz = read_mrz('\n'.join(mrz_lines))
            if mrz:
                raw_mrz_data = {
                    "document_type": mrz.type,
                    "issuing_state": mrz.country,
                    "number": mrz.number,
                    "expiration_date": mrz.expiration_date,
                    "expiration_date_str": getattr(mrz, 'expiration_date_str', None)
                }
    except ImportError:
        logger.warning("passporteye is not installed; skipping MRZ parsing.")
    except Exception as e:
        logger.warning(f"Error during MRZ parsing: {e}")

    # 4. Call the pipeline with both OCR and MRZ data
    return _pipeline_extract(file_content, doc_type, raw_mrz_data=raw_mrz_data) 