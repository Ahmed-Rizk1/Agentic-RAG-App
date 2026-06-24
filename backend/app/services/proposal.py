import uuid
import logging
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.llm_log import ProposalDraft
from app.services.llm import call_llm_json

logger = logging.getLogger(__name__)

# --- Proposal State ---
class ProposalState(TypedDict):
    document_id: str
    text_context: Optional[str]
    proposal_data: Optional[dict]
    error: Optional[str]


# --- Nodes ---

async def retrieve_proposal_context_node(state: ProposalState) -> ProposalState:
    """Retrieves document text chunks related to scope, deliverables, requirements, and work description."""
    doc_id = uuid.UUID(state["document_id"])
    
    async with async_session() as db:
        try:
            # Load all chunks for document
            res = await db.execute(
                select(Chunk.content, Chunk.page_number)
                .where(Chunk.document_id == doc_id)
                .order_by(Chunk.chunk_index.asc())
            )
            chunks = res.all()
            if not chunks:
                state["error"] = "No document chunks found for proposal generation"
                return state
                
            # Filter chunks containing proposal keywords
            proposal_keywords = [
                "scope", "deliverable", "requirement", "objective", "task", "work", "technical", "annex", 
                "timeline", "schedule", "cost", "price", "specification", "qualification",
                "نطاق", "تسليم", "مخرجات", "متطلبات", "هدف", "أعمال", "فني", "مرفق", "جدول", "زمني", 
                "تكلفة", "سعر", "ملخص", "شروط", "مواصفات"
            ]
            
            selected_chunks = []
            char_count = 0
            
            # Eagerly grab first 4 pages as they contain the overview, organization, and index
            for content, page in chunks:
                if page <= 4:
                    selected_chunks.append(f"[Page {page}]: {content}")
                    char_count += len(content)
                    
            # Search for keyword-matching chunks on other pages
            for content, page in chunks:
                if page > 4:
                    has_kw = any(kw in content.lower() for kw in proposal_keywords)
                    if has_kw and char_count < 18000:
                        selected_chunks.append(f"[Page {page}]: {content}")
                        char_count += len(content)
                        
            # Grab last 2 pages if there is budget (often contains summary, annexes, cost terms)
            last_page = chunks[-1][1] if chunks else 0
            for content, page in chunks:
                if page >= last_page - 2 and page > 4:
                    if f"[Page {page}]: {content}" not in selected_chunks and char_count < 18000:
                        selected_chunks.append(f"[Page {page}]: {content}")
                        char_count += len(content)
                        
            state["text_context"] = "\n\n".join(selected_chunks)
            return state
        except Exception as e:
            logger.error(f"Error retrieving proposal context: {str(e)}")
            state["error"] = f"Retrieve context failed: {str(e)}"
            return state


async def generate_proposal_draft_node(state: ProposalState) -> ProposalState:
    """Calls the LLM to draft a structured business proposal in JSON based on retrieved context."""
    if state.get("error"):
        return state
        
    logger.info(f"Generating proposal draft for document {state['document_id']}")
    context = state["text_context"] or ""
    
    system_prompt = (
        "You are an expert proposal writer and procurement consultant. "
        "Your task is to write a highly professional, comprehensive, and tailored business proposal response "
        "based on the tender/procurement document context provided. "
        "Write the draft in the primary language of the tender context (Arabic if the context is predominantly in Arabic, "
        "otherwise English). Return your response strictly in JSON format."
    )
    
    prompt = (
        "Analyze the following tender/procurement document content and write a detailed proposal draft.\n"
        "Please generate a complete response containing the following four sections:\n"
        "1. Executive Summary: A professional introduction summarizing our understanding of the organization's needs and how our solution aligns.\n"
        "2. Scope Understanding: A detailed breakdown demonstrating absolute clarity on the scope of work, technical requirements, and objectives.\n"
        "3. Compliance Section: A summary outlining how we comply with all terms, required certifications, submission timelines, and conditions.\n"
        "4. Required Deliverables: A comprehensive list of the expected deliverables, outputs, milestones, and project timelines mentioned in the tender.\n\n"
        "CONTEXT:\n"
        f"{context}\n\n"
        "Respond ONLY with a JSON object of this structure:\n"
        "{\n"
        "  \"executive_summary\": \"string (paragraphs/markdown format)\",\n"
        "  \"scope_understanding\": \"string (paragraphs/markdown format)\",\n"
        "  \"compliance_section\": \"string (paragraphs/markdown format)\",\n"
        "  \"required_deliverables\": \"string (paragraphs/markdown format)\"\n"
        "}"
    )
    
    try:
        res = await call_llm_json(prompt, system_prompt, "proposal_drafting")
        state["proposal_data"] = res
        return state
    except Exception as e:
        logger.error(f"LLM proposal generation failed: {str(e)}")
        state["error"] = f"LLM Generation failed: {str(e)}"
        return state


async def store_proposal_draft_node(state: ProposalState) -> ProposalState:
    """Stores the generated proposal draft in the database."""
    doc_id = uuid.UUID(state["document_id"])
    
    async with async_session() as db:
        try:
            if state.get("error"):
                return state
                
            proposal_data = state["proposal_data"] or {}
            
            # Delete any existing proposal draft for this document
            existing = await db.execute(
                select(ProposalDraft).where(ProposalDraft.document_id == doc_id)
            )
            for old_prop in existing.scalars().all():
                await db.delete(old_prop)
                
            db_proposal = ProposalDraft(
                document_id=doc_id,
                executive_summary=proposal_data.get("executive_summary", ""),
                scope_understanding=proposal_data.get("scope_understanding", ""),
                compliance_section=proposal_data.get("compliance_section", ""),
                required_deliverables=proposal_data.get("required_deliverables", "")
            )
            db.add(db_proposal)
            await db.commit()
            return state
        except Exception as e:
            logger.error(f"Failed to save proposal draft: {str(e)}")
            await db.rollback()
            state["error"] = f"DB Save failed: {str(e)}"
            return state


# --- Build LangGraph workflow ---

workflow = StateGraph(ProposalState)

workflow.add_node("retrieve", retrieve_proposal_context_node)
workflow.add_node("generate", generate_proposal_draft_node)
workflow.add_node("store", store_proposal_draft_node)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", "store")
workflow.add_edge("store", END)

proposal_graph = workflow.compile()


# --- Runner ---

async def generate_proposal_draft(document_id: str) -> dict:
    """Runs the proposal draft generation workflow and returns results or raises exception."""
    state: ProposalState = {
        "document_id": document_id,
        "text_context": None,
        "proposal_data": None,
        "error": None
    }
    
    result_state = await proposal_graph.ainvoke(state)
    if result_state.get("error"):
        raise Exception(result_state["error"])
        
    return result_state["proposal_data"]
