import pdfplumber
import fitz  # PyMuPDF
import re
from typing import Dict, List, Any

# ─── Key financial patterns to hunt for ───────────────────────────────────────
PATTERNS = {
    "revenue":       r"(?:total\s+(?:revenue|income|turnover|sales))[^\d₹]*([\d,]+(?:\.\d+)?)\s*(?:cr|lakh|lakhs|crore|crores)?",
    "net_profit":    r"(?:net\s+profit|profit\s+after\s+tax|pat)[^\d₹]*([\d,]+(?:\.\d+)?)\s*(?:cr|lakh|lakhs|crore|crores)?",
    "ebitda":        r"(?:ebitda|operating\s+profit)[^\d₹]*([\d,]+(?:\.\d+)?)\s*(?:cr|lakh|lakhs|crore|crores)?",
    "total_assets":  r"(?:total\s+assets)[^\d₹]*([\d,]+(?:\.\d+)?)\s*(?:cr|lakh|lakhs|crore|crores)?",
    "total_debt":    r"(?:total\s+(?:debt|borrowings|liabilities))[^\d₹]*([\d,]+(?:\.\d+)?)\s*(?:cr|lakh|lakhs|crore|crores)?",
    "equity":        r"(?:shareholders?[\s']*equity|net\s+worth|total\s+equity)[^\d₹]*([\d,]+(?:\.\d+)?)\s*(?:cr|lakh|lakhs|crore|crores)?",
    "current_ratio": r"(?:current\s+ratio)[^\d]*([\d.]+)",
    "debt_equity":   r"(?:debt[\s/]+equity|d/e\s+ratio)[^\d]*([\d.]+)",
}

YEAR_PATTERN = re.compile(r"(?:FY|F\.Y\.|financial\s+year)\s*(\d{2,4}[-–]\d{2,4})", re.IGNORECASE)
CIN_PATTERN  = re.compile(r"\b([UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b")
PAN_PATTERN  = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b")


def _clean_number(raw: str) -> float:
    """Strip commas and convert to float."""
    try:
        return float(raw.replace(",", "").strip())
    except Exception:
        return 0.0


def _normalize_to_crore(value: float, unit_hint: str) -> float:
    """Normalize lakh-scale numbers to crores."""
    unit = unit_hint.lower()
    if "lakh" in unit:
        return round(value / 100, 2)
    return round(value, 2)


def extract_text_from_pdf(filepath: str) -> str:
    """Extract all text from a PDF using pdfplumber (best for digital PDFs)."""
    full_text = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)
        return "\n".join(full_text)
    except Exception as e:
        # Fallback to PyMuPDF
        try:
            doc = fitz.open(filepath)
            for page in doc:
                full_text.append(page.get_text())
            return "\n".join(full_text)
        except Exception as e2:
            return ""


def extract_tables_from_pdf(filepath: str) -> List[List[List[str]]]:
    """Extract tables from a PDF using pdfplumber."""
    all_tables = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    all_tables.extend(tables)
    except Exception:
        pass
    return all_tables


def extract_financials_from_text(text: str) -> Dict[str, Any]:
    """Run regex patterns over raw text to pull financial KPIs."""
    text_lower = text.lower()
    results = {}

    for key, pattern in PATTERNS.items():
        matches = re.findall(pattern, text_lower)
        if matches:
            # Take first meaningful match
            val = _clean_number(matches[0])
            if val > 0:
                results[key] = val

    # Try to find company name (first non-blank line near top)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    results["company_name"] = lines[0] if lines else "Unknown"

    # CIN
    cin_match = CIN_PATTERN.search(text)
    results["cin"] = cin_match.group(1) if cin_match else None

    # Financial Year mentioned
    fy_matches = YEAR_PATTERN.findall(text)
    results["financial_years"] = list(set(fy_matches)) if fy_matches else []

    return results


def extract_financials_from_tables(tables: List[List[List[str]]]) -> Dict[str, Any]:
    """Try to extract P&L and Balance Sheet data from table structures."""
    extracted = {}
    kw_map = {
        "revenue":     ["revenue", "turnover", "total income", "net sales"],
        "net_profit":  ["net profit", "profit after tax", "pat"],
        "ebitda":      ["ebitda", "operating profit"],
        "total_assets":["total assets"],
        "total_debt":  ["borrowings", "total debt", "loans"],
        "equity":      ["equity", "net worth", "shareholders"],
    }

    for table in tables:
        for row in table:
            if not row or len(row) < 2:
                continue
            label = str(row[0] or "").lower().strip()
            # Find value columns (last non-empty numeric cell)
            value_cell = None
            for cell in reversed(row[1:]):
                if cell and re.search(r"[\d,]+", str(cell)):
                    value_cell = str(cell)
                    break

            if value_cell:
                for key, keywords in kw_map.items():
                    if any(kw in label for kw in keywords):
                        val = _clean_number(re.sub(r"[^\d.,]", "", value_cell))
                        if val > 0 and key not in extracted:
                            extracted[key] = val

    return extracted


def process_annual_report(filepath: str) -> Dict[str, Any]:
    """
    Master function: process an annual report PDF and return
    structured financial data.
    """
    text   = extract_text_from_pdf(filepath)
    tables = extract_tables_from_pdf(filepath)

    # Merge: tables win over regex (more structured)
    text_data  = extract_financials_from_text(text)
    table_data = extract_financials_from_tables(tables)

    merged = {**text_data, **table_data}  # table_data overrides

    # Derived metrics
    rev    = merged.get("revenue", 0)
    profit = merged.get("net_profit", 0)
    debt   = merged.get("total_debt", 0)
    equity = merged.get("equity", 1)
    assets = merged.get("total_assets", 0)

    if rev and profit:
        merged["net_profit_margin_pct"] = round((profit / rev) * 100, 2)
    if debt and equity:
        merged["debt_equity_ratio"] = round(debt / equity, 2)
    if assets and debt:
        merged["debt_to_assets"] = round(debt / assets, 2)

    merged["source"] = "annual_report"
    merged["pages"]  = _count_pages(filepath)
    merged["raw_text_length"] = len(text)

    return merged


def _count_pages(filepath: str) -> int:
    try:
        with pdfplumber.open(filepath) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0
