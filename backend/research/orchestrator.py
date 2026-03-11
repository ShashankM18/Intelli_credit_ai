"""
Research Orchestrator — India Stack
Runs all agents in parallel:
  1. News Agent     → Tavily API + Google News RSS (fallback)
  2. BSE Agent      → BSE India public API (free, no key)
  3. RBI Agent      → RBI website scraper (static, reliable)
  4. MCA Agent      → MCA21 scraper (best-effort)
  5. eCourts Agent  → eCourts scraper (best-effort)
"""

import concurrent.futures
from typing import Dict, Any
from datetime import datetime

from research.news_agent    import research_company_news, research_promoter, research_sector
from research.bse_agent     import full_bse_research
from research.rbi_agent     import fetch_rbi_circulars, get_rbi_policy_rate
from research.mca_agent     import search_company_mca
from research.ecourts_agent import search_ecourts_party


def run_full_research(
    company_name:  str,
    promoter_name: str  = None,
    sector:        str  = None,
    cin:           str  = None,
    state:         str  = None,
    tavily_api_key: str = None,   # Optional — falls back to Google RSS if None
) -> Dict[str, Any]:
    """
    Run all research agents concurrently.
    Returns unified intelligence report with risk signals.
    """

    tasks = {
        "company_news": (
            research_company_news,
            [company_name],
            {"api_key": tavily_api_key}
        ),
        "sector_news": (
            research_sector,
            [sector or "MSME India"],
            {"api_key": tavily_api_key}
        ),
        "bse_data": (
            full_bse_research,
            [company_name],
            {}
        ),
        "rbi_circulars": (
            fetch_rbi_circulars,
            [sector or "msme"],
            {"max_results": 5}
        ),
        "rbi_policy": (
            get_rbi_policy_rate,
            [],
            {}
        ),
        "mca_data": (
            search_company_mca,
            [company_name],
            {"cin": cin}
        ),
        "litigation": (
            search_ecourts_party,
            [company_name],
            {"state": state}
        ),
    }

    if promoter_name:
        tasks["promoter_news"] = (
            research_promoter,
            [promoter_name],
            {"api_key": tavily_api_key}
        )
        tasks["promoter_litigation"] = (
            search_ecourts_party,
            [promoter_name],
            {"state": state}
        )

    # ── Run all tasks in parallel ─────────────────────────────────────────────
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            key: executor.submit(fn, *args, **kwargs)
            for key, (fn, args, kwargs) in tasks.items()
        }
        for key, future in futures.items():
            try:
                results[key] = future.result(timeout=20)
            except Exception as e:
                results[key] = {"status": "error", "error": str(e)}

    # ── Synthesize risk signals ───────────────────────────────────────────────
    risk_signals = []
    overall_risk = "LOW"

    # 1. Company news
    news = results.get("company_news", {})
    if news.get("overall_sentiment") == "negative":
        risk_signals.append({
            "type": "ADVERSE_NEWS", "severity": "HIGH", "source": "News Research",
            "detail": f"{news.get('negative_count', 0)} adverse articles found for {company_name}",
        })
        overall_risk = "HIGH"
    elif news.get("positive_count", 0) > 1:
        risk_signals.append({
            "type": "POSITIVE_NEWS", "severity": "LOW", "source": "News Research",
            "detail": f"{news.get('positive_count', 0)} positive signals — exports, orders, growth",
        })

    # 2. Promoter news
    promoter = results.get("promoter_news", {})
    if promoter.get("adverse_news"):
        risk_signals.append({
            "type": "PROMOTER_ADVERSE_NEWS", "severity": "HIGH", "source": "News Research",
            "detail": f"Adverse news found for promoter: {promoter_name}",
        })
        overall_risk = "HIGH"

    # 3. BSE data (pledging, announcements)
    bse = results.get("bse_data", {})
    for flag in bse.get("all_flags", []):
        severity = flag.get("severity", "LOW")
        risk_signals.append({
            "type":     flag.get("type", "BSE_FLAG"),
            "severity": severity,
            "source":   "BSE India",
            "detail":   flag.get("detail", ""),
        })
        if severity == "HIGH":
            overall_risk = "HIGH"
        elif severity == "MEDIUM" and overall_risk == "LOW":
            overall_risk = "MEDIUM"

    # 4. Litigation
    litigation = results.get("litigation", {})
    lit_risk   = litigation.get("risk_level", "LOW")
    case_count = litigation.get("case_count", 0)
    if lit_risk == "HIGH":
        risk_signals.append({
            "type": "HIGH_LITIGATION_RISK", "severity": "HIGH", "source": "eCourts",
            "detail": f"{case_count} pending cases — high-risk case types detected",
        })
        overall_risk = "HIGH"
    elif lit_risk == "MEDIUM":
        risk_signals.append({
            "type": "LITIGATION_RISK", "severity": "MEDIUM", "source": "eCourts",
            "detail": f"{case_count} pending cases found",
        })
        if overall_risk == "LOW":
            overall_risk = "MEDIUM"
    else:
        risk_signals.append({
            "type": "CLEAN_LITIGATION", "severity": "LOW", "source": "eCourts",
            "detail": "No adverse litigation found on eCourts portal",
        })

    # 5. MCA status
    mca    = results.get("mca_data", {})
    status = mca.get("company_status", "").lower()
    if status in ("strike off", "dissolved", "inactive"):
        risk_signals.append({
            "type": "COMPANY_INACTIVE", "severity": "HIGH", "source": "MCA21",
            "detail": f"Company status on MCA21: {mca.get('company_status')}",
        })
        overall_risk = "HIGH"
    elif status == "active":
        risk_signals.append({
            "type": "COMPANY_ACTIVE", "severity": "LOW", "source": "MCA21",
            "detail": "Company is active and compliant on MCA21",
        })

    # 6. RBI regulatory
    rbi     = results.get("rbi_circulars", {})
    rbi_count = rbi.get("count", 0)
    if rbi_count > 0:
        risk_signals.append({
            "type": "RBI_REGULATORY_ACTIVITY", "severity": "MEDIUM", "source": "RBI India",
            "detail": f"{rbi_count} recent RBI circulars relevant to {sector} sector",
        })

    # 7. Sector headwinds
    sector_news = results.get("sector_news", {})
    if sector_news.get("headwind_signals", 0) >= 2:
        risk_signals.append({
            "type": "SECTOR_HEADWINDS", "severity": "MEDIUM", "source": "Sector Research",
            "detail": f"Multiple negative signals in {sector} sector outlook",
        })

    return {
        "company":                company_name,
        "promoter":               promoter_name,
        "sector":                 sector,
        "researched_at":          datetime.now().isoformat(),
        "results":                results,
        "risk_signals":           risk_signals,
        "overall_research_risk":  overall_risk,
        "signal_count":           len(risk_signals),
        "news_sentiment":         news.get("overall_sentiment", "neutral"),
        "litigation_risk":        lit_risk,
        "mca_status":             mca.get("company_status", "unknown"),
        "rbi_repo_rate":          results.get("rbi_policy", {}).get("repo_rate_pct", 6.5),
        "bse_found":              bse.get("found", False),
        "search_method":          "tavily" if tavily_api_key else "google_rss",
    }
