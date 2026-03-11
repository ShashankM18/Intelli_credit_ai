"""
News Research Agent — India Optimized
Primary:  Tavily Search API (structured web results, India domains prioritized)
Fallback: Google News RSS (free, no key, excellent India coverage)
"""

import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from typing import Dict, List, Any
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

NEGATIVE_KEYWORDS = [
    "fraud", "scam", "arrested", "defaulter", "npa", "wilful defaulter",
    "bankruptcy", "insolvency", "liquidation", "ed raid", "cbi",
    "enforcement directorate", "money laundering", "hawala", "fake invoice",
    "tax evasion", "sebi notice", "rbi penalty", "nclt", "winding up",
    "bank fraud", "cheque bounce", "loan default", "attached property"
]
POSITIVE_KEYWORDS = [
    "export order", "expansion", "new plant", "award", "profit", "revenue growth",
    "ipo", "funding", "partnership", "contract", "recognition", "certification",
    "turnover increase", "new order", "capacity expansion"
]

INDIA_DOMAINS = [
    "economictimes.indiatimes.com", "livemint.com", "business-standard.com",
    "moneycontrol.com", "financialexpress.com", "thehindu.com", "ndtv.com",
    "bseindia.com", "nseindia.com", "rbi.org.in", "mca.gov.in",
    "timesofindia.com", "outlookindia.com", "thehindubusinessline.com",
]


def _detect_sentiment(text: str) -> str:
    t = text.lower()
    for kw in NEGATIVE_KEYWORDS:
        if kw in t:
            return "negative"
    for kw in POSITIVE_KEYWORDS:
        if kw in t:
            return "positive"
    return "neutral"


# ── Tavily API ────────────────────────────────────────────────────────────────
def _tavily_search(query: str, api_key: str, max_results: int = 5) -> List[Dict]:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key":       api_key,
                "query":         query,
                "search_depth":  "basic",
                "max_results":   max_results,
                "include_domains": INDIA_DOMAINS,
            },
            timeout=10,
        )
        resp.raise_for_status()
        articles = []
        for r in resp.json().get("results", []):
            content = r.get("content", "")
            articles.append({
                "title":     r.get("title", ""),
                "url":       r.get("url", ""),
                "snippet":   content[:300],
                "source":    r.get("url", "").split("/")[2] if r.get("url") else "",
                "published": r.get("published_date", ""),
                "sentiment": _detect_sentiment(r.get("title", "") + " " + content),
                "via":       "tavily",
            })
        return articles
    except Exception:
        return []


# ── Google News RSS fallback ──────────────────────────────────────────────────
def _google_news_rss(query: str, max_results: int = 5) -> List[Dict]:
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        articles = []
        for item in root.findall(".//item")[:max_results]:
            title  = item.findtext("title", "").strip()
            source = item.find("source")
            articles.append({
                "title":     title,
                "url":       item.findtext("link", ""),
                "snippet":   "",
                "source":    source.text if source is not None else "Google News",
                "published": item.findtext("pubDate", ""),
                "sentiment": _detect_sentiment(title),
                "via":       "google_rss",
            })
        return articles
    except Exception:
        return []


# ── Smart unified search ──────────────────────────────────────────────────────
def smart_search(query: str, api_key: str = None, max_results: int = 5) -> List[Dict]:
    """Tavily if key available, Google RSS as fallback."""
    if api_key:
        results = _tavily_search(query, api_key, max_results)
        if results:
            return results
    return _google_news_rss(query, max_results)


# ── High-level research functions ─────────────────────────────────────────────
def research_company_news(company_name: str, api_key: str = None) -> Dict[str, Any]:
    queries = [
        f'"{company_name}" India',
        f'"{company_name}" fraud OR NPA OR default OR NCLT OR insolvency',
        f'"{company_name}" expansion OR export OR profit',
    ]
    all_articles = []
    for q in queries:
        all_articles.extend(smart_search(q, api_key, max_results=4))
        time.sleep(0.3)

    seen, unique = set(), []
    for a in all_articles:
        if a.get("title") and a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    negative = [a for a in unique if a["sentiment"] == "negative"]
    positive = [a for a in unique if a["sentiment"] == "positive"]
    overall  = "negative" if len(negative) > 2 else \
               "positive" if len(positive) > len(negative) else "neutral"

    return {
        "source": "news_research", "company": company_name,
        "total_articles": len(unique), "articles": unique[:10],
        "negative_count": len(negative), "positive_count": len(positive),
        "overall_sentiment": overall, "red_flags": negative[:3],
    }


def research_promoter(promoter_name: str, api_key: str = None) -> Dict[str, Any]:
    queries = [
        f'"{promoter_name}" director India',
        f'"{promoter_name}" fraud OR arrest OR SEBI OR ED OR default',
    ]
    all_articles = []
    for q in queries:
        all_articles.extend(smart_search(q, api_key, max_results=4))
        time.sleep(0.3)

    negative = [a for a in all_articles if a["sentiment"] == "negative"]
    return {
        "source": "promoter_research", "promoter": promoter_name,
        "articles": all_articles[:6], "adverse_news": len(negative) > 0,
        "adverse_count": len(negative), "red_flags": negative[:2],
    }


def research_sector(sector: str, api_key: str = None) -> Dict[str, Any]:
    queries = [
        f"India {sector} sector outlook 2025",
        f"RBI {sector} regulation India 2025",
        f"{sector} industry India headwinds challenges",
    ]
    all_articles = []
    for q in queries:
        all_articles.extend(smart_search(q, api_key, max_results=3))
        time.sleep(0.3)

    return {
        "source": "sector_research", "sector": sector,
        "articles": all_articles[:8],
        "headwind_signals": sum(1 for a in all_articles if a["sentiment"] == "negative"),
    }
