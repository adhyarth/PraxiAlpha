# ==========================================
# PraxiAlpha — Backend Dockerfile
# ==========================================
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy everything (needed for pip install -e .)
COPY . .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -e ".[dev]"

# Expose port
EXPOSE 8000

# Default command: run FastAPI with uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
