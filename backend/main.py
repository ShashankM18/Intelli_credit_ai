"""
IntelliCredit Backend — Phase 1: Data Ingestion & Analysis
Run with: uvicorn main:app --reload --port 8000
"""

import os, shutil, tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import json
from datetime import datetime

# Internal modules
from extractors.pdf_extractor  import process_annual_report
from extractors.gst_extractor  import parse_gstr3b, parse_gstr2a, cross_check_gst, gst_compliance_score
from extractors.bank_extractor import parse_bank_excel, parse_bank_pdf, cross_check_gst_vs_bank, compute_amb
from extractors.ocr_extractor  import smart_extract
from analyzer.risk_scorer      import compute_overall_score
from analyzer.cam_generator    import generate_cam
from research.orchestrator     import run_full_research

app = FastAPI(
    title="IntelliCredit API",
    description="AI-powered Credit Appraisal Engine — Phase 1: Data Ingestion",
    version="1.0.0"
)

# Allow React frontend (localhost:3000 / any origin in dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory session store (replace with DB in production) ──────────────────
SESSION: dict = {}


def _save_temp(upload: UploadFile) -> str:
    """Save uploaded file to a temp path and return the path."""
    suffix = os.path.splitext(upload.filename)[-1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    shutil.copyfileobj(upload.file, tmp)
    tmp.close()
    return tmp.name


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "IntelliCredit API running", "phase": 1}


