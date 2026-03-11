"""
RBI Regulatory Intelligence Agent
Scrapes RBI's public website for circulars and notifications.
RBI site is static HTML — very reliable, no JS needed, no auth.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List
import re
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

RBI_BASE = "https://www.rbi.org.in"

# Sector keyword mapping for RBI search
SECTOR_KEYWORDS = {
    "textiles":     ["msme", "textile", "export", "working capital"],
    "nbfc":         ["nbfc", "non-banking", "shadow banking", "p2p"],
    "real estate":  ["real estate", "housing", "mortgage", "ltv"],
    "pharma":       ["pharmaceutical", "healthcare", "msme"],
    "steel":        ["steel", "metal", "commodity", "infrastructure"],
    "it":           ["it sector", "technology", "fintech"],
    "agriculture":  ["agriculture", "kisan", "farm", "crop loan", "kcc"],
    "msme":         ["msme", "small enterprise", "micro", "mudra"],
}


def _get_html(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def fetch_rbi_circulars(sector: str = None, max_results: int = 10) -> Dict[str, Any]:
    """
    Fetch latest RBI circulars from the public notifications page.
    Filter by sector-relevant keywords if provided.
    """
    result = {"source": "rbi_india", "sector": sector}

    # RBI notifications listing page
    url  = f"{RBI_BASE}/Scripts/NotificationUser.aspx"
    html = _get_html(url)

    if not html:
        return {**result, "status": "unreachable",
                "message": "RBI site unreachable. Check at rbi.org.in manually.",
                "circulars": []}

    soup = BeautifulSoup(html, "html.parser")
    circulars = []

    # Parse notification table
    table = soup.find("table", {"id": re.compile(r"gvData", re.I)}) or \
            soup.find("table", {"class": re.compile(r"tablebg|tablestyle", re.I)})

    if table:
        rows = table.find_all("tr")[1:]  # skip header
        for row in rows[:30]:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            date_text  = cols[0].get_text(strip=True)
            title_col  = cols[1]
            title      = title_col.get_text(strip=True)
            link_tag   = title_col.find("a")
            link       = (RBI_BASE + link_tag["href"]) if link_tag and link_tag.get("href") else ""
            dept       = cols[2].get_text(strip=True) if len(cols) > 2 else ""

            # Filter by sector keywords if provided
            if sector:
                keywords = SECTOR_KEYWORDS.get(sector.lower(), [sector.lower()])
                if not any(kw in title.lower() for kw in keywords + ["msme", "bank", "credit"]):
                    continue

            circulars.append({
                "date":       date_text,
                "title":      title,
                "url":        link,
                "department": dept,
                "relevance":  _score_relevance(title, sector),
            })

            if len(circulars) >= max_results:
                break

    # Sort by relevance
    circulars.sort(key=lambda x: x["relevance"], reverse=True)

    result.update({
        "status":   "success" if circulars else "no_results",
        "count":    len(circulars),
        "circulars": circulars,
        "rbi_url":  url,
    })
    return result


def fetch_rbi_master_directions(sector: str = None) -> Dict[str, Any]:
    """
    Fetch RBI Master Directions — the most important regulatory docs for lending.
    """
    url  = f"{RBI_BASE}/Scripts/BS_ViewMasDirections.aspx"
    html = _get_html(url)
    result = {"source": "rbi_master_directions", "sector": sector}

    if not html:
        return {**result, "status": "unreachable", "directions": []}

    soup = BeautifulSoup(html, "html.parser")
    directions = []

    for link in soup.find_all("a", href=True)[:50]:
        text = link.get_text(strip=True)
        if not text or len(text) < 10:
            continue
        if sector:
            keywords = SECTOR_KEYWORDS.get(sector.lower(), [sector.lower()])
            if not any(kw in text.lower() for kw in keywords):
                continue
        href = link["href"]
        directions.append({
            "title": text,
            "url":   RBI_BASE + href if href.startswith("/") else href,
        })

    result.update({"directions": directions[:5], "count": len(directions)})
    return result


def _score_relevance(title: str, sector: str = None) -> int:
    """Score how relevant a circular is to credit assessment."""
    score = 0
    t = title.lower()
    credit_keywords = ["credit", "lending", "loan", "npa", "provisioning", "exposure", "limit"]
    for kw in credit_keywords:
        if kw in t:
            score += 2
    if sector:
        sector_kws = SECTOR_KEYWORDS.get(sector.lower(), [sector.lower()])
        for kw in sector_kws:
            if kw in t:
                score += 3
    return score


def get_rbi_policy_rate() -> Dict[str, Any]:
    """
    Fetch current RBI repo rate and policy stance from RBI website.
    Critical for pricing the loan (MCLR base).
    """
    url  = f"{RBI_BASE}/Scripts/PublicationsView.aspx?id=22160"
    html = _get_html(url)
    result = {"source": "rbi_policy_rate"}

    # Try to find rate in text
    rate_pattern = re.compile(r"repo\s+rate[^0-9]*([\d.]+)\s*(?:per\s+cent|%)", re.IGNORECASE)
    match = rate_pattern.search(html) if html else None

    if match:
        result.update({"repo_rate_pct": float(match.group(1)), "status": "found"})
    else:
        # Hardcode known rate as fallback (update periodically)
        result.update({
            "repo_rate_pct": 6.5,
            "status":        "fallback",
            "note":          "Using last known RBI repo rate. Verify at rbi.org.in",
        })

    return result
