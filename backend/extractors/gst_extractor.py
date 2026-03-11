import pandas as pd
import re
from typing import Dict, Any, List


# ─── Column name aliases seen in real GSTR exports ────────────────────────────
TAXABLE_ALIASES   = ["taxable value", "taxable amount", "taxable turnover", "taxable supply"]
TAX_ALIASES       = ["total tax", "igst", "cgst", "sgst", "tax amount", "integrated tax"]
GSTIN_ALIASES     = ["gstin", "gstin of supplier", "gstin/uin", "supplier gstin"]
INVOICE_ALIASES   = ["invoice no", "invoice number", "bill no", "document no"]
MONTH_ALIASES     = ["return period", "month", "tax period", "filing period"]
FILED_DATE_ALIASES= ["date of filing", "filed on", "filing date"]


def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase and strip all column names."""
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df


def _find_col(df: pd.DataFrame, aliases: List[str]) -> str | None:
    """Return the first column name that matches any alias."""
    for alias in aliases:
        for col in df.columns:
            if alias in col:
                return col
    return None


def _to_numeric(series: pd.Series) -> pd.Series:
    """Coerce a series to numeric, stripping ₹ and commas."""
    return pd.to_numeric(
        series.astype(str).str.replace(r"[₹,\s]", "", regex=True),
        errors="coerce"
    ).fillna(0)


# ─── GSTR-3B Parser ───────────────────────────────────────────────────────────
def parse_gstr3b(filepath: str) -> Dict[str, Any]:
    """
    Parse GSTR-3B summary return (usually a single-sheet Excel / CSV).
    Returns: total taxable turnover, total tax paid, filing periods.
    """
    try:
        df = pd.read_excel(filepath) if filepath.endswith((".xlsx", ".xls")) else pd.read_csv(filepath)
    except Exception as e:
        return {"error": str(e), "source": "gstr3b"}

    df = _normalize_cols(df)

    taxable_col = _find_col(df, TAXABLE_ALIASES)
    tax_col     = _find_col(df, TAX_ALIASES)
    month_col   = _find_col(df, MONTH_ALIASES)

    total_taxable = float(_to_numeric(df[taxable_col]).sum()) if taxable_col else 0.0
    total_tax     = float(_to_numeric(df[tax_col]).sum())     if tax_col     else 0.0

    periods = []
    if month_col:
        periods = df[month_col].dropna().astype(str).unique().tolist()

    return {
        "source":          "gstr3b",
        "declared_turnover_lakh": round(total_taxable / 1e5, 2),
        "declared_turnover_crore": round(total_taxable / 1e7, 2),
        "total_tax_paid_lakh": round(total_tax / 1e5, 2),
        "filing_periods":  periods[:12],   # last 12 at most
        "num_rows":        len(df),
        "columns_found":   df.columns.tolist(),
    }


# ─── GSTR-2A Parser ───────────────────────────────────────────────────────────
def parse_gstr2a(filepath: str) -> Dict[str, Any]:
    """
    Parse GSTR-2A (purchase register auto-populated from supplier filings).
    Returns: total purchases, list of suppliers, any mismatches.
    """
    try:
        df = pd.read_excel(filepath) if filepath.endswith((".xlsx", ".xls")) else pd.read_csv(filepath)
    except Exception as e:
        return {"error": str(e), "source": "gstr2a"}

    df = _normalize_cols(df)

    taxable_col = _find_col(df, TAXABLE_ALIASES)
    gstin_col   = _find_col(df, GSTIN_ALIASES)

    total_purchases = float(_to_numeric(df[taxable_col]).sum()) if taxable_col else 0.0

    suppliers = []
    if gstin_col:
        suppliers = df[gstin_col].dropna().unique().tolist()[:50]

    return {
        "source":               "gstr2a",
        "total_purchases_crore": round(total_purchases / 1e7, 2),
        "unique_suppliers":      len(suppliers),
        "supplier_gstins":       suppliers,
        "num_rows":              len(df),
    }


# ─── Cross-check: GSTR-3B vs GSTR-2A ─────────────────────────────────────────
def cross_check_gst(gstr3b: Dict, gstr2a: Dict) -> Dict[str, Any]:
    """
    Identify circular trading / revenue inflation signals by comparing
    declared sales (3B) against purchase data (2A).
    """
    sales     = gstr3b.get("declared_turnover_crore", 0)
    purchases = gstr2a.get("total_purchases_crore", 0)

    if sales == 0:
        return {"status": "insufficient_data", "flags": []}

    gross_margin_pct = round(((sales - purchases) / sales) * 100, 1) if sales else 0
    flags = []

    # Red flag: gross margin below 2% for a trading company suggests circular trading
    if purchases > 0 and gross_margin_pct < 2:
        flags.append({
            "type":     "CIRCULAR_TRADING_RISK",
            "severity": "HIGH",
            "detail":   f"Gross margin of {gross_margin_pct}% is suspiciously low. "
                        f"Sales ₹{sales}Cr vs Purchases ₹{purchases}Cr. "
                        "Possible circular trading — same invoices routed through multiple entities."
        })

    # Warning: purchases > sales (claiming more input credit than output tax)
    if purchases > sales * 1.05:
        flags.append({
            "type":     "EXCESS_INPUT_CREDIT",
            "severity": "MEDIUM",
            "detail":   f"Purchases (₹{purchases}Cr) exceed sales (₹{sales}Cr) by >5%. "
                        "Possible fake invoice claims for input tax credit."
        })

    # Healthy signal
    if not flags:
        flags.append({
            "type":     "CLEAN",
            "severity": "LOW",
            "detail":   f"GST data appears consistent. Gross margin {gross_margin_pct}% is within normal range."
        })

    return {
        "declared_sales_crore":     sales,
        "declared_purchases_crore": purchases,
        "gross_margin_pct":         gross_margin_pct,
        "flags":                    flags,
        "status":                   "flagged" if any(f["severity"] in ("HIGH","MEDIUM") for f in flags) else "clean",
    }


# ─── GST Compliance Score ─────────────────────────────────────────────────────
def gst_compliance_score(gstr3b: Dict) -> Dict[str, Any]:
    """
    Compute a simple GST compliance score based on filing regularity.
    12 months filed on time = 100%. Each missing month = -8.3 pts.
    """
    periods = gstr3b.get("filing_periods", [])
    filed   = len(periods)
    expected = 12
    score = round((filed / expected) * 100, 1)

    return {
        "months_filed":    filed,
        "months_expected": expected,
        "compliance_pct":  score,
        "rating":          "Excellent" if score >= 95 else "Good" if score >= 85 else "Average" if score >= 70 else "Poor",
    }
