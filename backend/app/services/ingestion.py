import os
import uuid
import logging
import httpx
import fitz
import numpy as np
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.document import Document, DocumentStatus, DocumentType, DocumentMetadata
from app.models.chunk import Chunk

logger = logging.getLogger(__name__)

# --- State Schema ---
class IngestionState(TypedDict):
    document_id: str
    file_path: str
    project_id: str
    status: str
    error: Optional[str]
    
    # Processed data
    page_count: Optional[int]
    doc_type: Optional[str]
    metadata: Optional[dict]
    chunks: Optional[list[dict]]


# --- Helper Functions ---

def chunk_text(text: str, page_number: int, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[dict]:
    """Splits page text into overlapping chunks matching word boundaries."""
    chunks = []
    text_len = len(text)
    start = 0
    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            # Look back for word boundaries (spaces/newlines) in the last 10% of window
            lookback = int(chunk_size * 0.1)
            found_boundary = False
            for i in range(end, end - lookback, -1):
                if text[i - 1] in ("\n", " ", "\t"):
                    end = i
                    found_boundary = True
                    break
        
        chunk_content = text[start:end].strip()
        if chunk_content:
            chunks.append({
                "content": chunk_content,
                "page_number": page_number,
                "start_char": start,
                "end_char": end
            })
        
        if end == text_len:
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


from app.services.llm import call_llm_json
from app.services.cache import cache_service

async def call_hf_embeddings(texts: list[str]) -> list[list[float]]:
    """Calls Hugging Face Inference API for BGE-M3 embeddings with Redis/in-memory caching."""
    if not texts:
        return []

    # 1. Check cache for cached embeddings
    results: list[Optional[list[float]]] = [None] * len(texts)
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    for idx, text in enumerate(texts):
        cached_vec = await cache_service.get_embedding(text)
        if cached_vec is not None:
            results[idx] = cached_vec
        else:
            uncached_indices.append(idx)
            uncached_texts.append(text)

    if not uncached_texts:
        return [res for res in results if res is not None]

    dim = 1024
    fetched_embeddings: list[list[float]] = []

    if settings.hf_api_key == "hf_placeholder":
        # Generate mock embeddings for uncached texts
        logger.warning("HF API key is placeholder. Returning mock random embeddings.")
        for text in uncached_texts:
            np.random.seed(hash(text) % 2**32)
            vec = np.random.randn(dim)
            vec = vec / np.linalg.norm(vec)
            fetched_embeddings.append(vec.tolist())
    else:
        url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{settings.hf_embedding_model}"
        headers = {"Authorization": f"Bearer {settings.hf_api_key}"}
        batch_size = 16

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=3.0)) as client:
                for i in range(0, len(uncached_texts), batch_size):
                    batch = uncached_texts[i:i + batch_size]
                    response = await client.post(
                        url, 
                        headers=headers, 
                        json={"inputs": batch, "options": {"wait_for_model": True}}
                    )
                    if response.status_code != 200:
                        raise Exception(f"Hugging Face embedding API failed: {response.text}")
                    
                    res_json = response.json()
                    if isinstance(res_json, list):
                        if len(batch) == 1 and not isinstance(res_json[0], list):
                            fetched_embeddings.append(res_json)
                        else:
                            fetched_embeddings.extend(res_json)
                    else:
                        raise Exception(f"Unexpected HF response format: {res_json}")
        except Exception as e:
            logger.warning(f"HF embedding connection/API failed: {str(e)}. Falling back to mock embeddings.")
            for text in uncached_texts:
                np.random.seed(hash(text) % 2**32)
                vec = np.random.randn(dim)
                vec = vec / np.linalg.norm(vec)
                fetched_embeddings.append(vec.tolist())

    # 2. Store newly fetched embeddings in cache and populate results
    for idx_pos, orig_idx in enumerate(uncached_indices):
        vec = fetched_embeddings[idx_pos]
        results[orig_idx] = vec
        await cache_service.set_embedding(uncached_texts[idx_pos], vec)

    return [res for res in results if res is not None]


# --- Graph Nodes ---

