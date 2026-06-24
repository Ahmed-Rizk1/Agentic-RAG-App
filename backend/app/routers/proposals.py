import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Project
from app.models.document import Document, DocumentStatus
from app.models.llm_log import ProposalDraft
from app.models.user import User
from app.schemas.proposal import ProposalDraftResponse
from app.services.proposal import generate_proposal_draft

router = APIRouter(prefix="/api/projects/{project_id}/documents/{document_id}/proposal", tags=["proposals"])


async def verify_document_access(project_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Document:
    """Verifies project belongs to user and document belongs to project and is ready."""
    # 1. Project access
    proj_res = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    if not proj_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied"
        )
        
    # 2. Document access
    doc_res = await db.execute(
        select(Document).where(Document.id == document_id, Document.project_id == project_id)
    )
    document = doc_res.scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this project"
        )
        
    if document.status != DocumentStatus.ready:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is not ready (current status: {document.status})"
        )
        
    return document


@router.post("", response_model=ProposalDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_proposal_draft(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Triggers proposal draft generation on the specified document and returns/saves it."""
    # Verify access and document state
    await verify_document_access(project_id, document_id, current_user.id, db)
    
    try:
        # Run LangGraph proposal generation
        await generate_proposal_draft(str(document_id))
        
        # Load newly created proposal draft
        result = await db.execute(
            select(ProposalDraft).where(ProposalDraft.document_id == document_id)
        )
        proposal = result.scalar_one()
        return proposal
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate proposal draft: {str(e)}"
        )


@router.get("", response_model=ProposalDraftResponse)
async def get_proposal_draft(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gets the existing proposal draft for the document if it exists, otherwise returns 404."""
    # Verify access
    await verify_document_access(project_id, document_id, current_user.id, db)
    
    result = await db.execute(
        select(ProposalDraft).where(ProposalDraft.document_id == document_id)
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal draft has not been generated for this document yet"
        )
        
    return proposal
