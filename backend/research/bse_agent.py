"""
BSE India API Agent
Fetches company filings, announcements, and financials from BSE India.
100% free — no API key needed. Official government-backed data.
Works for all BSE-listed companies.
"""

import requests
from typing import Dict, Any, List

HEADERS = {
    "User-Agent":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":     "https://www.bseindia.com",
    "Accept":      "application/json",
}

BSE_BASE = "https://api.bseindia.com/BseIndiaAPI/api"


def _get(url: str, params: dict = None) -> dict:
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def search_company_bse(company_name: str) -> Dict[str, Any]:
    """
    Search for a company on BSE by name.
    Returns: ISIN, scrip code, company name, listing status.
    """
    result = {"source": "bse_india", "searched": company_name}
    try:
        url  = f"{BSE_BASE}/ListofScripData/w?Group=&Scripcode=&shname={company_name}&industry=&segment=Equity&status=Active"
        data = _get(url)
        companies = data if isinstance(data, list) else data.get("Table", [])
        if companies:
            top = companies[0]
            result.update({
                "found":        True,
                "scrip_code":   top.get("SCRIP_CD", ""),
                "isin":         top.get("ISIN_NO", ""),
                "company_name": top.get("Issuer_Name", ""),
                "industry":     top.get("Industry", ""),
                "status":       top.get("Status", ""),
                "all_matches":  companies[:5],
            })
        else:
            result["found"] = False
            result["message"] = "Company not found on BSE (may be unlisted)"
    except Exception as e:
        result["error"] = str(e)
        result["found"] = False
    return result


def get_company_announcements(scrip_code: str, days: int = 180) -> Dict[str, Any]:
    """
    Fetch recent announcements filed by company on BSE.
    Includes: board meetings, results, acquisitions, legal notices.
    """
    result = {"source": "bse_announcements", "scrip_code": scrip_code}
    try:
        url  = f"{BSE_BASE}/AnnSubCategoryGetData/w?strCat=-1&strPrevDate=&strScrip={scrip_code}&strSearch=P&strToDate=&strType=C&subcategory=-1"
        data = _get(url)

        announcements = data if isinstance(data, list) else data.get("Table", [])
        red_flags = []

        for ann in announcements[:20]:
            headline = str(ann.get("HEADLINE", "")).lower()
            # Flag important announcements
            if any(kw in headline for kw in [
                "litigation", "legal", "nclt", "court", "arbitration",
                "fraud", "penalty", "notice", "attachment", "winding"
            ]):
                red_flags.append({
                    "date":     ann.get("News_submission_dt", ""),
                    "headline": ann.get("HEADLINE", ""),
                    "category": ann.get("CATEGORYNAME", ""),
                    "severity": "HIGH",
                })
            elif any(kw in headline for kw in [
                "acquisition", "merger", "expansion", "new order", "export"
            ]):
                red_flags.append({
                    "date":     ann.get("News_submission_dt", ""),
                    "headline": ann.get("HEADLINE", ""),
                    "category": ann.get("CATEGORYNAME", ""),
                    "severity": "POSITIVE",
                })

        result.update({
            "total_announcements": len(announcements),
            "recent":              announcements[:10],
            "flagged":             red_flags,
        })
    except Exception as e:
        result["error"] = str(e)
    return result


def get_shareholding_pattern(scrip_code: str) -> Dict[str, Any]:
    """
    Fetch latest shareholding pattern from BSE.
    Important for: promoter pledge check, FII/DII confidence.
    """
    result = {"source": "bse_shareholding", "scrip_code": scrip_code}
    try:
        url  = f"{BSE_BASE}/ShareHoldingPatterns/w?scripcode={scrip_code}"
        data = _get(url)
        sh   = data if isinstance(data, list) else data.get("Table", [])

        promoter_pct = 0.0
        pledged_pct  = 0.0

        for row in sh:
            category = str(row.get("Category", "")).lower()
            if "promoter" in category:
                promoter_pct = float(row.get("Percentage", 0) or 0)
            if "pledge" in category:
                pledged_pct  = float(row.get("Percentage", 0) or 0)

        flags = []
        if pledged_pct > 50:
            flags.append({
                "type": "HIGH_PROMOTER_PLEDGE",
                "severity": "HIGH",
                "detail": f"Promoter holding pledged: {pledged_pct}% — major red flag for lending"
            })
        elif pledged_pct > 20:
            flags.append({
                "type": "MODERATE_PROMOTER_PLEDGE",
                "severity": "MEDIUM",
                "detail": f"Promoter holding pledged: {pledged_pct}% — monitor closely"
            })

        result.update({
            "promoter_holding_pct": promoter_pct,
            "pledged_pct":          pledged_pct,
            "shareholding_data":    sh[:10],
            "flags":                flags,
        })
    except Exception as e:
        result["error"] = str(e)
    return result


def get_financial_results(scrip_code: str) -> Dict[str, Any]:
    """
    Fetch latest quarterly / annual financial results from BSE.
    """
    result = {"source": "bse_financials", "scrip_code": scrip_code}
    try:
        url  = f"{BSE_BASE}/FinancialResults/w?scripcode={scrip_code}&Type=Standalone&Period=Annual"
        data = _get(url)
        results_list = data if isinstance(data, list) else data.get("Table", [])

        if results_list:
            latest = results_list[0]
            result.update({
                "period":          latest.get("PERIOD", ""),
                "revenue":         latest.get("Total_Income", 0),
                "net_profit":      latest.get("Net_Profit", 0),
                "eps":             latest.get("EPS", 0),
                "all_periods":     results_list[:4],
            })
    except Exception as e:
        result["error"] = str(e)
    return result


def full_bse_research(company_name: str) -> Dict[str, Any]:
    """
    Master function: search BSE + fetch all data in sequence.
    """
    search = search_company_bse(company_name)

    if not search.get("found"):
        return {
            "source":  "bse_india",
            "found":   False,
            "message": f"'{company_name}' is not listed on BSE. "
                       "Use MCA/news research for unlisted companies.",
        }

    scrip_code = search.get("scrip_code", "")
    announcements = get_company_announcements(scrip_code)
    shareholding  = get_shareholding_pattern(scrip_code)
    financials    = get_financial_results(scrip_code)

    # Aggregate all flags
    all_flags = announcements.get("flagged", []) + shareholding.get("flags", [])

    return {
        "source":        "bse_india",
        "found":         True,
        "company":       search.get("company_name"),
        "isin":          search.get("isin"),
        "scrip_code":    scrip_code,
        "industry":      search.get("industry"),
        "announcements": announcements,
        "shareholding":  shareholding,
        "financials":    financials,
        "all_flags":     all_flags,
        "risk_level":    "HIGH"   if any(f.get("severity") == "HIGH"   for f in all_flags) else
                         "MEDIUM" if any(f.get("severity") == "MEDIUM" for f in all_flags) else "LOW",
    }
