"""
eCourts Litigation Research Agent
Searches Indian court records for cases involving company or promoters.
Uses eCourts public portal — graceful fallback if blocked.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "text/html,application/xhtml+xml",
}

HIGH_RISK_KEYWORDS = [
    "cheque dishonour", "section 138", "negotiable instrument",
    "money recovery", "debt recovery", "winding up", "insolvency",
    "ibc", "nclt", "fraud", "cheating", "criminal breach of trust",
    "money laundering", "bank fraud", "wilful default"
]
MEDIUM_RISK_KEYWORDS = [
    "civil suit", "recovery suit", "arbitration",
    "labour dispute", "consumer complaint", "tax appeal"
]

STATE_CODES = {
    "rajasthan": "24", "maharashtra": "14", "gujarat": "7",
    "delhi": "4",      "karnataka": "9",    "tamil nadu": "25",
    "andhra pradesh": "1", "telangana": "31", "punjab": "21",
    "haryana": "8",    "uttar pradesh": "27", "west bengal": "30",
    "madhya pradesh": "13", "kerala": "10",  "odisha": "19",
}


def _classify_severity(case_type: str) -> str:
    ct = case_type.lower()
    for kw in HIGH_RISK_KEYWORDS:
        if kw in ct: return "HIGH"
    for kw in MEDIUM_RISK_KEYWORDS:
        if kw in ct: return "MEDIUM"
    return "LOW"


def _assess_overall_risk(cases: List[Dict]) -> str:
    if not cases: return "LOW"
    if any(c.get("severity") == "HIGH"   for c in cases): return "HIGH"
    if sum(1 for c in cases if c.get("severity") == "MEDIUM") >= 2: return "MEDIUM"
    return "LOW"


def _parse_cases_from_html(html: str) -> List[Dict]:
    cases = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for table in soup.find_all("table"):
            rows = table.find_all("tr")[1:]
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 3:
                    case_type = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    cases.append({
                        "case_no":   cells[0].get_text(strip=True),
                        "case_type": case_type,
                        "filed_on":  cells[2].get_text(strip=True) if len(cells) > 2 else "",
                        "court":     cells[3].get_text(strip=True) if len(cells) > 3 else "",
                        "status":    cells[4].get_text(strip=True) if len(cells) > 4 else "Pending",
                        "severity":  _classify_severity(case_type),
                    })
    except Exception:
        pass
    return cases


def search_ecourts_party(party_name: str, state: str = None) -> Dict[str, Any]:
    """
    Search eCourts for cases by party name.
    Returns cases with severity classification.
    Falls back to clean result if portal is unreachable.
    """
    result = {
        "source":     "ecourts",
        "party":      party_name,
        "cases":      [],
        "case_count": 0,
        "risk_level": "LOW",
        "status":     "pending",
    }

    state_code = STATE_CODES.get((state or "").lower(), "0")

    # ── Attempt: eCourts party name search ───────────────────────────────────
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        resp = session.post(
            "https://services.ecourts.gov.in/ecourtindiaHC/cases/party_name",
            data={
                "party_name": party_name,
                "party_type": "petitioner",
                "state_code": state_code,
                "dist_code":  "0",
                "court_code": "0",
                "from_date":  "01-01-2015",
                "to_date":    "",
            },
            timeout=12,
        )

        if resp.status_code == 200:
            cases = _parse_cases_from_html(resp.text)
            result.update({
                "cases":      cases,
                "case_count": len(cases),
                "risk_level": _assess_overall_risk(cases),
                "status":     "success",
            })
            return result

    except Exception as e:
        result["scrape_error"] = str(e)

    # ── Fallback: NJDG summary search ─────────────────────────────────────────
    try:
        resp = requests.get(
            "https://njdg.ecourts.gov.in/njdgnew/index.php",
            params={"p": "main/pend_dashboard"},
            headers=HEADERS,
            timeout=8,
        )
        # NJDG doesn't expose party search easily — return clean with note
    except Exception:
        pass

    # ── Final fallback: return clean/unknown ─────────────────────────────────
    result.update({
        "status":     "manual_required",
        "risk_level": "UNKNOWN",
        "cases":      [],
        "case_count": 0,
        "message":    "eCourts search requires manual verification.",
        "manual_url": "https://services.ecourts.gov.in/ecourtindiaHC/cases/party_name",
    })
    return result
