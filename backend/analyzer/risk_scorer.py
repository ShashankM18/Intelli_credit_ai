from typing import Dict, Any


# ─── Weights for the Five C's ─────────────────────────────────────────────────
WEIGHTS = {
    "character":  0.20,   # Promoter background, CIBIL, litigation
    "capacity":   0.30,   # Revenue, profitability, DSCR
    "capital":    0.20,   # Net worth, D/E ratio, leverage
    "collateral": 0.15,   # Security cover
    "conditions": 0.15,   # Sector outlook, macro
}

# Score bands
def _band(score: float) -> str:
    if score >= 80: return "LOW RISK"
    if score >= 65: return "MODERATE RISK"
    if score >= 50: return "HIGH RISK"
    return "VERY HIGH RISK"

def _decision(score: float) -> str:
    if score >= 70: return "APPROVE"
    if score >= 55: return "CONDITIONAL APPROVE"
    return "REJECT"


# ─── Individual C scorers ─────────────────────────────────────────────────────

def score_character(data: Dict) -> Dict[str, Any]:
    """Score based on promoter credibility and legal history."""
    score = 60  # Base

    cibil = data.get("cibil_score", 0)
    if cibil >= 750: score += 20
    elif cibil >= 700: score += 12
    elif cibil >= 650: score += 5
    elif cibil > 0: score -= 10

    if data.get("litigation_count", 0) == 0:
        score += 10
    elif data.get("litigation_count", 0) <= 2:
        score -= 5
    else:
        score -= 20

    if data.get("gst_compliance_pct", 0) >= 90:
        score += 10
    elif data.get("gst_compliance_pct", 0) >= 75:
        score += 5
    else:
        score -= 10

    return {
        "score": max(0, min(100, score)),
        "inputs": data,
        "label": "Character"
    }


def score_capacity(data: Dict) -> Dict[str, Any]:
    """Score based on ability to repay — cash flows and profitability."""
    score = 60

    margin = data.get("net_profit_margin_pct", 0)
    if margin >= 15: score += 20
    elif margin >= 8: score += 12
    elif margin >= 4: score += 5
    elif margin >= 0: score -= 5
    else: score -= 20

    dscr = data.get("dscr", 0)
    if dscr >= 1.75: score += 15
    elif dscr >= 1.25: score += 8
    elif dscr >= 1.0: score += 2
    elif dscr > 0: score -= 15

    revenue_growth = data.get("revenue_growth_pct", 0)
    if revenue_growth >= 15: score += 5
    elif revenue_growth >= 5: score += 2
    elif revenue_growth < 0: score -= 10

    wc_days = data.get("working_capital_days", 0)
    if 0 < wc_days <= 60: score += 5
    elif wc_days <= 90: score += 0
    elif wc_days <= 120: score -= 5
    elif wc_days > 120: score -= 15

    return {
        "score": max(0, min(100, score)),
        "inputs": data,
        "label": "Capacity"
    }


def score_capital(data: Dict) -> Dict[str, Any]:
    """Score based on financial strength and leverage."""
    score = 60

    de = data.get("debt_equity_ratio", 0)
    if de <= 0.5: score += 20
    elif de <= 1.0: score += 12
    elif de <= 1.5: score += 5
    elif de <= 2.5: score -= 10
    else: score -= 25

    current_ratio = data.get("current_ratio", 0)
    if current_ratio >= 2.0: score += 10
    elif current_ratio >= 1.5: score += 6
    elif current_ratio >= 1.0: score += 0
    else: score -= 15

    net_worth = data.get("net_worth_crore", 0)
    if net_worth >= 100: score += 10
    elif net_worth >= 25: score += 5
    elif net_worth < 5: score -= 10

    return {
        "score": max(0, min(100, score)),
        "inputs": data,
        "label": "Capital"
    }


def score_collateral(data: Dict) -> Dict[str, Any]:
    """Score based on security offered."""
    score = 50

    coverage = data.get("collateral_coverage_ratio", 0)
    if coverage >= 2.0: score += 30
    elif coverage >= 1.5: score += 20
    elif coverage >= 1.0: score += 10
    elif coverage >= 0.75: score -= 10
    else: score -= 25

    if data.get("title_clear", True): score += 10
    if data.get("collateral_type") in ("land", "property", "fdr"): score += 10
    elif data.get("collateral_type") == "stock": score += 3

    return {
        "score": max(0, min(100, score)),
        "inputs": data,
        "label": "Collateral"
    }