async def parse_pdf_node(state: IngestionState) -> IngestionState:
    """Parses PDF text and splits it into chunks."""
    logger.info(f"Starting PDF parsing for document {state['document_id']}")
    try:
        doc = fitz.open(state["file_path"])
        page_count = len(doc)
        
        all_chunks = []
        for idx in range(page_count):
            page = doc[idx]
            text = page.get_text()
            page_chunks = chunk_text(text, idx + 1)
            all_chunks.extend(page_chunks)
            
        doc.close()
        
        state["page_count"] = page_count
        state["chunks"] = all_chunks
        state["status"] = "parsed"
        return state
    except Exception as e:
        logger.error(f"Error parsing PDF: {str(e)}")
        state["error"] = f"Parsing Error: {str(e)}"
        state["status"] = "failed"
        return state


async def classify_and_extract_node(state: IngestionState) -> IngestionState:
    """Classifies document and extracts metadata using Groq."""
    if state.get("error"):
        return state
        
    logger.info(f"Classifying and extracting metadata for document {state['document_id']}")
    try:
        # Construct sample content from first ~5 pages
        first_pages = []
        chunks = state["chunks"] or []
        for chunk in chunks:
            if chunk["page_number"] <= 5:
                first_pages.append(chunk["content"])
        
        sample_text = "\n".join(first_pages)[:8000] # Cap at 8k chars
        if not sample_text:
            sample_text = "No text content found in document."
            
        # 1. Classification
        system_class_prompt = "You are an expert document classifier. Return JSON format."
        class_prompt = (
            "Classify the following document content into one of the following types:\n"
            "- tender\n- contract\n- rfp\n- procurement\n- unknown\n\n"
            f"Content:\n{sample_text}\n\n"
            "Respond ONLY with a JSON object: {\"doc_type\": \"tender\" | \"contract\" | \"rfp\" | \"procurement\" | \"unknown\"}"
        )
        class_res = await call_llm_json(class_prompt, system_class_prompt, "ingestion_classify")
        state["doc_type"] = class_res.get("doc_type", "unknown")
        
        # 2. Metadata Extraction
        system_meta_prompt = "You are an expert metadata extraction system. Return JSON format."
        meta_prompt = (
            "Extract metadata from the following document content (which may be in Arabic or English):\n"
            "- organization_name (The public or private organization issuing the tender/request)\n"
            "- tender_number (The official reference number of the tender/procurement, if present)\n"
            "- submission_deadline (The deadline date, e.g., 'YYYY-MM-DD' or similar description)\n"
            "- budget_amount (The total budget estimate, if present, as a float number)\n"
            "- budget_currency (The currency, e.g., 'SAR', 'USD', 'AED', 'EGP', etc.)\n"
            "- certifications (List of required certifications, standards, or qualifications, e.g., ISO, classification grade, etc.)\n"
            "- language (The primary language of the document, e.g. 'ar' or 'en')\n\n"
            f"Content:\n{sample_text}\n\n"
            "Respond ONLY with a JSON object of this structure:\n"
            "{\n"
            "  \"organization_name\": string | null,\n"
            "  \"tender_number\": string | null,\n"
            "  \"submission_deadline\": string | null,\n"
            "  \"budget_amount\": number | null,\n"
            "  \"budget_currency\": string | null,\n"
            "  \"certifications\": list of strings | null,\n"
            "  \"language\": string | null\n"
            "}"
        )
        meta_res = await call_llm_json(meta_prompt, system_meta_prompt, "ingestion_metadata")
        # Store full response as raw extraction, and extract structured fields
        state["metadata"] = meta_res
        state["status"] = "metadata_extracted"
        return state
    except Exception as e:
        logger.error(f"Error classifying/extracting metadata: {str(e)}")
        state["error"] = f"AI Metadata Error: {str(e)}"
        state["status"] = "failed"
        return state


async def embed_chunks_node(state: IngestionState) -> IngestionState:
    """Generates embeddings for all document chunks."""
    if state.get("error"):
        return state
        
    logger.info(f"Generating embeddings for document {state['document_id']} ({len(state['chunks'] or [])} chunks)")
    try:
        chunks = state["chunks"] or []
        if not chunks:
            state["status"] = "embedded"
            return state
            
        texts = [c["content"] for c in chunks]
        embeddings = await call_hf_embeddings(texts)
        
        for idx, emb in enumerate(embeddings):
            chunks[idx]["embedding"] = emb
            
        state["chunks"] = chunks
        state["status"] = "embedded"
        return state
    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        state["error"] = f"Embedding Error: {str(e)}"
        state["status"] = "failed"
        return state