# ─── ENDPOINT 1: Upload Annual Report / Financial Statement PDF ───────────────
@app.post("/upload/annual-report")
async def upload_annual_report(file: UploadFile = File(...)):
    """
    Upload a PDF annual report.
    Extracts: revenue, net profit, EBITDA, D/E ratio, current ratio, CIN, FY years.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted for annual reports.")

    tmp_path = _save_temp(file)
    try:
        # Try digital extraction first
        result = process_annual_report(tmp_path)

        # If very little text extracted, try OCR
        if result.get("raw_text_length", 0) < 500:
            ocr = smart_extract(tmp_path)
            result["ocr_fallback"] = True
            result["ocr_status"]   = ocr.get("status")
        else:
            result["ocr_fallback"] = False

        SESSION["annual_report"] = result
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        raise HTTPException(500, f"PDF extraction failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


# ─── ENDPOINT 2: Upload GSTR-3B ───────────────────────────────────────────────
@app.post("/upload/gstr3b")
async def upload_gstr3b(file: UploadFile = File(...)):
    """
    Upload GSTR-3B Excel / CSV.
    Extracts: declared turnover, tax paid, filing periods.
    Computes: compliance score.
    """
    tmp_path = _save_temp(file)
    try:
        data = parse_gstr3b(tmp_path)
        compliance = gst_compliance_score(data)
        data["compliance"] = compliance
        SESSION["gstr3b"] = data

        # Auto cross-check if bank data is available
        cross = None
        if "bank" in SESSION:
            bank_credits = SESSION["bank"].get("total_credits_crore", 0)
            gst_turnover = data.get("declared_turnover_crore", 0)
            cross = cross_check_gst_vs_bank(gst_turnover, bank_credits)
            SESSION["cross_check_bank"] = cross

        return JSONResponse({"success": True, "data": data, "cross_check_bank": cross})
    except Exception as e:
        raise HTTPException(500, f"GST extraction failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


# ─── ENDPOINT 3: Upload GSTR-2A ───────────────────────────────────────────────
@app.post("/upload/gstr2a")
async def upload_gstr2a(file: UploadFile = File(...)):
    """
    Upload GSTR-2A Excel / CSV.
    Extracts: total purchases, suppliers.
    Cross-checks against GSTR-3B for circular trading.
    """
    tmp_path = _save_temp(file)
    try:
        data = parse_gstr2a(tmp_path)
        SESSION["gstr2a"] = data

        cross = None
        if "gstr3b" in SESSION:
            cross = cross_check_gst(SESSION["gstr3b"], data)
            SESSION["cross_check_gst"] = cross

        return JSONResponse({"success": True, "data": data, "cross_check_circular": cross})
    except Exception as e:
        raise HTTPException(500, f"GSTR-2A extraction failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


# ─── ENDPOINT 4: Upload Bank Statement ───────────────────────────────────────
@app.post("/upload/bank-statement")
async def upload_bank_statement(file: UploadFile = File(...)):
    """
    Upload bank statement (PDF or Excel).
    Extracts: total credits, debits, monthly summary, bounce flags.
    Cross-checks against GST turnover automatically.
    """
    tmp_path = _save_temp(file)
    try:
        ext = file.filename.lower().split(".")[-1]
        if ext in ("xlsx", "xls", "csv"):
            data = parse_bank_excel(tmp_path)
        elif ext == "pdf":
            data = parse_bank_pdf(tmp_path)
        else:
            raise HTTPException(400, f"Unsupported bank statement format: {ext}")

        data["avg_monthly_credits_crore"] = compute_amb(data.get("monthly_credits_crore", {}))
        SESSION["bank"] = data

        # Auto cross-check with GST if available
        cross = None
        if "gstr3b" in SESSION:
            gst_turn = SESSION["gstr3b"].get("declared_turnover_crore", 0)
            cross = cross_check_gst_vs_bank(gst_turn, data.get("total_credits_crore", 0))
            SESSION["cross_check_bank"] = cross

        return JSONResponse({"success": True, "data": data, "cross_check_bank": cross})
    except Exception as e:
        raise HTTPException(500, f"Bank statement extraction failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


# ─── ENDPOINT 5: Upload Scanned Document (OCR) ───────────────────────────────
@app.post("/upload/scanned")
async def upload_scanned(file: UploadFile = File(...)):
    """
    Upload a scanned PDF or image.
    Runs Tesseract OCR and returns extracted text + detected financials.
    """
    tmp_path = _save_temp(file)
    try:
        result = smart_extract(tmp_path)
        SESSION["scanned"] = result
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        raise HTTPException(500, f"OCR extraction failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


# ─── ENDPOINT 6: Get Full Analysis Summary ────────────────────────────────────
@app.get("/analysis/summary")
def get_summary():
    """
    Returns everything extracted so far in the session.
    Includes cross-checks, anomaly flags, and extracted financials.
    """
    return JSONResponse({
        "annual_report":       SESSION.get("annual_report"),
        "gstr3b":              SESSION.get("gstr3b"),
        "gstr2a":              SESSION.get("gstr2a"),
        "bank":                SESSION.get("bank"),
        "cross_check_gst":     SESSION.get("cross_check_gst"),
        "cross_check_bank":    SESSION.get("cross_check_bank"),
        "scanned":             SESSION.get("scanned"),
        "documents_uploaded":  list(SESSION.keys()),
    })


# ─── ENDPOINT 7: Compute Risk Score ──────────────────────────────────────────
@app.post("/analysis/risk-score")
async def compute_risk(payload: dict):
    """
    Compute Five C's risk score.
    Accepts JSON body with all scoring inputs.
    Also accepts qualitative officer notes to adjust score.
    """
    try:
        # Pull from session if available, override with payload
        annual = SESSION.get("annual_report", {})
        gst    = SESSION.get("gstr3b", {})
        bank   = SESSION.get("bank", {})

        # Build scoring inputs
        character_data = {
            "cibil_score":        payload.get("cibil_score", 0),
            "litigation_count":   payload.get("litigation_count", 0),
            "gst_compliance_pct": gst.get("compliance", {}).get("compliance_pct", 0),
        }
        capacity_data = {
            "net_profit_margin_pct": annual.get("net_profit_margin_pct", payload.get("net_profit_margin_pct", 0)),
            "dscr":                  payload.get("dscr", 1.0),
            "revenue_growth_pct":    payload.get("revenue_growth_pct", 0),
            "working_capital_days":  payload.get("working_capital_days", 90),
            "requested_amount_crore":payload.get("requested_amount_crore", 10),
        }
        capital_data = {
            "debt_equity_ratio": annual.get("debt_equity_ratio", payload.get("debt_equity_ratio", 1.0)),
            "current_ratio":     annual.get("current_ratio", payload.get("current_ratio", 1.5)),
            "net_worth_crore":   annual.get("equity", payload.get("net_worth_crore", 10)),
        }
        collateral_data = {
            "collateral_coverage_ratio": payload.get("collateral_coverage_ratio", 1.0),
            "title_clear":               payload.get("title_clear", True),
            "collateral_type":           payload.get("collateral_type", "property"),
        }
        conditions_data = {
            "sector_outlook":       payload.get("sector_outlook", "neutral"),
            "rbi_regulatory_flags": payload.get("rbi_regulatory_flags", 0),
            "news_sentiment":       payload.get("news_sentiment", "neutral"),
        }

        # Officer qualitative notes adjustment
        qualitative_boost = 0
        officer_notes = payload.get("officer_notes", {})
        if officer_notes.get("capacity_utilization_pct", 0) >= 75:
            qualitative_boost += 3
        if officer_notes.get("management_quality") == "strong":
            qualitative_boost += 4
        if officer_notes.get("site_visit_positive"):
            qualitative_boost += 2

        result = compute_overall_score(
            character_data, capacity_data, capital_data, collateral_data, conditions_data
        )

        # Apply qualitative boost
        if qualitative_boost:
            result["scores"]["overall"] = min(100, result["scores"]["overall"] + qualitative_boost)
            result["qualitative_boost"] = qualitative_boost
            result["explainability"].append(
                ("positive", f"Qualitative assessment by Credit Officer: +{qualitative_boost} pts")
            )

        SESSION["risk_score"] = result
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        raise HTTPException(500, f"Risk scoring failed: {str(e)}")


# ─── ENDPOINT 9: Run Web Research Agent ──────────────────────────────────────
@app.post("/research/run")
async def run_research(payload: dict):
    """
    Phase 2: Trigger the full web research agent.
    Runs in parallel: Google News, MCA21, eCourts, sector news.

    Body: {
        "company_name": "Rajasthan Textiles Pvt Ltd",
        "promoter_name": "Ramesh Agarwal",   (optional)
        "sector": "Textiles",                (optional)
        "cin": "U17111RJ2010PTC030452",      (optional)
        "state": "Rajasthan"                 (optional)
    }
    """
    company_name  = payload.get("company_name")
    if not company_name:
        raise HTTPException(400, "company_name is required")

    try:
        report = run_full_research(
            company_name   = company_name,
            promoter_name  = payload.get("promoter_name"),
            sector         = payload.get("sector"),
            cin            = payload.get("cin"),
            state          = payload.get("state"),
            tavily_api_key = payload.get("tavily_api_key") or os.getenv("TAVILY_API_KEY"),
        )
        SESSION["research"] = report
        return JSONResponse({"success": True, "data": report})
    except Exception as e:
        raise HTTPException(500, f"Research agent failed: {str(e)}")


@app.get("/research/summary")
def get_research_summary():
    """Return cached research results from session."""
    research = SESSION.get("research")
    if not research:
        raise HTTPException(404, "No research run yet. POST to /research/run first.")
    return JSONResponse({"success": True, "data": research})



# ─── ENDPOINT: Generate CAM Report ───────────────────────────────────────────
@app.post("/report/generate-cam")
async def generate_cam_report(payload: dict):
    """
    Phase 3: Generate a full Credit Appraisal Memo (CAM) Word document.
    Pulls all session data (financials, research, scores) and compiles into .docx
    Body: same as /analysis/risk-score + optional company_info fields
    """
    from fastapi.responses import Response

    try:
        # Pull everything from session
        annual   = SESSION.get("annual_report", {})
        gst      = SESSION.get("gstr3b", {})
        bank     = SESSION.get("bank", {})
        research = SESSION.get("research", {})
        risk     = SESSION.get("risk_score", {})

        company_info = {
            "name":     payload.get("company_name", annual.get("company_name", "N/A")),
            "cin":      payload.get("cin", annual.get("cin", "N/A")),
            "sector":   payload.get("sector", "N/A"),
            "promoter": payload.get("promoter_name", "N/A"),
            "address":  payload.get("address", "N/A"),
            "founded":  payload.get("founded", "N/A"),
            "employees":payload.get("employees", "N/A"),
        }

        # Build financials: payload values take priority over session data
        financials = {
            **annual,  # session data as base
            # Override with payload values if provided
            "revenue":               payload.get("revenue",               annual.get("revenue",               "N/A")),
            "net_profit":            payload.get("net_profit",            annual.get("net_profit",            "N/A")),
            "net_profit_margin_pct": payload.get("net_profit_margin_pct", annual.get("net_profit_margin_pct", "N/A")),
            "ebitda":                payload.get("ebitda",                annual.get("ebitda",                "N/A")),
            "total_debt":            payload.get("total_debt",            annual.get("total_debt",            "N/A")),
            "equity":                payload.get("net_worth_crore",       annual.get("equity",               "N/A")),
            "debt_equity_ratio":     payload.get("debt_equity_ratio",     annual.get("debt_equity_ratio",    "N/A")),
            "current_ratio":         payload.get("current_ratio",         annual.get("current_ratio",        "N/A")),
            "dscr":                  payload.get("dscr",                  1.0),
            "collateral_coverage":   payload.get("collateral_coverage_ratio", 1.0),
            "working_capital_days":  payload.get("working_capital_days",  "N/A"),
            "revenue_growth_pct":    payload.get("revenue_growth_pct",    "N/A"),
            "fy":                    payload.get("fy",                    "2024"),
        }

        recommendation = {
            **risk,
            "decision":       risk.get("decision", "PENDING"),
            "limit_crore":    risk.get("suggested_limit_crore", 0),
            "rate_pct":       risk.get("interest_rate_pct", 0),
            "rate_breakdown": risk.get("rate_breakdown", "MCLR + Spread"),
            "requested_crore":payload.get("requested_amount_crore", 0),
            "risk_band":      risk.get("risk_band", "Moderate Risk"),
        }

        cam_data = {
            "company_info":    company_info,
            "financials":      financials,
            "gst_data":        {
                "compliance_pct":           payload.get("gst_compliance_pct",      gst.get("compliance", {}).get("compliance_pct", "N/A")),
                "declared_turnover_crore":  payload.get("gst_declared_turnover",   gst.get("declared_turnover_crore", "N/A")),
            },
            "bank_data":       {
                "total_credits_crore":        payload.get("bank_credits_crore",      bank.get("total_credits_crore", "N/A")),
                "avg_monthly_credits_crore":  payload.get("avg_monthly_bank_credits", bank.get("avg_monthly_credits_crore", "N/A")),
                "bounce_flags":               bank.get("bounce_flags", []),
            },
            "cross_check_bank":SESSION.get("cross_check_bank", {}),
            "research":        research,
            "scores":          risk.get("scores", {}),
            "recommendation":  recommendation,
            "explainability":  risk.get("explainability", []),
            "officer_notes":   payload.get("officer_notes", {}),
        }

        doc_bytes = generate_cam(cam_data)
        company_slug = company_info["name"].replace(" ", "_")[:30]
        filename = f"CAM_{company_slug}_{datetime.now().strftime('%Y%m%d')}.docx"

        return Response(
            content=doc_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(500, f"CAM generation failed: {str(e)}")


# ─── ENDPOINT: Full Pipeline (Upload docs → CAM in one shot) ─────────────────
@app.post("/pipeline/full")
async def full_pipeline(
    # ── Company info (required) ───────────────────────────────────────────────
    company_name:             str        = Form(...),
    promoter_name:            str        = Form(...),
    sector:                   str        = Form(...),
    requested_amount_crore:   float      = Form(...),
    cin:                      str        = Form(""),
    address:                  str        = Form(""),
    founded:                  str        = Form(""),
    employees:                int        = Form(0),
    state:                    str        = Form(""),
    tavily_api_key:           str        = Form(""),

    # ── Financial inputs (used when no PDF uploaded) ──────────────────────────
    revenue:                  float      = Form(0),
    net_profit_margin_pct:    float      = Form(0),
    ebitda:                   float      = Form(0),
    total_debt:               float      = Form(0),
    net_worth_crore:          float      = Form(0),
    debt_equity_ratio:        float      = Form(0),
    current_ratio:            float      = Form(0),
    dscr:                     float      = Form(0),
    working_capital_days:     float      = Form(0),
    collateral_coverage_ratio:float      = Form(0),
    cibil_score:              int        = Form(0),
    revenue_growth_pct:       float      = Form(0),
    sector_outlook:           str        = Form("neutral"),
    news_sentiment:           str        = Form("neutral"),
    capacity_utilization_pct: float      = Form(0),
    management_quality:       str        = Form("average"),
    site_visit_positive:      bool       = Form(False),

    # ── Document uploads (all optional) ──────────────────────────────────────
    annual_report:            Optional[UploadFile] = File(None),
    gstr3b:                   Optional[UploadFile] = File(None),
    gstr2a:                   Optional[UploadFile] = File(None),
    bank_statement:           Optional[UploadFile] = File(None),
):
    """
    ONE-SHOT FULL PIPELINE:
    Upload your documents + fill company info → get CAM Word document back.

    Steps executed automatically:
      1. Parse uploaded documents (annual report PDF, GSTR-3B, GSTR-2A, bank statement)
      2. Run web research (news, MCA, eCourts, BSE, RBI)
      3. Compute Five C scoring
      4. Generate CAM Word document
      5. Return .docx file for download
    """
    from fastapi import Form
    from fastapi.responses import Response

    SESSION.clear()
    progress = []

    # ── STEP 1: Process uploaded documents ────────────────────────────────────
    fin_from_docs  = {}
    gst_data_out   = {}
    bank_data_out  = {}
    cross_check_out= {}

    # Annual Report PDF
    if annual_report and annual_report.filename:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                shutil.copyfileobj(annual_report.file, tmp)
                tmp_path = tmp.name
            fin_from_docs = process_annual_report(tmp_path)
            SESSION["annual_report"] = fin_from_docs
            os.unlink(tmp_path)
            progress.append(f"Annual report parsed: {annual_report.filename}")
        except Exception as e:
            progress.append(f"Annual report parse failed: {e}")

    # GSTR-3B
    gst_compliance_pct_val = 0
    gst_turnover_val       = 0
    if gstr3b and gstr3b.filename:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                shutil.copyfileobj(gstr3b.file, tmp)
                tmp_path = tmp.name
            from extractors.gst_extractor import parse_gstr3b, gst_compliance_score
            g3b = parse_gstr3b(tmp_path)
            compliance = gst_compliance_score(g3b)
            gst_data_out = {**g3b, "compliance": compliance}
            SESSION["gstr3b"] = gst_data_out
            gst_compliance_pct_val = compliance.get("compliance_pct", 0)
            gst_turnover_val       = g3b.get("declared_turnover_crore", 0)
            os.unlink(tmp_path)
            progress.append(f"GSTR-3B parsed: turnover INR {gst_turnover_val} Cr, compliance {gst_compliance_pct_val}%")
        except Exception as e:
            progress.append(f"GSTR-3B parse failed: {e}")

    # GSTR-2A
    if gstr2a and gstr2a.filename:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                shutil.copyfileobj(gstr2a.file, tmp)
                tmp_path = tmp.name
            from extractors.gst_extractor import parse_gstr2a, cross_check_gst
            g2a = parse_gstr2a(tmp_path)
            cross = cross_check_gst(gst_data_out, g2a) if gst_data_out else {}
            SESSION["gstr2a"]   = g2a
            SESSION["cross_gst"] = cross
            os.unlink(tmp_path)
            progress.append(f"GSTR-2A parsed: purchases INR {g2a.get('total_purchases_crore',0)} Cr")
        except Exception as e:
            progress.append(f"GSTR-2A parse failed: {e}")

    # Bank Statement
    bank_credits_val       = 0
    avg_monthly_credits_val= 0
    if bank_statement and bank_statement.filename:
        try:
            ext = bank_statement.filename.rsplit(".", 1)[-1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                shutil.copyfileobj(bank_statement.file, tmp)
                tmp_path = tmp.name
            if ext in ("xlsx", "xls", "csv"):
                bank_out = parse_bank_excel(tmp_path)
            else:
                bank_out = parse_bank_pdf(tmp_path)
            cross_bank = cross_check_gst_vs_bank(gst_turnover_val, bank_out.get("total_credits_crore", 0)) if gst_turnover_val else {}
            SESSION["bank"]           = bank_out
            SESSION["cross_check_bank"] = cross_bank
            bank_credits_val        = bank_out.get("total_credits_crore", 0)
            avg_monthly_credits_val = bank_out.get("avg_monthly_credits_crore", 0)
            os.unlink(tmp_path)
            progress.append(f"Bank statement parsed: credits INR {bank_credits_val} Cr")
        except Exception as e:
            progress.append(f"Bank statement parse failed: {e}")

    # ── STEP 2: Web Research ──────────────────────────────────────────────────
    research_out = {}
    try:
        research_out = run_full_research(
            company_name   = company_name,
            promoter_name  = promoter_name,
            sector         = sector,
            cin            = cin or None,
            state          = state or None,
            tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY"),
        )
        SESSION["research"] = research_out
        progress.append(f"Research done: {research_out.get('signal_count',0)} signals, risk={research_out.get('overall_research_risk','?')}")
    except Exception as e:
        progress.append(f"Research failed: {e}")

    # ── STEP 3: Merge financials (docs override manual inputs) ────────────────
    # Priority: extracted from docs > manually provided in form
    def _pick(doc_val, form_val):
        """Use doc value if non-zero/non-None, else fall back to form value."""
        if doc_val and doc_val not in (0, "N/A", "", None):
            return doc_val
        return form_val if form_val not in (0, None) else "N/A"

    merged_fin = {
        "revenue":               _pick(fin_from_docs.get("revenue"),            revenue),
        "net_profit_margin_pct": _pick(fin_from_docs.get("net_profit_margin_pct"), net_profit_margin_pct),
        "ebitda":                _pick(fin_from_docs.get("ebitda"),              ebitda),
        "total_debt":            _pick(fin_from_docs.get("total_debt"),          total_debt),
        "equity":                _pick(fin_from_docs.get("equity"),              net_worth_crore),
        "debt_equity_ratio":     _pick(fin_from_docs.get("debt_equity_ratio"),   debt_equity_ratio),
        "current_ratio":         _pick(fin_from_docs.get("current_ratio"),       current_ratio),
        "dscr":                  dscr,
        "collateral_coverage":   collateral_coverage_ratio,
        "working_capital_days":  working_capital_days,
        "fy":                    fin_from_docs.get("fy", "2024"),
    }

    gst_compliance_final = _pick(gst_compliance_pct_val, 0)
    gst_turnover_final   = _pick(gst_turnover_val, 0)
    bank_credits_final   = _pick(bank_credits_val, 0)

    # ── STEP 4: Compute Five C's Score ────────────────────────────────────────
    character_data = {
        "cibil_score":        cibil_score,
        "litigation_count":   research_out.get("results",{}).get("litigation",{}).get("case_count", 0),
        "gst_compliance_pct": gst_compliance_final,
    }
    capacity_data = {
        "net_profit_margin_pct": net_profit_margin_pct,
        "dscr":                  dscr,
        "revenue_growth_pct":    revenue_growth_pct,
        "working_capital_days":  working_capital_days,
        "requested_amount_crore":requested_amount_crore,
    }
    capital_data = {
        "debt_equity_ratio": debt_equity_ratio,
        "current_ratio":     current_ratio,
        "net_worth_crore":   net_worth_crore,
    }
    collateral_data = {
        "collateral_coverage_ratio": collateral_coverage_ratio,
        "title_clear":               True,
        "collateral_type":           "property",
    }
    conditions_data = {
        "sector_outlook":       sector_outlook,
        "rbi_regulatory_flags": research_out.get("results",{}).get("rbi_circulars",{}).get("count", 0),
        "news_sentiment":       research_out.get("news_sentiment", news_sentiment),
    }

    risk_out = compute_overall_score(character_data, capacity_data, capital_data, collateral_data, conditions_data)

    # Qualitative boost from officer notes
    qualitative_boost = 0
    if capacity_utilization_pct >= 75:
        qualitative_boost += 3
    if management_quality == "strong":
        qualitative_boost += 4
    if site_visit_positive:
        qualitative_boost += 2
    if qualitative_boost:
        risk_out["scores"]["overall"] = min(100, risk_out["scores"]["overall"] + qualitative_boost)
        risk_out["qualitative_boost"] = qualitative_boost
        risk_out["explainability"].append(
            ("positive", f"Qualitative assessment by Credit Officer: +{qualitative_boost} pts")
        )
    SESSION["risk_score"] = risk_out
    progress.append(
        f"Score computed: {risk_out.get('scores',{}).get('overall',0)}/100 "        f"→ {risk_out.get('decision','?')} "        f"INR {risk_out.get('suggested_limit_crore',0)} Cr at {risk_out.get('interest_rate_pct',0)}%"
    )

    # ── STEP 5: Build CAM data and generate document ──────────────────────────
    cam_data = {
        "company_info": {
            "name":      company_name,
            "cin":       cin or "N/A",
            "sector":    sector,
            "promoter":  promoter_name,
            "address":   address or "N/A",
            "founded":   founded or "N/A",
            "employees": employees or "N/A",
        },
        "financials": {
            **merged_fin,
            "net_profit": round(
                (merged_fin.get("revenue") or 0) *
                (merged_fin.get("net_profit_margin_pct") or 0) / 100, 2
            ),
        },
        "gst_data": {
            "compliance_pct":          gst_compliance_final,
            "declared_turnover_crore": gst_turnover_final,
        },
        "bank_data": {
            "total_credits_crore":       bank_credits_final,
            "avg_monthly_credits_crore": avg_monthly_credits_val or "N/A",
        },
        "cross_check_bank": SESSION.get("cross_check_bank", {}),
        "research":          research_out,
        "scores":            risk_out.get("scores", {}),
        "recommendation": {
            **risk_out,
            "limit_crore":     risk_out.get("suggested_limit_crore", 0),
            "rate_pct":        risk_out.get("interest_rate_pct", 0),
            "rate_breakdown":  risk_out.get("rate_breakdown", "MCLR + Spread"),
            "requested_crore": requested_amount_crore,
            "risk_band":       risk_out.get("risk_band", "Moderate Risk"),
        },
        "explainability":  risk_out.get("explainability", []),
        "officer_notes": {
            "capacity_utilization":  f"Factory at {capacity_utilization_pct}% capacity",
            "management_quality":    management_quality,
            "collateral_assessment": f"Coverage: {collateral_coverage_ratio}x",
        },
    }

    doc_bytes = generate_cam(cam_data)
    slug      = company_name.replace(" ", "_")[:30]
    filename  = f"CAM_{slug}_{datetime.now().strftime('%Y%m%d')}.docx"

    # Log pipeline summary to console
    print("=== Pipeline Summary ===")
    for step in progress:
        print(f"  ✓ {step}")
    print("========================")

    return Response(
        content=doc_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# ─── ENDPOINT 8: Reset Session ───────────────────────────────────────────────
@app.post("/session/reset")
def reset_session():
    SESSION.clear()
    return {"success": True, "message": "Session cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


