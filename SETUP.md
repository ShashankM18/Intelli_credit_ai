# IntelliCredit — Phase 1 Setup Guide

## ⚡ Quick Start (5 minutes)

### 1. Install Python dependencies
```bash
cd intelli-credit/backend
pip install -r requirements.txt
```

### 2. (Optional) Install Tesseract OCR for scanned documents
```bash
# Ubuntu / Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Windows
# Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
```

### 3. Run the backend server
```bash
cd intelli-credit/backend
uvicorn main:app --reload --port 8000
```

### 4. Open API docs in browser
```
http://localhost:8000/docs
```
Interactive Swagger UI — test all endpoints directly.

---

## 📡 API Endpoints

| Method | Endpoint | What it does |
|--------|----------|--------------|
| POST | `/upload/annual-report` | Upload PDF annual report → extract financials |
| POST | `/upload/gstr3b` | Upload GSTR-3B Excel/CSV → turnover + compliance |
| POST | `/upload/gstr2a` | Upload GSTR-2A → purchases + circular trading check |
| POST | `/upload/bank-statement` | Upload bank statement → credits + bounce flags |
| POST | `/upload/scanned` | Upload scanned PDF/image → OCR extraction |
| GET  | `/analysis/summary` | Get all extracted data + cross-checks |
| POST | `/analysis/risk-score` | Compute Five C's score + decision |
| POST | `/session/reset` | Clear session |

---

## 🧪 Test with Sample Data

```bash
# Test annual report upload
curl -X POST http://localhost:8000/upload/annual-report \
  -F "file=@sample_annual_report.pdf"

# Test GST upload
curl -X POST http://localhost:8000/upload/gstr3b \
  -F "file=@sample_gstr3b.xlsx"

# Get full summary
curl http://localhost:8000/analysis/summary

# Compute risk score
curl -X POST http://localhost:8000/analysis/risk-score \
  -H "Content-Type: application/json" \
  -d '{
    "cibil_score": 742,
    "litigation_count": 0,
    "dscr": 1.48,
    "revenue_growth_pct": 12.4,
    "working_capital_days": 94,
    "debt_equity_ratio": 1.42,
    "current_ratio": 1.89,
    "net_worth_crore": 38.2,
    "collateral_coverage_ratio": 1.8,
    "requested_amount_crore": 25,
    "sector_outlook": "headwinds",
    "news_sentiment": "positive",
    "officer_notes": {
      "capacity_utilization_pct": 78,
      "management_quality": "strong",
      "site_visit_positive": true
    }
  }'
```

---

## 🏗️ Architecture

```
Browser (React UI)
      │
      ▼ HTTP (localhost:8000)
┌─────────────────────────┐
│   FastAPI Backend        │
│   main.py               │
├─────────────────────────┤
│ extractors/             │
│   pdf_extractor.py  ←── pdfplumber + PyMuPDF
│   gst_extractor.py  ←── pandas
│   bank_extractor.py ←── pandas + pdfplumber
│   ocr_extractor.py  ←── Tesseract
├─────────────────────────┤
│ analyzer/               │
│   risk_scorer.py    ←── Pure Python weighted scoring
└─────────────────────────┘
```

---

## 🎯 What Phase 1 Delivers

✅ Upload any of: PDF annual report, GSTR-3B, GSTR-2A, bank statement (PDF/Excel), scanned image
✅ Automatic OCR fallback for scanned PDFs
✅ Cross-verification: GST vs Bank (revenue inflation detection)
✅ Circular trading detection (GSTR-3B vs 2A)
✅ Bounce/ECS return detection in bank statements
✅ Five C's risk scoring engine with qualitative officer input
✅ Explainable decision logic (no black box)

## Next Phases
- Phase 2: Web Research Agent (news crawling, eCourts, MCA)
- Phase 3: CAM Report Generator (python-docx)
- Phase 4: React frontend integration
