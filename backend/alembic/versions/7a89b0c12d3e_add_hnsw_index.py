"""add_hnsw_index

Revision ID: 7a89b0c12d3e
Revises: 5de29207edd8
Create Date: 2026-07-24 17:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7a89b0c12d3e'
down_revision: Union[str, Sequence[str], None] = '5de29207edd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with HNSW vector index for high-performance vector search."""
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding_hnsw;")
