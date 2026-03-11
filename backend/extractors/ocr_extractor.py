import fitz  # PyMuPDF
import io
import re
from typing import Dict, Any, List

# Try to import OCR libraries (optional — graceful fallback if not installed)
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def _pdf_page_to_image(page) -> "Image.Image":
    """Convert a PyMuPDF page to a PIL Image at 300 DPI."""
    mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img_bytes = pix.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))


def _is_scanned(filepath: str, text_threshold: int = 50) -> bool:
    """
    Heuristic: if a PDF has fewer than `text_threshold` characters per page
    on average, it's likely a scanned image-based PDF.
    """
    try:
        doc = fitz.open(filepath)
        total_text = sum(len(page.get_text()) for page in doc)
        avg_chars = total_text / max(len(doc), 1)
        return avg_chars < text_threshold
    except Exception:
        return False


def ocr_pdf(filepath: str, max_pages: int = 10) -> Dict[str, Any]:
    """
    Run Tesseract OCR on a scanned PDF.
    Returns extracted text and page count.
    """
    if not OCR_AVAILABLE:
        return {
            "status":  "ocr_unavailable",
            "message": "pytesseract / Pillow not installed. Run: pip install pytesseract Pillow",
            "text":    "",
        }

    try:
        doc = fitz.open(filepath)
        pages_to_process = min(len(doc), max_pages)
        extracted_pages = []

        for i in range(pages_to_process):
            img = _pdf_page_to_image(doc[i])
            # Tesseract config for financial documents
            config = "--psm 6 -l eng"
            text = pytesseract.image_to_string(img, config=config)
            extracted_pages.append(text)

        full_text = "\n".join(extracted_pages)
        return {
            "status":       "success",
            "pages_ocred":  pages_to_process,
            "total_pages":  len(doc),
            "text":         full_text,
            "char_count":   len(full_text),
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "text": ""}


def ocr_image(filepath: str) -> Dict[str, Any]:
    """
    Run Tesseract OCR on a single image file (JPG, PNG, TIFF).
    """
    if not OCR_AVAILABLE:
        return {"status": "ocr_unavailable", "text": ""}

    try:
        img = Image.open(filepath)
        config = "--psm 6 -l eng"
        text = pytesseract.image_to_string(img, config=config)
        return {"status": "success", "text": text, "char_count": len(text)}
    except Exception as e:
        return {"status": "error", "message": str(e), "text": ""}


def smart_extract(filepath: str) -> Dict[str, Any]:
    """
    Auto-detect whether PDF is digital or scanned.
    Use pdfplumber for digital, Tesseract for scanned.
    """
    if filepath.lower().endswith(".pdf"):
        if _is_scanned(filepath):
            result = ocr_pdf(filepath)
            result["extraction_method"] = "tesseract_ocr"
        else:
            # Use standard extraction (handled by pdf_extractor.py)
            result = {
                "status":             "digital_pdf",
                "extraction_method":  "pdfplumber",
                "message":            "Digital PDF — use pdf_extractor.process_annual_report()"
            }
    elif filepath.lower().endswith((".jpg", ".jpeg", ".png", ".tiff", ".bmp")):
        result = ocr_image(filepath)
        result["extraction_method"] = "tesseract_ocr"
    else:
        result = {"status": "unsupported", "text": "", "extraction_method": "none"}

    return result


def extract_financials_from_ocr_text(text: str) -> Dict[str, Any]:
    """
    Post-process OCR text to extract financial figures.
    OCR text is noisier so we use broader patterns.
    """
    patterns = {
        "revenue":    r"(?:revenue|turnover|sales)[^\d]*([\d,]+(?:\.\d+)?)",
        "net_profit": r"(?:net profit|profit after tax)[^\d]*([\d,]+(?:\.\d+)?)",
        "total_assets": r"total assets[^\d]*([\d,]+(?:\.\d+)?)",
    }

    results = {}
    text_lower = text.lower()

    for key, pattern in patterns.items():
        matches = re.findall(pattern, text_lower)
        if matches:
            try:
                val = float(matches[0].replace(",", ""))
                if val > 0:
                    results[key] = val
            except ValueError:
                pass

    return results
