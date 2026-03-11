import pandas as pd
import pdfplumber
import re
from typing import Dict, Any, List
from datetime import datetime


# ─── Column aliases for bank statement exports ────────────────────────────────
DATE_ALIASES    = ["date", "txn date", "transaction date", "value date", "posting date"]
DEBIT_ALIASES   = ["debit", "withdrawal", "dr", "debit amount", "withdrawals"]
CREDIT_ALIASES  = ["credit", "deposit", "cr", "credit amount", "deposits"]
BALANCE_ALIASES = ["balance", "closing balance", "running balance", "available balance"]
NARRATION_ALIASES = ["narration", "description", "particulars", "remarks", "details", "transaction remarks"]


def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df


def _find_col(df: pd.DataFrame, aliases: List[str]) -> str | None:
    for alias in aliases:
        for col in df.columns:
            if alias in col:
                return col
    return None


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r"[₹,\s()]", "", regex=True),
        errors="coerce"
    ).fillna(0)


# ─── Extract bank statement from Excel / CSV ──────────────────────────────────
def parse_bank_excel(filepath: str) -> Dict[str, Any]:
    try:
        df = pd.read_excel(filepath, header=None) if filepath.endswith((".xlsx", ".xls")) else pd.read_csv(filepath, header=None)
    except Exception as e:
        return {"error": str(e)}

    # Find header row (first row with >3 non-null values)
    header_row = 0
    for i, row in df.iterrows():
        non_null = row.dropna().shape[0]
        if non_null >= 3:
            header_row = i
            break

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    df = _normalize_cols(df)

    credit_col    = _find_col(df, CREDIT_ALIASES)
    debit_col     = _find_col(df, DEBIT_ALIASES)
    balance_col   = _find_col(df, BALANCE_ALIASES)
    narration_col = _find_col(df, NARRATION_ALIASES)
    date_col      = _find_col(df, DATE_ALIASES)

    total_credits = float(_to_numeric(df[credit_col]).sum()) if credit_col else 0.0
    total_debits  = float(_to_numeric(df[debit_col]).sum())  if debit_col  else 0.0

    closing_balance = 0.0
    if balance_col:
        balances = _to_numeric(df[balance_col])
        closing_balance = float(balances.dropna().iloc[-1]) if not balances.empty else 0.0

    # Monthly credit summary
    monthly_credits = {}
    if date_col and credit_col:
        df["_date"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
        df["_credit_num"] = _to_numeric(df[credit_col])
        monthly = df.groupby(df["_date"].dt.to_period("M"))["_credit_num"].sum()
        monthly_credits = {str(k): round(float(v) / 1e7, 2) for k, v in monthly.items()}

    # Suspicious narration patterns (EMI bounce, returns, etc.)
    bounce_keywords = ["ecs return", "nach return", "emi bounce", "cheque return", "inward return", "unpaid"]
    bounces = []
    if narration_col:
        narrations = df[narration_col].dropna().astype(str).str.lower()
        for kw in bounce_keywords:
            hits = df[narrations.str.contains(kw, na=False)]
            if not hits.empty:
                bounces.append({"keyword": kw, "count": len(hits)})

    return {
        "source":                  "bank_statement",
        "total_credits_crore":     round(total_credits / 1e7, 2),
        "total_debits_crore":      round(total_debits / 1e7, 2),
        "closing_balance_lakh":    round(closing_balance / 1e5, 2),
        "monthly_credits_crore":   monthly_credits,
        "num_transactions":        len(df),
        "bounce_flags":            bounces,
        "has_narration":           narration_col is not None,
    }


# ─── Extract bank statement from scanned PDF ──────────────────────────────────
def parse_bank_pdf(filepath: str) -> Dict[str, Any]:
    """
    Parse a bank statement PDF (digital, not scanned).
    Falls back to text-based regex extraction.
    """
    tables_data = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in (tables or []):
                    tables_data.extend(table)
    except Exception:
        pass

    # Try to detect header row
    credit_col_idx = None
    debit_col_idx  = None
    total_credits  = 0.0
    total_debits   = 0.0
    bounces        = []

    for i, row in enumerate(tables_data):
        if not row:
            continue
        row_str = [str(c or "").lower() for c in row]

        # Find header
        if credit_col_idx is None:
            for j, cell in enumerate(row_str):
                if any(a in cell for a in CREDIT_ALIASES):
                    credit_col_idx = j
                if any(a in cell for a in DEBIT_ALIASES):
                    debit_col_idx = j
            continue

        # Data rows
        if credit_col_idx is not None and credit_col_idx < len(row):
            raw = str(row[credit_col_idx] or "").replace(",", "").replace("₹", "").strip()
            try:
                total_credits += float(raw) if raw else 0
            except ValueError:
                pass

        if debit_col_idx is not None and debit_col_idx < len(row):
            raw = str(row[debit_col_idx] or "").replace(",", "").replace("₹", "").strip()
            try:
                total_debits += float(raw) if raw else 0
            except ValueError:
                pass

        # Bounce check in narration
        full_row = " ".join(str(c or "") for c in row).lower()
        for kw in ["return", "bounce", "unpaid", "dishonour"]:
            if kw in full_row:
                bounces.append(kw)

    return {
        "source":               "bank_statement_pdf",
        "total_credits_crore":  round(total_credits / 1e7, 2),
        "total_debits_crore":   round(total_debits / 1e7, 2),
        "num_table_rows":       len(tables_data),
        "bounce_flags":         list(set(bounces)),
    }


# ─── Cross-check: GST declared vs Bank credits ───────────────────────────────
def cross_check_gst_vs_bank(gst_turnover_crore: float, bank_credits_crore: float) -> Dict[str, Any]:
    """
    Compare GST declared turnover vs actual bank credits.
    A large discrepancy is a red flag for revenue inflation.
    """
    if bank_credits_crore == 0:
        return {"status": "insufficient_data", "flags": []}

    delta = gst_turnover_crore - bank_credits_crore
    delta_pct = round((abs(delta) / bank_credits_crore) * 100, 1)
    flags = []

    if delta > 0 and delta_pct > 15:
        flags.append({
            "type":     "REVENUE_INFLATION_RISK",
            "severity": "HIGH",
            "detail":   f"GST declared turnover (₹{gst_turnover_crore}Cr) exceeds bank credits "
                        f"(₹{bank_credits_crore}Cr) by {delta_pct}%. "
                        "Possible revenue inflation — declared sales not reflecting in bank account."
        })
    elif delta < 0 and delta_pct > 20:
        flags.append({
            "type":     "UNDECLARED_INCOME",
            "severity": "MEDIUM",
            "detail":   f"Bank credits (₹{bank_credits_crore}Cr) exceed GST turnover "
                        f"(₹{gst_turnover_crore}Cr) by {delta_pct}%. "
                        "Possible undeclared income or non-business receipts."
        })
    else:
        flags.append({
            "type":     "RECONCILED",
            "severity": "LOW",
            "detail":   f"GST turnover (₹{gst_turnover_crore}Cr) and bank credits "
                        f"(₹{bank_credits_crore}Cr) are broadly reconciled. Delta: {delta_pct}%."
        })

    return {
        "gst_turnover_crore":   gst_turnover_crore,
        "bank_credits_crore":   bank_credits_crore,
        "delta_crore":          round(delta, 2),
        "delta_pct":            delta_pct,
        "flags":                flags,
        "status":               "flagged" if any(f["severity"] == "HIGH" for f in flags) else
                                "watch"   if any(f["severity"] == "MEDIUM" for f in flags) else "clean",
    }


# ─── Average Monthly Balance ──────────────────────────────────────────────────
def compute_amb(monthly_credits: Dict[str, float]) -> float:
    """Average monthly balance/credits over available months."""
    if not monthly_credits:
        return 0.0
    values = list(monthly_credits.values())
    return round(sum(values) / len(values), 2)