async def store_node(state: IngestionState) -> IngestionState:
    """Stores the fully processed document, chunks, and metadata in the database."""
    doc_id = uuid.UUID(state["document_id"])
    
    async with async_session() as db:
        try:
            # Fetch the document record
            result = await db.execute(select(Document).where(Document.id == doc_id))
            document = result.scalar_one_or_none()
            if not document:
                raise Exception(f"Document {doc_id} not found in database during store phase")
                
            if state.get("error"):
                document.status = DocumentStatus.failed
                document.processing_error = state["error"]
                await db.commit()
                return state
                
            # Update main document model
            document.status = DocumentStatus.ready
            document.page_count = state["page_count"]
            
            # Map doc_type string to enum
            try:
                document.doc_type = DocumentType(state["doc_type"])
            except ValueError:
                document.doc_type = DocumentType.unknown
                
            # Create DocumentMetadata
            meta = state["metadata"] or {}
            doc_metadata = DocumentMetadata(
                document_id=doc_id,
                organization_name=meta.get("organization_name"),
                tender_number=meta.get("tender_number"),
                submission_deadline=meta.get("submission_deadline"),
                budget_amount=meta.get("budget_amount"),
                budget_currency=meta.get("budget_currency"),
                certifications=meta.get("certifications"),
                language=meta.get("language"),
                raw_extraction=meta
            )
            db.add(doc_metadata)
            
            # Create Chunks
            for idx, chunk in enumerate(state["chunks"] or []):
                db_chunk = Chunk(
                    document_id=doc_id,
                    chunk_index=idx,
                    content=chunk["content"],
                    page_number=chunk["page_number"],
                    start_char=chunk["start_char"],
                    end_char=chunk["end_char"],
                    embedding=chunk.get("embedding")
                )
                db.add(db_chunk)
                
            await db.commit()
            state["status"] = "completed"
            logger.info(f"Successfully ingested document {doc_id}")
            return state
            
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
            await db.rollback()
            # Try to save error to document status
            try:
                result = await db.execute(select(Document).where(Document.id == doc_id))
                document = result.scalar_one_or_none()
                if document:
                    document.status = DocumentStatus.failed
                    document.processing_error = f"Database Save Error: {str(e)}"
                    await db.commit()
            except Exception as inner_e:
                logger.error(f"Failed to update document failure status: {str(inner_e)}")
            
            state["error"] = f"Database Save Error: {str(e)}"
            state["status"] = "failed"
            return state


# --- Build LangGraph workflow ---

workflow = StateGraph(IngestionState)

# Add nodes
workflow.add_node("parse", parse_pdf_node)
workflow.add_node("classify_and_extract", classify_and_extract_node)
workflow.add_node("embed", embed_chunks_node)
workflow.add_node("store", store_node)

# Add edges
workflow.set_entry_point("parse")
workflow.add_conditional_edges(
    "parse",
    lambda state: "store" if state.get("error") else "classify_and_extract",
    {"store": "store", "classify_and_extract": "classify_and_extract"}
)
workflow.add_conditional_edges(
    "classify_and_extract",
    lambda state: "store" if state.get("error") else "embed",
    {"store": "store", "embed": "embed"}
)
workflow.add_edge("embed", "store")
workflow.add_edge("store", END)

ingestion_graph = workflow.compile()


# --- Background worker runner ---

async def run_ingestion_workflow(document_id: str, file_path: str, project_id: str):
    """Entry point run as a FastAPI background task."""
    initial_state: IngestionState = {
        "document_id": document_id,
        "file_path": file_path,
        "project_id": project_id,
        "status": "started",
        "error": None,
        "page_count": None,
        "doc_type": None,
        "metadata": None,
        "chunks": None
    }
    
    # Mark document as processing initially
    doc_uuid = uuid.UUID(document_id)
    async with async_session() as db:
        result = await db.execute(select(Document).where(Document.id == doc_uuid))
        document = result.scalar_one_or_none()
        if document:
            document.status = DocumentStatus.processing
            await db.commit()
            
    try:
        await ingestion_graph.ainvoke(initial_state)
    except Exception as e:
        logger.error(f"Ingestion graph execution crashed: {str(e)}")
        # Make sure the status is set to failed
        async with async_session() as db:
            result = await db.execute(select(Document).where(Document.id == doc_uuid))
            document = result.scalar_one_or_none()
            if document and document.status != DocumentStatus.ready:
                document.status = DocumentStatus.failed
                document.processing_error = f"Graph Crash: {str(e)}"
                await db.commit()
