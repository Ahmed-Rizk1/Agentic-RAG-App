FROM python:3.13-slim

# Set build and runtime environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies (including git/build-essential if needed for dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependencies manifest
COPY pyproject.toml uv.lock ./

# Install python dependencies using uv (without installing the project itself yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code and config files
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Expose port
EXPOSE 8000

# Start script: run migrations and launch uvicorn on the container-configured PORT
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

