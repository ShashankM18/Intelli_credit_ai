"""
MCA21 Research Agent
Fetches publicly available company data from MCA21 portal.
Graceful fallback if portal blocks scraping.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Any
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html",
}


def search_company_mca(company_name: str = None, cin: str = None) -> Dict[str, Any]:
    """
    Search MCA21 for company master data.
    Returns: registration status, directors, ROC, paid-up capital.
    Falls back gracefully if portal is unreachable.
    """
    result = {
        "source":   "mca21",
        "searched": company_name or cin,
        "status":   "pending",
    }

    # ── Attempt 1: MCA company master data endpoint ───────────────────────────
    try:
        if cin:
            url = f"https://www.mca.gov.in/mcafoportal/getCompanyDetails.do?companyID={cin.upper().strip()}"
        else:
            cleaned = re.sub(r'\b(pvt|ltd|limited|private|public)\b', '',
                             company_name or "", flags=re.IGNORECASE).strip()
            url = f"https://www.mca.gov.in/mcafoportal/getCompanyDetails.do?companyName={cleaned}"

        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            try:
                data = resp.json()
                result.update({
                    "company_name":       data.get("companyName", ""),
                    "cin":                data.get("cin", cin or ""),
                    "roc":                data.get("rocCode", ""),
                    "registration_date":  data.get("dateOfRegistration", ""),
                    "company_status":     data.get("companyStatus", "Active"),
                    "company_category":   data.get("companyCategory", ""),
                    "paid_up_capital":    data.get("paidUpCapital", ""),
                    "registered_address": data.get("registeredOfficeAddress", ""),
                    "status":             "success",
                })
                return result
            except Exception:
                pass
    except requests.exceptions.RequestException:
        pass

    # ── Attempt 2: Scrape MCA search HTML ────────────────────────────────────
    try:
        resp = requests.post(
            "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do",
            data={"companyName": company_name or "", "companyID": cin or ""},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            parsed = {}
            for table in soup.find_all("table"):
                for row in table.find_all("tr"):
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 2:
                        key   = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        if "company name"  in key: parsed["company_name"]     = value
                        if "cin"           in key: parsed["cin"]               = value
                        if "status"        in key: parsed["company_status"]    = value
                        if "registration"  in key: parsed["registration_date"] = value
                        if "roc"           in key: parsed["roc"]               = value
                        if "paid up"       in key: parsed["paid_up_capital"]   = value
            if parsed:
                result.update({**parsed, "status": "scraped"})
                return result
    except Exception:
        pass

    # ── Fallback: return clean placeholder ───────────────────────────────────
    result.update({
        "status":         "manual_required",
        "company_status": "Unknown",
        "message":        "MCA portal not reachable. Verify manually.",
        "manual_url":     f"https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do",
    })
    return result


def get_company_charges(cin: str) -> Dict[str, Any]:
    """
    Fetch registered charges (liens/mortgages) against company from MCA.
    """
    result = {"source": "mca21_charges", "cin": cin, "charges": [], "charge_count": 0}
    try:
        url  = f"https://www.mca.gov.in/mcafoportal/viewCharges.do?cin={cin}"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            soup   = BeautifulSoup(resp.text, "html.parser")
            charges = []
            for table in soup.find_all("table"):
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        charges.append({
                            "charge_id": cells[0].get_text(strip=True),
                            "holder":    cells[1].get_text(strip=True) if len(cells) > 1 else "",
                            "amount":    cells[2].get_text(strip=True) if len(cells) > 2 else "",
                            "status":    cells[3].get_text(strip=True) if len(cells) > 3 else "",
                        })
            result.update({"charges": charges, "charge_count": len(charges), "status": "success"})
    except Exception as e:
        result["status"] = "error"
        result["error"]  = str(e)
    return result
