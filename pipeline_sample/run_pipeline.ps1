# ================================================================
# IntelliCredit — ONE SHOT Pipeline (PowerShell)
# Uploads all documents + sends company info → downloads CAM .docx
# ================================================================
# USAGE:
#   1. Place this script + sample files in the same folder
#   2. Run: .\run_pipeline.ps1
# ================================================================

$BASE_URL   = "http://localhost:8000"
$OUTPUT_DIR = $PSScriptRoot

Write-Host "`n================================================" -ForegroundColor Cyan
Write-Host "  IntelliCredit — One-Shot Pipeline" -ForegroundColor Cyan
Write-Host "================================================`n" -ForegroundColor Cyan

# Build multipart form with files + company info
$boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"

function Add-FormField($name, $value) {
    return "--$boundary$LF" +
           "Content-Disposition: form-data; name=`"$name`"$LF$LF" +
           "$value$LF"
}

function Add-FormFile($name, $filePath) {
    $fileName = Split-Path $filePath -Leaf
    $bytes    = [System.IO.File]::ReadAllBytes($filePath)
    $encoding = [System.Text.Encoding]::GetEncoding("iso-8859-1")
    $content  = $encoding.GetString($bytes)
    return "--$boundary$LF" +
           "Content-Disposition: form-data; name=`"$name`"; filename=`"$fileName`"$LF" +
           "Content-Type: application/octet-stream$LF$LF" +
           "$content$LF"
}

$body = ""

# ── Company Info ──────────────────────────────────────────────
$body += Add-FormField "company_name"              "Mumbai Pharma Industries Pvt Ltd"
$body += Add-FormField "promoter_name"             "Vikram Shah"
$body += Add-FormField "sector"                    "Pharma"
$body += Add-FormField "cin"                       "U24230MH2008PTC182345"
$body += Add-FormField "address"                   "Unit 12, MIDC Andheri East, Mumbai - 400093"
$body += Add-FormField "founded"                   "2008"
$body += Add-FormField "employees"                 "312"
$body += Add-FormField "state"                     "Maharashtra"
$body += Add-FormField "requested_amount_crore"    "18"

# ── Financial Inputs ──────────────────────────────────────────
$body += Add-FormField "revenue"                   "67.4"
$body += Add-FormField "net_profit_margin_pct"     "5.2"
$body += Add-FormField "ebitda"                    "9.1"
$body += Add-FormField "total_debt"                "26.8"
$body += Add-FormField "net_worth_crore"           "14.5"
$body += Add-FormField "debt_equity_ratio"         "1.85"
$body += Add-FormField "current_ratio"             "1.22"
$body += Add-FormField "dscr"                      "1.15"
$body += Add-FormField "working_capital_days"      "118"
$body += Add-FormField "collateral_coverage_ratio" "1.3"
$body += Add-FormField "cibil_score"               "698"
$body += Add-FormField "revenue_growth_pct"        "4.2"
$body += Add-FormField "sector_outlook"            "neutral"
$body += Add-FormField "capacity_utilization_pct"  "58"
$body += Add-FormField "management_quality"        "average"
$body += Add-FormField "site_visit_positive"       "false"

# ── Tavily Key (optional — leave empty to use Google RSS) ─────
$body += Add-FormField "tavily_api_key"            ""

# ── Attach Documents ──────────────────────────────────────────
$gstr3bFile = Join-Path $PSScriptRoot "sample_gstr3b.xlsx"
$gstr2aFile = Join-Path $PSScriptRoot "sample_gstr2a.xlsx"
$bankFile   = Join-Path $PSScriptRoot "sample_bank_statement.xlsx"

if (Test-Path $gstr3bFile) {
    Write-Host "  Attaching GSTR-3B..." -ForegroundColor Gray
    $body += Add-FormFile "gstr3b" $gstr3bFile
}
if (Test-Path $gstr2aFile) {
    Write-Host "  Attaching GSTR-2A..." -ForegroundColor Gray
    $body += Add-FormFile "gstr2a" $gstr2aFile
}
if (Test-Path $bankFile) {
    Write-Host "  Attaching Bank Statement..." -ForegroundColor Gray
    $body += Add-FormFile "bank_statement" $bankFile
}

$body += "--$boundary--$LF"

# ── Fire the request ──────────────────────────────────────────
Write-Host "`n  Sending to /pipeline/full..." -ForegroundColor Yellow
Write-Host "  (Research takes ~20 sec — please wait)`n" -ForegroundColor Gray

$outputPath = Join-Path $OUTPUT_DIR "CAM_MumbaiPharma.docx"

try {
    $encoding    = [System.Text.Encoding]::GetEncoding("iso-8859-1")
    $bodyBytes   = $encoding.GetBytes($body)
    $contentType = "multipart/form-data; boundary=$boundary"

    $response = Invoke-WebRequest -Uri "$BASE_URL/pipeline/full" `
        -Method POST `
        -ContentType $contentType `
        -Body $bodyBytes `
        -OutFile $outputPath

    if (Test-Path $outputPath) {
        $size = (Get-Item $outputPath).Length
        Write-Host "================================================" -ForegroundColor Green
        Write-Host "  SUCCESS!" -ForegroundColor Green
        Write-Host "  CAM Report saved: $outputPath" -ForegroundColor Green
        Write-Host "  File size: $([math]::Round($size/1024,1)) KB" -ForegroundColor Green
        Write-Host "================================================`n" -ForegroundColor Green
        # Auto-open the document
        Start-Process $outputPath
    }
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host "Make sure the server is running: uvicorn main:app --reload --port 8000" -ForegroundColor Yellow
}
