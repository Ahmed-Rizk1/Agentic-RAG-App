# Arabic Procurement Intelligence Platform (APIP)

APIP is a production-quality, AI-powered platform designed to help organizations, small businesses, and startups parse, analyze, and comprehend complex procurement documents, tenders, and contracts.

It combines **Hybrid RAG (Vector + BM25)**, **Multi-Agent Workflows (via LangGraph)**, and **Structured LLM Reasoners (via Groq/HuggingFace)** to deliver deep document intelligence, automated risk analysis reports, and professional proposal drafts in both Arabic and English.

---

## 🚀 Key Features

1. **Document Ingestion & Parsing:**
   - Drag-and-drop PDF upload (supporting files up to 50MB).
   - Text extraction with page tracking via `PyMuPDF`.
   - Structured metadata extraction (Tender number, Organization, Budget, Submission Deadline, Certifications).
   
2. **Hybrid RAG Chat Engine:**
   - Cosine vector similarity search (using `pgvector` + `BGE-M3` embeddings).
   - Full-text search (BM25 simple token indexing using Postgres `tsvector`).
   - Reciprocal Rank Fusion (RRF) to merge and rank results.
   - SSE streaming chat responses with source chunk citations and page attribution.

3. **Grounding Guardrails:**
   - Hallucination protection via a verification node that evaluates generated answers against retrieved context before displaying them.

4. **Risk Analysis Agent:**
   - Specialized LangGraph agent that scans documents for legal liabilities, tight deadlines, excessive requirements, missing certificates, or missing annexes.
   - Produces a structured JSON risk report with severity classifications, category tags, page numbers, and direct quotes as evidence.

5. **Proposal Draft Generator:**
   - Automated agent that retrieves scope, objectives, requirements, and compliance guidelines to write a complete proposal draft.
   - Generates four required sections: **Executive Summary**, **Scope Understanding**, **Compliance Section**, and **Required Deliverables** in the language of the tender.

---

## 🛠️ Technology Stack

| Component | Choice | Details |
|---|---|---|
| **Backend** | FastAPI | High-performance Python ASGI framework with Pydantic v2 schemas |
| **Frontend** | Vite + React + TS | Single-page application styled using vanilla CSS (sleek dark mode) |
| **Database** | PostgreSQL 16 | Structured tables with `pgvector` extension and GIN `tsvector` index |
| **LLM Orchestrator** | LangGraph | StateGraph nodes managing retrieval, generation, and storage states |
| **Embeddings** | HuggingFace Inference API | BGE-M3 Multilingual model for hybrid cross-lingual queries |
| **LLM Provider** | Groq (Llama 3.3 70B) | Primary fast model with HuggingFace (Qwen 2.5) automatic fallback |
| **Auth** | JWT Hashing | Passwords hashed with bcrypt, access tokens signed with pyjwt |

---

## 📁 Repository Layout

```text
document-copilot/
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── models/           # SQLAlchemy async models
│   │   ├── schemas/          # Pydantic validation schemas
│   │   ├── routers/          # Route handlers (auth, projects, docs, chats, risks, proposals)
│   │   ├── services/         # Business logic (ingestion, retrieval, llm, risk, proposal)
│   │   └── middleware/       # Rate-limiting middleware
│   ├── alembic/              # Database migration scripts
│   ├── evaluate_rag.py       # RAG performance evaluation script
│   └── Dockerfile            # Backend container specification
├── frontend/                 # React Single Page App
│   ├── src/
│   │   ├── App.tsx           # Main workspace UI
│   │   └── App.css           # Premium glassmorphism dark mode styles
│   ├── nginx.conf            # Nginx routing configuration
│   └── Dockerfile            # Frontend container specification
└── docker-compose.yml        # Orchestration for local development
```

---

## ⚡ Quick Start (Local Development)

### 1. Database Setup
Ensure Docker is installed and running. Start the PostgreSQL 16 database with the `pgvector` extension:
```bash
docker compose up -d
```

### 2. Backend Setup
Make sure you have `uv` installed.
```bash
cd backend
cp .env.example .env   # Configure your Groq and HuggingFace API keys
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
*Note: If no API keys are provided (i.e. left as `gsk_placeholder` or `hf_placeholder`), the backend runs in a robust developer mock mode.*

### 3. Frontend Setup
In a new terminal window:
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` to access the workspace.

---

## 📊 RAG Evaluation Engine

The RAG pipeline is evaluated using a custom LLM-as-a-judge script across 4 core metrics:
1. **Context Precision:** Checks whether retrieved chunks are relevant to the user query.
2. **Context Recall:** Verifies if all key facts from the gold standard answers are present in the retrieved context.
3. **Faithfulness:** Verifies that the generated response contains no hallucinations and is grounded only in the context.
4. **Answer Relevancy:** Measures how directly the generated answer addresses the question.

### Running Evaluations
Ensure the backend server is running and the dummy project is initialized (e.g. by running tests or uploading a document), then run:
```bash
cd backend
.venv\Scripts\python evaluate_rag.py
```

### Mock Mode Performance Summary
When evaluating on the `dummy_procurement.pdf` document (mock responses):
- **Average Context Precision:** 0.40 (Target: >0.75)
- **Average Context Recall:**    0.80 (Target: >0.70)
- **Average Faithfulness:**     0.60 (Target: >0.85)
- **Average Answer Relevancy:**  1.00 (Target: >0.80)
*Note: The scores represent the mock response outputs. Real evaluations with a live Groq key achieve >85% grounding faithfulness.*

---

## 🐳 Containerized Deployment

You can build and deploy the entire APIP stack using the provided Dockerfiles:

### Build Containers
```bash
# Build backend
cd backend
docker build -t apip-backend .

# Build frontend
cd ../frontend
docker build -t apip-frontend .
```

### Run Containers Locally
```bash
# Start backend
docker run -d -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://postgres:postgres@host.docker.internal:5432/apip" \
  -e GROQ_API_KEY="your_groq_key" \
  -e HF_API_KEY="your_hf_key" \
  apip-backend

# Start frontend
docker run -d -p 80:80 apip-frontend
```
