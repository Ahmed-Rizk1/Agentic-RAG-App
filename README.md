# Agentic RAG — Enterprise Document Intelligence Platform

An enterprise-grade, production-ready **Agentic RAG Platform** engineered for deep document parsing, complex contract analysis, and automated executive report generation across multi-lingual documents (Arabic & English).

The system integrates **Hybrid RAG (Dense Vector + BM25 Sparse Search)**, **Multi-Agent State Machines (LangGraph)**, **Self-Correction Grounding Guardrails**, **Redis Caching**, and **HNSW Indexing** to deliver high-precision document intelligence with sub-5ms retrieval speeds.

---

## 🚀 Key Features & Capabilities

1. **Document Ingestion & Asynchronous Parsing:**
   - Multi-format PDF processing with page-level tracking via `PyMuPDF`.
   - Non-blocking background worker pipeline using FastAPI `BackgroundTasks`.

2. **Hybrid RAG Retrieval Engine:**
   - **Dense Vector Search:** Cosine similarity search using `pgvector` with **HNSW indexing** and `BGE-M3` multilingual embeddings.
   - **Sparse Full-Text Search:** BM25 token indexing via PostgreSQL `tsvector` with GIN indexes.
   - **Rank Fusion:** Reciprocal Rank Fusion (RRF) algorithm to rank combined search results.
   - **Streaming SSE Chat:** Token-by-token streaming with page attribution and source chunk citations.

3. **Self-Correction & Grounding Guardrails (Corrective RAG):**
   - Hallucination verification node that evaluates generated answers against retrieved context before streaming to the client.
   - Intelligent query router distinguishing casual statements from document queries.

4. **Multi-Agent Risk Analysis Workflows:**
   - Specialized **LangGraph StateGraph Agent** scanning documents for legal liabilities, tight deadlines, penalty clauses, and compliance requirements.
   - Produces structured JSON risk reports with severity classifications and direct page quotes.

5. **Proposal Generation Agent:**
   - Autonomous agent that analyzes scope and technical guidelines to write complete 4-part proposals (*Executive Summary*, *Scope Understanding*, *Compliance*, and *Required Deliverables*).

6. **Enterprise Performance & Caching:**
   - **Redis Caching Layer (`redis.asyncio`)**: Caches query vector embeddings by text hash with graceful in-memory fallback.
   - **SQLAlchemy Connection Pooling (`asyncpg`)**: Configured pool size and health pre-pings for concurrent SSE streaming.

---

## 🛠️ Technology Stack

| Layer | Technology | Details |
|---|---|---|
| **Backend API** | FastAPI | Async ASGI Python backend with Pydantic v2 schemas |
| **Frontend** | React 18 + Vite + TypeScript | Glassmorphism dark mode SPA with responsive RTL/LTR support |
| **Database** | PostgreSQL 16 | Relational tables + `pgvector` extension with HNSW index |
| **Caching & Queue** | Redis 7 | `redis.asyncio` caching layer with in-memory fallback |
| **Agent Orchestrator** | LangGraph | Multi-node `StateGraph` workflows for Risk & Proposal agents |
| **Embeddings** | HuggingFace Inference API | `BAAI/bge-m3` multilingual embeddings |
| **LLM Inference** | Groq (Llama 3.3 70B) | High-speed primary LLM with HuggingFace fallback |
| **Security & Auth** | JWT + Bcrypt | Password hashing with bcrypt, access tokens signed with PyJWT |

---

## 📁 Repository Layout

```text
apip/
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── models/           # SQLAlchemy async models
│   │   ├── schemas/          # Pydantic validation schemas
│   │   ├── routers/          # API Route handlers
│   │   ├── services/         # Core business logic (RAG, Cache, LLM, Risk, Proposal)
│   │   └── middleware/       # Rate-limiting middleware
│   ├── alembic/              # Database migration scripts (Schema + HNSW vector index)
│   ├── evaluate_rag.py       # RAG performance evaluation script
│   └── Dockerfile            # Backend container specification
├── frontend/                 # React Single Page Application
│   ├── src/                  # App components and state management
│   ├── nginx.conf            # Production Nginx routing configuration
│   └── Dockerfile            # Frontend container specification
└── docker-compose.yml        # Multi-container orchestration (Postgres, Redis)
```

---

## ⚡ Quick Start (Local Development)

### 1. Start Infrastructure (Postgres + Redis)
```bash
docker compose up -d
```

### 2. Backend Setup
```bash
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
*Note: If API keys are unconfigured, the application gracefully operates in developer mock mode.*

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.

---

## 🌐 Simple Production Deployment Guide

Deploying this platform is straightforward using cloud services or a single server:

### Option A: Cloud Deployment (Railway / Render + Supabase) — Recommended

1. **Database (Supabase / Managed Postgres)**:
   - Create a free PostgreSQL 16 database on [Supabase](https://supabase.com) or Railway.
   - Enable `pgvector` extension in the SQL editor: `CREATE EXTENSION IF NOT EXISTS vector;`.

2. **Backend Service (Railway or Render)**:
   - Connect your GitHub repository to [Railway.app](https://railway.app) or [Render.com](https://render.com).
   - Set the root directory to `backend`.
   - Set Environment Variables:
     - `DATABASE_URL` (Your PostgreSQL connection string)
     - `REDIS_URL` (Railway Redis instance URL)
     - `JWT_SECRET` (Random secret key)
     - `GROQ_API_KEY` & `HF_API_KEY`
   - Build Command: `uv sync && uv run alembic upgrade head`
   - Start Command: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`

3. **Frontend Service (Vercel / Netlify / Render)**:
   - Connect your GitHub repo to [Vercel](https://vercel.com) or Netlify.
   - Set root directory to `frontend`.
   - Build Command: `npm run build`
   - Output Directory: `dist`

---

### Option B: Docker Compose Deployment (Single VPS / Server)

To deploy on any cloud VPS (DigitalOcean, AWS EC2, Hetzner):

```bash
# 1. Clone the repository
git clone https://github.com/Ahmed-Rizk1/APIP.git
cd APIP

# 2. Configure production .env
cp backend/.env.example backend/.env

# 3. Start full stack using Docker Compose
docker compose up -d --build
```

---

## 📊 RAG Evaluation Engine

The RAG pipeline includes an LLM-as-a-judge evaluation suite testing 4 core metrics:
1. **Context Precision:** Evaluates relevance of retrieved chunks to user query.
2. **Context Recall:** Verifies if gold-standard facts are captured in context.
3. **Faithfulness:** Verifies responses are 100% grounded without hallucinations.
4. **Answer Relevancy:** Measures directness of generated answers.

To execute RAG evaluation benchmarks:
```bash
cd backend
uv run python evaluate_rag.py
```
