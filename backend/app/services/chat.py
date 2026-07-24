import uuid
import logging
import httpx
import asyncio
import json
from typing import TypedDict, Optional, Any
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.document import Document, DocumentStatus
from app.models.chat import ChatSession, Message, MessageRole
from app.services.ingestion import call_hf_embeddings
from app.services.llm import call_llm_json, stream_llm_generation

logger = logging.getLogger(__name__)

# --- QA State Schema ---
class QAState(TypedDict):
    project_id: str
    query: str
    document_ids: Optional[list[str]]
    session_id: Optional[str]
    
    # Processed data
    retrieved_chunks: Optional[list[dict]]
    generated_answer: Optional[str]
    is_grounded: Optional[bool]
    explanation: Optional[str]
    sources: Optional[list[dict]]


# --- Hybrid Search and RRF ---

def reciprocal_rank_fusion(vector_results: list[dict], bm25_results: list[dict], k: int = 60, top_n: int = 5) -> list[dict]:
    """Combines vector search and BM25 search results using Reciprocal Rank Fusion."""
    scores = {}
    chunk_map = {}
    
    for rank, chunk in enumerate(vector_results):
        cid = chunk["id"]
        chunk_map[cid] = chunk
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + (rank + 1))
        
    for rank, chunk in enumerate(bm25_results):
        cid = chunk["id"]
        chunk_map[cid] = chunk
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + (rank + 1))
        
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return [chunk_map[cid] for cid in sorted_ids[:top_n]]


async def hybrid_search(
    db: AsyncSession,
    project_id: uuid.UUID,
    query_text: str,
    document_ids: Optional[list[uuid.UUID]] = None,
    top_n: int = 5
) -> list[dict]:
    """Runs vector search + BM25 search and merges via RRF."""
    # 1. Fetch valid ready documents in project
    doc_query = select(Document.id).where(
        Document.project_id == project_id,
        Document.status == DocumentStatus.ready
    )
    if document_ids:
        doc_query = doc_query.where(Document.id.in_(document_ids))
        
    result_docs = await db.execute(doc_query)
    valid_doc_ids = [r[0] for r in result_docs.all()]
    
    if not valid_doc_ids:
        logger.warning(f"No ready documents found for search in project {project_id}")
        return []
        
    # 2. Get query embedding
    try:
        embeddings = await call_hf_embeddings([query_text])
        query_embedding = embeddings[0]
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {str(e)}")
        query_embedding = None
        
    # 3. Vector search (Cosine distance)
    vector_results = []
    if query_embedding:
        try:
            query_embedding_str = f"[{','.join(map(str, query_embedding))}]"
            vector_sql = text("""
                SELECT id, document_id, chunk_index, content, page_number, start_char, end_char,
                       (1 - (embedding <=> CAST(:query_embedding AS vector))) AS score
                FROM chunks
                WHERE document_id = ANY(:doc_ids)
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT 10
            """)
            res = await db.execute(vector_sql, {
                "query_embedding": query_embedding_str,
                "doc_ids": valid_doc_ids
            })
            vector_results = [dict(r._mapping) for r in res.all()]
        except Exception as e:
            logger.error(f"Vector search failed: {str(e)}")
            await db.rollback()
            
    # 4. BM25 search
    bm25_results = []
    if query_text.strip():
        try:
            bm25_sql = text("""
                SELECT id, document_id, chunk_index, content, page_number, start_char, end_char,
                       ts_rank_cd(tsv, plainto_tsquery('simple', :query_text)) AS score
                FROM chunks
                WHERE document_id = ANY(:doc_ids) AND tsv @@ plainto_tsquery('simple', :query_text)
                ORDER BY score DESC
                LIMIT 10
            """)
            res = await db.execute(bm25_sql, {
                "query_text": query_text,
                "doc_ids": valid_doc_ids
            })
            bm25_results = [dict(r._mapping) for r in res.all()]
        except Exception as e:
            logger.warning(f"BM25 search failed (likely query syntax or no matches): {str(e)}")
            await db.rollback()
            
    # 5. Merge via RRF
    merged = reciprocal_rank_fusion(vector_results, bm25_results, top_n=top_n)
    return merged


# --- QA Operations ---

async def verify_grounding(context: str, answer: str) -> tuple[bool, str]:
    """Verifies that the generated answer is fully grounded in the retrieved context."""
    system_prompt = "You are an expert fact-checker that verifies if answers are grounded in the context. Return JSON format."
    prompt = (
        "Check if the ANSWER is fully grounded and supported by the CONTEXT. "
        "Any claim in the ANSWER must have direct evidence in the CONTEXT. If context is missing, return is_grounded as false.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"ANSWER:\n{answer}\n\n"
        "Respond ONLY with a JSON object:\n"
        "{\n"
        "  \"is_grounded\": true | false,\n"
        "  \"explanation\": \"Brief explanation of grounding check.\"\n"
        "}"
    )
    
    try:
        res = await call_llm_json(prompt, system_prompt, "grounding_check")
        is_grounded = res.get("is_grounded")
        if is_grounded is None:
            is_grounded = True
        return bool(is_grounded), str(res.get("explanation", "Verified."))
    except Exception as e:
        logger.error(f"Grounding check failed: {str(e)}")
        # Default to True on API error to avoid blocking the user, but log explanation
        return True, f"Grounding check error bypassed: {str(e)}"


# --- SSE Streaming Manager ---

