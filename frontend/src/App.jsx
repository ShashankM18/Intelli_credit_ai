import React, { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function App() {
  const [company, setCompany] = useState({
    company_name: "",
    promoter_name: "",
    sector: "",
    requested_amount_crore: "",
    cin: "",
    address: "",
    founded: "",
    employees: "",
    state: "",
  });

  const [financials, setFinancials] = useState({
    revenue: "",
    net_profit_margin_pct: "",
    ebitda: "",
    total_debt: "",
    net_worth_crore: "",
    debt_equity_ratio: "",
    current_ratio: "",
    dscr: "",
    working_capital_days: "",
    collateral_coverage_ratio: "",
    cibil_score: "",
    revenue_growth_pct: "",
    sector_outlook: "neutral",
    news_sentiment: "neutral",
    capacity_utilization_pct: "",
    management_quality: "average",
    site_visit_positive: false,
  });

  const [files, setFiles] = useState({
    annual_report: null,
    gstr3b: null,
    gstr2a: null,
    bank_statement: null,
  });

  const [tavilyKey, setTavilyKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  const handleCompanyChange = (e) => {
    const { name, value } = e.target;
    setCompany((prev) => ({ ...prev, [name]: value }));
  };

  const handleFinancialChange = (e) => {
    const { name, value, type, checked } = e.target;
    if (type === "checkbox") {
      setFinancials((prev) => ({ ...prev, [name]: checked }));
    } else {
      setFinancials((prev) => ({ ...prev, [name]: value }));
    }
  };

  const handleFileChange = (e) => {
    const { name, files: fileList } = e.target;
    setFiles((prev) => ({ ...prev, [name]: fileList[0] || null }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setMessage("");

    try {
      const formData = new FormData();

      // Company info
      Object.entries(company).forEach(([key, value]) => {
        formData.append(key, value || "");
      });

      // Tavily / state
      formData.append("tavily_api_key", tavilyKey || "");

      // Financials and qualitative inputs
      Object.entries(financials).forEach(([key, value]) => {
        if (typeof value === "boolean") {
          formData.append(key, String(value));
        } else {
          formData.append(key, value !== "" ? String(value) : "0");
        }
      });

      // Files (optional)
      Object.entries(files).forEach(([key, file]) => {
        if (file) {
          formData.append(key, file);
        }
      });

      const response = await fetch(`${API_BASE}/pipeline/full`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed with ${response.status}`);
      }

      const blob = await response.blob();
      const contentDisposition = response.headers.get("Content-Disposition") || "";
      const match = contentDisposition.match(/filename="?(.+)"?/i);
      const filename = match ? match[1] : "CAM_Report.docx";

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      setMessage("CAM document generated and downloaded.");
    } catch (err) {
      console.error(err);
      setMessage(`Failed to generate CAM: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              IntelliCredit
            </h1>
            <p className="text-sm text-slate-500">
              Minimal console to upload documents and generate CAM.
            </p>
          </div>
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
            Beta · Internal use
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8 space-y-8">
        <section className="grid gap-6 md:grid-cols-[2fr,1.5fr]">
          <form
            onSubmit={handleSubmit}
            className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
          >
            <div className="space-y-2">
              <h2 className="text-base font-semibold text-slate-900">
                Company information
              </h2>
              <p className="text-sm text-slate-500">
                Basic details required to run the full pipeline and build the CAM.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">
                  Company name<span className="text-rose-500">*</span>
                </label>
                <input
                  required
                  name="company_name"
                  value={company.company_name}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="Acme Textiles Pvt Ltd"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">
                  Promoter name<span className="text-rose-500">*</span>
                </label>
                <input
                  required
                  name="promoter_name"
                  value={company.promoter_name}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="Ramesh Agarwal"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">
                  Sector<span className="text-rose-500">*</span>
                </label>
                <input
                  required
                  name="sector"
                  value={company.sector}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="Textiles"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">
                  Requested amount (Cr)<span className="text-rose-500">*</span>
                </label>
                <input
                  required
                  type="number"
                  step="0.01"
                  name="requested_amount_crore"
                  value={company.requested_amount_crore}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="10"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">
                  CIN
                </label>
                <input
                  name="cin"
                  value={company.cin}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="U17111RJ2010PTC030452"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">
                  State
                </label>
                <input
                  name="state"
                  value={company.state}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="Rajasthan"
                />
              </div>
              <div className="space-y-1 md:col-span-2">
                <label className="text-sm font-medium text-slate-700">
                  Registered address
                </label>
                <input
                  name="address"
                  value={company.address}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="Full registered office address"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">
                  Year founded
                </label>
                <input
                  name="founded"
                  value={company.founded}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="2010"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700">
                  Employees
                </label>
                <input
                  type="number"
                  name="employees"
                  value={company.employees}
                  onChange={handleCompanyChange}
                  className="input"
                  placeholder="120"
                />
              </div>
            </div>

            <div className="space-y-2 pt-4 border-t border-slate-100">
              <h2 className="text-base font-semibold text-slate-900">
                Financial inputs (optional when uploading docs)
              </h2>
              <p className="text-sm text-slate-500">
                If documents are uploaded, extracted values will override these.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <NumberField
                label="Revenue (Cr)"
                name="revenue"
                value={financials.revenue}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="Net profit margin (%)"
                name="net_profit_margin_pct"
                value={financials.net_profit_margin_pct}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="EBITDA (Cr)"
                name="ebitda"
                value={financials.ebitda}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="Total debt (Cr)"
                name="total_debt"
                value={financials.total_debt}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="Net worth (Cr)"
                name="net_worth_crore"
                value={financials.net_worth_crore}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="Debt / Equity"
                name="debt_equity_ratio"
                value={financials.debt_equity_ratio}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="Current ratio"
                name="current_ratio"
                value={financials.current_ratio}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="DSCR"
                name="dscr"
                value={financials.dscr}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="Working capital days"
                name="working_capital_days"
                value={financials.working_capital_days}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="Collateral coverage (x)"
                name="collateral_coverage_ratio"
                value={financials.collateral_coverage_ratio}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="CIBIL score"
                name="cibil_score"
                value={financials.cibil_score}
                onChange={handleFinancialChange}
              />
              <NumberField
                label="Revenue growth (%)"
                name="revenue_growth_pct"
                value={financials.revenue_growth_pct}
                onChange={handleFinancialChange}
              />
              <SelectField
                label="Sector outlook"
                name="sector_outlook"
                value={financials.sector_outlook}
                onChange={handleFinancialChange}
                options={[
                  { value: "positive", label: "Positive" },
                  { value: "neutral", label: "Neutral" },
                  { value: "negative", label: "Negative" },
                ]}
              />
              <SelectField
                label="News sentiment"
                name="news_sentiment"
                value={financials.news_sentiment}
                onChange={handleFinancialChange}
                options={[
                  { value: "positive", label: "Positive" },
                  { value: "neutral", label: "Neutral" },
                  { value: "negative", label: "Negative" },
                ]}
              />
              <NumberField
                label="Capacity utilisation (%)"
                name="capacity_utilization_pct"
                value={financials.capacity_utilization_pct}
                onChange={handleFinancialChange}
              />
              <SelectField
                label="Management quality"
                name="management_quality"
                value={financials.management_quality}
                onChange={handleFinancialChange}
                options={[
                  { value: "strong", label: "Strong" },
                  { value: "average", label: "Average" },
                  { value: "weak", label: "Weak" },
                ]}
              />
              <div className="flex items-center gap-2 pt-6">
                <input
                  id="site_visit_positive"
                  type="checkbox"
                  name="site_visit_positive"
                  checked={financials.site_visit_positive}
                  onChange={handleFinancialChange}
                  className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                />
                <label
                  htmlFor="site_visit_positive"
                  className="text-sm text-slate-700"
                >
                  Site visit positive
                </label>
              </div>
            </div>

            <div className="space-y-2 pt-4 border-t border-slate-100">
              <h2 className="text-base font-semibold text-slate-900">
                Upload documents
              </h2>
              <p className="text-sm text-slate-500">
                All uploads are optional, but recommended for richer analytics.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <FileField
                label="Annual report (PDF)"
                name="annual_report"
                accept=".pdf"
                onChange={handleFileChange}
                file={files.annual_report}
              />
              <FileField
                label="GSTR-3B (Excel / CSV)"
                name="gstr3b"
                accept=".xlsx,.xls,.csv"
                onChange={handleFileChange}
                file={files.gstr3b}
              />
              <FileField
                label="GSTR-2A (Excel / CSV)"
                name="gstr2a"
                accept=".xlsx,.xls,.csv"
                onChange={handleFileChange}
                file={files.gstr2a}
              />
              <FileField
                label="Bank statement (PDF / Excel)"
                name="bank_statement"
                accept=".pdf,.xlsx,.xls,.csv"
                onChange={handleFileChange}
                file={files.bank_statement}
              />
            </div>

            <div className="space-y-2 pt-4 border-t border-slate-100">
              <h2 className="text-base font-semibold text-slate-900">
                Research API key (optional)
              </h2>
              <p className="text-sm text-slate-500">
                Used to power the web research agent (Tavily). Leave blank to skip.
              </p>
              <input
                type="password"
                className="input max-w-md"
                placeholder="TAVILY_API_KEY"
                value={tavilyKey}
                onChange={(e) => setTavilyKey(e.target.value)}
              />
            </div>

            <div className="flex items-center justify-between pt-2">
              <p className="text-xs text-slate-500">
                When you submit, documents are processed, research is run, scores are
                computed, and a CAM .docx is generated.
              </p>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {submitting ? "Generating CAM…" : "Run full pipeline & download CAM"}
              </button>
            </div>

            {message && (
              <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                {message}
              </div>
            )}
          </form>

          <aside className="space-y-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-900">
                How this console works
              </h3>
              <ol className="mt-2 space-y-1 text-sm text-slate-600">
                <li>1. Fill in basic company details.</li>
                <li>2. Optionally provide key financial inputs.</li>
                <li>3. Upload available documents (annual report, GST, bank).</li>
                <li>4. Optionally add Tavily API key for research.</li>
                <li>5. Submit to download the CAM Word document.</li>
              </ol>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-slate-900">
                API configuration
              </h3>
              <p className="mt-2 text-xs text-slate-600">
                The UI talks to the FastAPI backend at:
              </p>
              <p className="mt-1 rounded bg-slate-50 px-2 py-1 text-xs font-mono text-slate-700">
                {API_BASE}/pipeline/full
              </p>
              <p className="mt-2 text-xs text-slate-500">
                Override this by setting <span className="font-mono">VITE_API_BASE_URL</span> in a
                <span className="font-mono">.env</span> file in the frontend.
              </p>
            </div>
          </aside>
        </section>

        <footer className="border-t border-slate-200 pt-4 pb-8 text-xs text-slate-500">
          IntelliCredit · Internal credit risk tooling
        </footer>
      </main>
    </div>
  );
}

function NumberField({ label, name, value, onChange }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-slate-700">{label}</label>
      <input
        type="number"
        step="0.01"
        name={name}
        value={value}
        onChange={onChange}
        className="input"
      />
    </div>
  );
}

function SelectField({ label, name, value, onChange, options }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-slate-700">{label}</label>
      <select
        name={name}
        value={value}
        onChange={onChange}
        className="input"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function FileField({ label, name, accept, onChange, file }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-slate-700">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="file"
          name={name}
          accept={accept}
          onChange={onChange}
          className="block w-full text-xs text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white hover:file:bg-slate-800"
        />
      </div>
      {file && (
        <p className="text-[11px] text-slate-500 truncate">
          Selected: <span className="font-medium">{file.name}</span>
        </p>
      )}
    </div>
  );
}

export default App;

