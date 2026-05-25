# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=WARNING

# Install uv for dependency management
RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY src/ ./src/

# ---- dev target ----
FROM base AS dev
ENV LOG_LEVEL=DEBUG
RUN uv pip install --system -e ".[dev]"
CMD ["task-cli", "--help"]

# ---- prod target ----
FROM base AS prod
RUN uv pip install --system -e .
CMD ["task-cli", "--help"]
