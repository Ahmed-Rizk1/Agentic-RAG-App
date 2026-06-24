import uuid
import logging
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.llm_log import RiskReport
from app.services.llm import call_llm_json

logger = logging.getLogger(__name__)

# --- Risk State ---
class RiskState(TypedDict):
    document_id: str
    text_context: Optional[str]
    report_data: Optional[dict]
    error: Optional[str]


# --- Nodes ---

async def retrieve_risk_context_node(state: RiskState) -> RiskState:
    """Retrieves document text chunks related to risks, terms, deadlines and certifications."""
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
                state["error"] = "No document chunks found for analysis"
                return state
                
            # Filter chunks containing risk keywords or simply take first/last few pages
            risk_keywords = [
                "penalty", "delay", "fine", "bond", "guarantee", "liability", "indemnity", "termination", 
                "qualification", "certif", "deadline", "liquidated", "governing law", "dispute",
                "غرامة", "تأخير", "جزاء", "ضمان", "كفالة", "مسؤولية", "تصنيف", "شهادة", "موعد", "فسخ", "نزاع"
            ]
            
            selected_chunks = []
            char_count = 0
            
            # Eagerly grab first 4 pages as they contain core context and metadata
            for content, page in chunks:
                if page <= 4:
                    selected_chunks.append(f"[Page {page}]: {content}")
                    char_count += len(content)
                    
            # Search for keyword-matching chunks on other pages
            for content, page in chunks:
                if page > 4:
                    # check if any keyword matches
                    has_kw = any(kw in content.lower() for kw in risk_keywords)
                    if has_kw and char_count < 15000:
                        selected_chunks.append(f"[Page {page}]: {content}")
                        char_count += len(content)
                        
            # If still short, grab last 2 pages
            last_page = chunks[-1][1] if chunks else 0
            for content, page in chunks:
                if page >= last_page - 2 and page > 4:
                    if f"[Page {page}]: {content}" not in selected_chunks and char_count < 15000:
                        selected_chunks.append(f"[Page {page}]: {content}")
                        char_count += len(content)
                        
            state["text_context"] = "\n\n".join(selected_chunks)
            return state
        except Exception as e:
            logger.error(f"Error retrieving risk context: {str(e)}")
            state["error"] = f"Retrieve context failed: {str(e)}"
            return state


async def analyze_risks_node(state: RiskState) -> RiskState:
    """Calls Groq to perform structured risk analysis on the selected context."""
    if state.get("error"):
        return state
        
    logger.info(f"Analyzing risks for document {state['document_id']}")
    context = state["text_context"] or ""
    
    system_prompt = "You are an expert procurement risk analyst. Return JSON format."
    prompt = (
        "Identify and analyze key business risks in the following document content.\n"
        "Look for risks matching these categories:\n"
        "1. Missing certifications (e.g. ISO certifications, specific classifications required)\n"
        "2. High requirements (e.g. excessive experience required, high bid bonds, strict financial terms)\n"
        "3. Legal concerns (e.g. penalties for delay, strict liability, governing law outside candidate country, strict SLAs)\n"
        "4. Tight deadlines (e.g. extremely short bid submission windows, fast delivery timelines)\n"
        "5. Missing documents (e.g. required forms, templates, or annexes mentioned but missing)\n\n"
        "Specify an overall_score ('low', 'medium', 'high') based on the severities.\n\n"
        "CONTENT:\n"
        f"{context}\n\n"
        "Respond ONLY with a JSON object of this structure:\n"
        "{\n"
        "  \"overall_score\": \"low\" | \"medium\" | \"high\",\n"
        "  \"risks\": [\n"
        "    {\n"
        "      \"category\": \"Missing certifications\" | \"High requirements\" | \"Legal concerns\" | \"Tight deadlines\" | \"Missing documents\",\n"
        "      \"severity\": \"low\" | \"medium\" | \"high\",\n"
        "      \"description\": string,\n"
        "      \"evidence\": string (direct Arabic or English quote from the text showing this risk),\n"
        "      \"page\": number | null\n"
        "    }\n"
        "  ]\n"
        "}"
    )
    
    try:
        res = await call_llm_json(prompt, system_prompt, "risk_analysis")
        state["report_data"] = res
        return state
    except Exception as e:
        logger.error(f"Groq risk analysis failed: {str(e)}")
        state["error"] = f"AI Analysis failed: {str(e)}"
        return state


async def store_risk_report_node(state: RiskState) -> RiskState:
    """Stores the generated risk report in the database."""
    doc_id = uuid.UUID(state["document_id"])
    
    async with async_session() as db:
        try:
            if state.get("error"):
                return state
                
            report_data = state["report_data"] or {}
            
            # Delete any existing risk report for this document
            existing = await db.execute(
                select(RiskReport).where(RiskReport.document_id == doc_id)
            )
            for old_rep in existing.scalars().all():
                await db.delete(old_rep)
                
            db_report = RiskReport(
                document_id=doc_id,
                overall_score=report_data.get("overall_score", "low"),
                risks=report_data.get("risks", [])
            )
            db.add(db_report)
            await db.commit()
            return state
        except Exception as e:
            logger.error(f"Failed to save risk report: {str(e)}")
            await db.rollback()
            state["error"] = f"DB Save failed: {str(e)}"
            return state


# --- Build LangGraph workflow ---

workflow = StateGraph(RiskState)

workflow.add_node("retrieve", retrieve_risk_context_node)
workflow.add_node("analyze", analyze_risks_node)
workflow.add_node("store", store_risk_report_node)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "analyze")
workflow.add_edge("analyze", "store")
workflow.add_edge("store", END)

risk_graph = workflow.compile()


# --- Runner ---

async def generate_risk_report(document_id: str) -> dict:
    """Runs the risk report generation workflow and returns results or raises exception."""
    state: RiskState = {
        "document_id": document_id,
        "text_context": None,
        "report_data": None,
        "error": None
    }
    
    result_state = await risk_graph.ainvoke(state)
    if result_state.get("error"):
        raise Exception(result_state["error"])
        
    return result_state["report_data"]
