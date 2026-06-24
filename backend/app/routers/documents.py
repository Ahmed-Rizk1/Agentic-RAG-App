import os
import uuid
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Project
from app.models.document import Document, DocumentStatus, DocumentMetadata
from app.models.user import User
from app.schemas.document import DocumentResponse, DocumentDetailResponse
from app.services.ingestion import run_ingestion_workflow

router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["documents"])


async def get_user_project(project_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Project:
    """Verifies project exists and belongs to user."""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you do not have permission to access it"
        )
    return project


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Verify project
    await get_user_project(project_id, current_user.id, db)
    
    # 2. Verify file is PDF
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only PDF documents are allowed."
        )
        
    # 3. Verify file size (spool file if necessary, or read headers)
    # Check if size attribute is present, otherwise fallback to reading file length
    size_bytes = getattr(file, "size", None)
    if size_bytes is None:
        content = await file.read()
        size_bytes = len(content)
        await file.seek(0)
    
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_file_size_mb}MB"
        )
        
    # 4. Create document DB record in 'uploading' state
    doc_id = uuid.uuid4()
    
    # Keep files organized in subdirectories per project
    project_dir = Path(settings.upload_dir) / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    file_path = project_dir / f"{doc_id}.pdf"
    
    document = Document(
        id=doc_id,
        project_id=project_id,
        filename=filename,
        file_path=str(file_path),
        file_size_bytes=size_bytes,
        status=DocumentStatus.uploading
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    # 5. Save file to disk
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        # Rollback DB record if file write fails
        await db.delete(document)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file to storage: {str(e)}"
        )
        
    # 6. Trigger LangGraph background ingestion
    background_tasks.add_task(
        run_ingestion_workflow, 
        str(document.id), 
        str(file_path), 
        str(project_id)
    )
    
    return document


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify project ownership
    await get_user_project(project_id, current_user.id, db)
    
    result = await db.execute(
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.desc())
    )
    documents = list(result.scalars().all())
    return documents


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document_details(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify project ownership
    await get_user_project(project_id, current_user.id, db)
    
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id, Document.project_id == project_id)
        .options(selectinload(Document.metadata_record))
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this project"
        )
        
    # Standard Pydantic mapping relies on matching names: DocumentDetailResponse.metadata matches Document.metadata_record
    # Let's dynamically attach metadata if needed, but since relationship is metadata_record, we can transform it
    # in Pydantic schema or just set standard attribute:
    document.metadata = document.metadata_record
    
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify project ownership
    await get_user_project(project_id, current_user.id, db)
    
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.project_id == project_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this project"
        )
        
    # Delete file from disk
    if os.path.exists(document.file_path):
        try:
            os.remove(document.file_path)
        except Exception as e:
            # log warning but continue deleting from DB
            pass
            
    await db.delete(document)
    await db.commit()
