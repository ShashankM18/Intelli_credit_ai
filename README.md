# Intelli Credit

Intelli Credit is a full‑stack application for analysing financial documents (such as bank statements, GST returns, and PDFs) and extracting structured insights to support credit decisioning. It consists of:

- **Backend**: FastAPI service (Python) for document upload, parsing, OCR, and analytics.
- **Frontend**: React + Vite UI for interacting with the analysis workflows.

---

## Project Structure

- `backend/` – FastAPI application and document processing code  
- `frontend/` – React (Vite) single‑page application  
- `pipeline_sample/` – Sample input documents (can be used for local testing)  

---

## Prerequisites

- **Git**
- **Node.js** (v18+ recommended)
- **Python** 3.10+
- **pip** (Python package manager)

Optional (for OCR features):

- **Tesseract OCR** installed and available on `PATH`

---

## Backend Setup (FastAPI)

From the project root:

```bash
cd backend
```

### 1. Create and activate a virtual environment (recommended)

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the backend server

```bash
uvicorn main:app --reload
```

- The API will typically be available at: `http://127.0.0.1:8000`
- FastAPI docs UI: `http://127.0.0.1:8000/docs`

> **Note**: If your application entrypoint module is not `main.py` or the FastAPI app is not named `app`, update the `uvicorn` command accordingly (e.g. `uvicorn src.app:app --reload`).

---

## Frontend Setup (React + Vite)

Open a new terminal from the project root:

```bash
cd frontend
```

### 1. Install dependencies

```bash
npm install
```

### 2. Run the development server

```bash
npm run dev
```

By default, Vite runs on `http://127.0.0.1:5173` (or a nearby port).  
Ensure any API base URLs in the frontend are pointing to your local backend (e.g. `http://127.0.0.1:8000`).

---

## Typical Local Development Flow

1. **Start backend**  
   - In `backend/`: `uvicorn main:app --reload`

2. **Start frontend**  
   - In `frontend/`: `npm run dev`

3. Open the app in your browser (Vite dev URL, usually `http://127.0.0.1:5173`) and interact with the UI.  
4. Use sample documents from `pipeline_sample/` to test uploads and analysis.

---

## Building for Production

### Frontend build

```bash
cd frontend
npm run build
```

This creates an optimized production build in `frontend/dist/`.

### Backend deployment

- Install dependencies from `backend/requirements.txt` in your target environment.
- Run the FastAPI app with a production ASGI server (e.g. `uvicorn` or `gunicorn` with `uvicorn.workers.UvicornWorker`).
- Optionally serve the frontend build (`frontend/dist/`) via a static file server or via the backend, depending on your deployment strategy.

---

## Notes

- Some features (especially OCR) require Tesseract to be installed on the host OS.
- If you encounter errors related to document parsing (PDF/Excel), ensure system‑level libraries for fonts and file formats are installed and that `openpyxl`, `xlrd`, and `PyMuPDF` from `requirements.txt` installed correctly.