def score_conditions(data: Dict) -> Dict[str, Any]:
    """Score based on macro / sector conditions."""
    score = 60

    sector_outlook = data.get("sector_outlook", "neutral").lower()
    if sector_outlook == "positive": score += 15
    elif sector_outlook == "neutral": score += 0
    elif sector_outlook == "headwinds": score -= 10
    elif sector_outlook == "negative": score -= 20

    rbi_flags = data.get("rbi_regulatory_flags", 0)
    score -= rbi_flags * 5

    news_sentiment = data.get("news_sentiment", "neutral").lower()
    if news_sentiment == "positive": score += 10
    elif news_sentiment == "negative": score -= 15

    return {
        "score": max(0, min(100, score)),
        "inputs": data,
        "label": "Conditions"
    }


# ─── Master Scoring Engine ───────────────────────────────────────────────────

def compute_overall_score(
    character_data: Dict,
    capacity_data: Dict,
    capital_data: Dict,
    collateral_data: Dict,
    conditions_data: Dict,
) -> Dict[str, Any]:
    """
    Compute the final weighted credit score and recommendation.
    """
    c1 = score_character(character_data)
    c2 = score_capacity(capacity_data)
    c3 = score_capital(capital_data)
    c4 = score_collateral(collateral_data)
    c5 = score_conditions(conditions_data)

    overall = round(
        c1["score"] * WEIGHTS["character"] +
        c2["score"] * WEIGHTS["capacity"] +
        c3["score"] * WEIGHTS["capital"] +
        c4["score"] * WEIGHTS["collateral"] +
        c5["score"] * WEIGHTS["conditions"],
        1
    )

    decision = _decision(overall)

    # Suggested loan amount: based on net worth and DSCR
    net_worth = capital_data.get("net_worth_crore", 0)
    requested = capacity_data.get("requested_amount_crore", 0)
    dscr      = capacity_data.get("dscr", 1.0)

    if decision == "APPROVE":
        # Cap at 2x net worth, adjusted by DSCR
        suggested = min(requested, net_worth * 2 * min(dscr / 1.5, 1.0))
        suggested = round(max(suggested * 0.8, 0), 2)  # 20% haircut for safety
    elif decision == "CONDITIONAL APPROVE":
        suggested = round(requested * 0.6, 2)
    else:
        suggested = 0.0

    # Interest rate: base MCLR + spread based on score
    if overall >= 80:   spread = 1.5
    elif overall >= 70: spread = 2.0
    elif overall >= 60: spread = 2.75
    else:               spread = 3.5

    mclr = 8.5  # Assumed MCLR
    rate = round(mclr + spread, 2)

    # Explainability factors
    explain = []
    if c1["score"] >= 75: explain.append(("positive", f"Strong promoter profile & compliance (Character: {c1['score']}/100)"))
    if c1["score"] < 60:  explain.append(("negative", f"Promoter credibility concerns (Character: {c1['score']}/100)"))
    if c2["score"] >= 70: explain.append(("positive", f"Healthy cash flow & profitability (Capacity: {c2['score']}/100)"))
    if c2["score"] < 55:  explain.append(("negative", f"Weak repayment capacity (Capacity: {c2['score']}/100)"))
    if c3["score"] < 55:  explain.append(("negative", f"High leverage ratio (Capital: {c3['score']}/100)"))
    if c4["score"] >= 75: explain.append(("positive", f"Adequate collateral coverage (Collateral: {c4['score']}/100)"))
    if c4["score"] < 50:  explain.append(("negative", f"Insufficient collateral cover (Collateral: {c4['score']}/100)"))
    if c5["score"] < 55:  explain.append(("negative", f"Adverse sector/macro conditions (Conditions: {c5['score']}/100)"))

    return {
        "scores": {
            "character":  c1["score"],
            "capacity":   c2["score"],
            "capital":    c3["score"],
            "collateral": c4["score"],
            "conditions": c5["score"],
            "overall":    overall,
        },
        "risk_band":              _band(overall),
        "decision":               decision,
        "suggested_limit_crore":  suggested,
        "interest_rate_pct":      rate,
        "rate_breakdown":         f"MCLR ({mclr}%) + Spread ({spread}%)",
        "explainability":         explain,
    }
