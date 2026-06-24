import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Project
from app.models.chat import ChatSession, Message
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatSessionResponse, MessageResponse, SourceInfo
from app.services.chat import handle_chat_sse

router = APIRouter(prefix="/api/projects/{project_id}/chats", tags=["chats"])


async def verify_project_access(project_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Project:
    """Verifies project exists and belongs to the user."""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied"
        )
    return project


@router.post("/stream")
async def chat_stream(
    project_id: uuid.UUID,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Streams RAG chat session response via SSE."""
    # Verify access to the project
    await verify_project_access(project_id, current_user.id, db)
    
    # Verify that requested documents belong to the project
    if body.document_ids:
        for doc_id in body.document_ids:
            # Check document is in the project
            # (In a larger scale, we could batch check this)
            from app.models.document import Document
            doc_res = await db.execute(
                select(Document).where(Document.id == doc_id, Document.project_id == project_id)
            )
            if not doc_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Document {doc_id} does not belong to this project"
                )
                
    # Return StreamingResponse with SSE content type
    return StreamingResponse(
        handle_chat_sse(
            project_id=project_id,
            query_text=body.message,
            session_id=body.session_id,
            document_ids=body.document_ids
        ),
        media_type="text/event-stream"
    )


@router.get("", response_model=list[ChatSessionResponse])
async def list_chat_sessions(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists all chat sessions in a project."""
    await verify_project_access(project_id, current_user.id, db)
    
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.project_id == project_id)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = list(result.scalars().all())
    return sessions


@router.get("/{session_id}", response_model=list[MessageResponse])
async def get_chat_messages(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gets all messages for a specific chat session."""
    await verify_project_access(project_id, current_user.id, db)
    
    # Verify session belongs to project
    session_res = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.project_id == project_id)
    )
    session = session_res.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found in this project"
        )
        
    # Load messages
    msg_res = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    messages = list(msg_res.scalars().all())
    
    # Transform to match schema exactly
    response_messages = []
    for msg in messages:
        sources_list = None
        if msg.sources and isinstance(msg.sources, dict):
            raw_sources = msg.sources.get("sources")
            if isinstance(raw_sources, list):
                sources_list = []
                for s in raw_sources:
                    sources_list.append(
                        SourceInfo(
                            page=s.get("page"),
                            snippet=s.get("snippet"),
                            chunk_id=uuid.UUID(s["chunk_id"]) if s.get("chunk_id") else None
                        )
                    )
                    
        response_messages.append(
            MessageResponse(
                id=msg.id,
                role=msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                content=msg.content,
                sources=sources_list,
                created_at=msg.created_at
            )
        )
        
    return response_messages


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deletes a chat session."""
    await verify_project_access(project_id, current_user.id, db)
    
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.project_id == project_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
        
    await db.delete(session)
    await db.commit()
