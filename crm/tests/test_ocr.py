import pytesseract
import logging
import os
from PIL import Image, ImageEnhance, ImageFilter

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def preprocess_image(image):
    # Convert to grayscale
    image = image.convert('L')
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)
    
    # Enhance brightness
    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(1.5)
    
    # Apply sharpening
    image = image.filter(ImageFilter.SHARPEN)
    
    # Apply thresholding
    image = image.point(lambda x: 0 if x < 128 else 255, '1')
    
    return image

def test_ocr():
    # Test with a document
    image_path = 'documents/PHOTO-2025-06-05-10-44-02.jpg'
    
    if not os.path.exists(image_path):
        logger.error(f"Image file not found: {image_path}")
        return
        
    logger.debug(f"Reading image: {image_path}")
    
    # Open and preprocess the image
    image = Image.open(image_path)
    processed_image = preprocess_image(image)
    
    # Save processed image for debugging
    processed_image.save('processed_image.png')
    
    # Extract text with Tesseract
    text = pytesseract.image_to_string(processed_image, config='--psm 6')
    
    # Print results
    logger.debug("\nExtracted text:")
    logger.debug(text)

if __name__ == "__main__":
    test_ocr() 