# ============================================================
# AstroVastuPro — Production Dockerfile (Render deployment)
# ============================================================

# Use slim Python image for smaller footprint
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# ------------------------------------------------------------
# System dependencies (for pip builds and common packages)
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    libffi-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Create a non-root user for better security
# ------------------------------------------------------------
RUN useradd --create-home --home-dir /home/appuser --shell /bin/bash appuser

# ------------------------------------------------------------
# Copy requirements first to leverage Docker layer caching
# ------------------------------------------------------------
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

# ------------------------------------------------------------
# Copy project files into image
# ------------------------------------------------------------
COPY . /app

# Ensure reports directory exists and is writable
RUN mkdir -p /app/reports \
    && chown -R appuser:appuser /app

# ------------------------------------------------------------
# Environment variables
# ------------------------------------------------------------
# Add /app to PYTHONPATH so 'import app' always works
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Add local bin to PATH for non-root user installs
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Disable Python output buffering (for immediate logs)
ENV PYTHONUNBUFFERED=1

# ------------------------------------------------------------
# Switch to non-root user
# ------------------------------------------------------------
USER appuser

# ------------------------------------------------------------
# Default start command for Render
# ------------------------------------------------------------
# Render automatically provides $PORT
CMD ["sh", "-c", "uvicorn app.astro_service_with_dasha:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