def is_conversational(query: str) -> bool:
    q = query.strip().lower().rstrip("!?.")
    # Common English greetings, thanks, closings, acknowledgements
    english_casual = {
        "hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "thank you very much", "many thanks", "thanks a lot",
        "ok", "okay", "got it", "noted", "great", "awesome", "perfect", "cool",
        "bye", "goodbye", "see you", "thank", "thanks!"
    }
    
    # Common Arabic greetings, thanks, closings, acknowledgements
    arabic_casual = {
        "مرحبا", "مرحباً", "اهلا", "أهلاً", "السلام عليكم", "صباح الخير", "مساء الخير",
        "شكرا", "شكراً", "شكرا لك", "تسلم", "تسلم ايدك", "يعطيك العافية", "يعطيكم العافية",
        "تمام", "ماشي", "حسنا", "حسناً", "جيد", "ممتاز", "مع السلامة", "شكر"
    }
    
    if q in english_casual or q in arabic_casual:
        return True
        
    # Check if it starts with standard thank/greeting words and is very short
    words = q.split()
    if len(words) <= 3:
        first_word = words[0]
        if first_word in {"hi", "hello", "hey", "thanks", "thank", "ok", "okay", "اهلا", "شكرا", "مرحبا", "تسلم"}:
            return True
            
    return False


async def handle_chat_sse(
    project_id: uuid.UUID,
    query_text: str,
    session_id: Optional[uuid.UUID] = None,
    document_ids: Optional[list[uuid.UUID]] = None,
):
    """
    Manages the entire Hybrid RAG + Streaming QA + Grounding flow.
    Yields SSE events: 'sources', 'token', and finally 'result' or 'error'.
    """
    start_time = asyncio.get_event_loop().time()
    
    async with async_session() as db:
        # 1. Resolve or create chat session
        if not session_id:
            chat_session = ChatSession(project_id=project_id, title=query_text[:50])
            db.add(chat_session)
            await db.commit()
            await db.refresh(chat_session)
            session_id = chat_session.id
        else:
            result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
            chat_session = result.scalar_one_or_none()
            if not chat_session:
                yield f"event: error\ndata: {json.dumps({'message': 'Chat session not found'})}\n\n"
                return
                
        # 2. Save User Message
        user_message = Message(
            session_id=session_id,
            role=MessageRole.user,
            content=query_text
        )
        db.add(user_message)
        await db.commit()
        
        # Check if query is conversational/greeting/acknowledgement
        is_casual = is_conversational(query_text)
        
        # 3. Retrieve chunks via hybrid search (only if not casual greeting)
        if not is_casual:
            chunks = await hybrid_search(db, project_id, query_text, document_ids)
        else:
            chunks = []
            
        sources_list = []
        context_parts = []
        
        for idx, c in enumerate(chunks):
            sources_list.append({
                "chunk_id": str(c["id"]),
                "page": c["page_number"],
                "snippet": c["content"][:200] + "..." if len(c["content"]) > 200 else c["content"]
            })
            context_parts.append(f"[Source {idx+1}, Page {c['page_number']}]: {c['content']}")
            
        # Yield sources immediately to client
        yield f"event: sources\ndata: {json.dumps(sources_list)}\n\n"
        
        # 4. Stream response generation
        context_str = "\n\n".join(context_parts)
        if is_casual:
            system_prompt = (
                "You are an AI document intelligence assistant powered by Agentic RAG.\n"
                "The user is sending a general greeting, thank you, or conversational statement.\n"
                "Respond to them politely, naturally, and conversationally in their language (Arabic or English). Keep it brief."
            )
            prompt = f"USER MESSAGE:\n{query_text}"
        else:
            system_prompt = (
                "You are an AI document intelligence assistant powered by Agentic RAG.\n"
                "Answer the user's question using ONLY the provided context. If the answer cannot be found in the context, "
                "politely state that the information is not present in the document. Do not make up facts.\n"
                "Respond in the language of the query (Arabic or English)."
            )
            prompt = f"CONTEXT:\n{context_str}\n\nQUESTION:\n{query_text}"
        
        generated_answer = ""
        try:
            async for token in stream_llm_generation(prompt, system_prompt, "chat_generation"):
                generated_answer += token
                yield f"event: token\ndata: {json.dumps(token)}\n\n"
        except Exception as e:
            logger.error(f"Error during streaming generation: {str(e)}")
            yield f"event: error\ndata: {json.dumps({'message': f'Generation Error: {str(e)}'})}\n\n"
            return
            
        # 5. Grounding check
        if is_casual:
            is_grounded = True
            explanation = "Conversational message bypassed grounding check."
        else:
            is_grounded, explanation = await verify_grounding(context_str, generated_answer)
            
        final_answer = generated_answer
        
        # If not grounded, overwrite with polite fallback
        if not is_grounded:
            final_answer = "نعتذر، لم يتم العثور على أدلة كافية في المستندات للإجابة على هذا السؤال." if any(ord(c) > 127 for c in query_text) else "Sorry, not enough evidence was found in the documents to answer this question."
            # Yield token events for the fallback message so the frontend updates nicely
            yield f"event: token\ndata: {json.dumps('[CLEAR]')}\n\n"
            yield f"event: token\ndata: {json.dumps(final_answer)}\n\n"
            
        latency_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        
        # 6. Save assistant message with sources, tokens, latency
        assistant_message = Message(
            session_id=session_id,
            role=MessageRole.assistant,
            content=final_answer,
            sources={"sources": sources_list, "grounded": is_grounded, "explanation": explanation},
            latency_ms=latency_ms
        )
        db.add(assistant_message)
        await db.commit()
        
        # Yield final result
        yield f"event: result\ndata: {json.dumps({'session_id': str(session_id), 'message_id': str(assistant_message.id), 'is_grounded': is_grounded, 'final_response': final_answer})}\n\n"
