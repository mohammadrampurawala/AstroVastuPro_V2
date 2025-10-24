# ============================================================
# AstroVastuPro — Dockerfile (Final Render Deployment Version)
# ============================================================

FROM python:3.11-slim

# ------------------------------------------------------------
# Set working directory inside container
# ------------------------------------------------------------
WORKDIR /app

# ------------------------------------------------------------
# System dependencies required for build and runtime
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
# Create a secure non-root user
# ------------------------------------------------------------
RUN useradd --create-home --home-dir /home/appuser --shell /bin/bash appuser

# ------------------------------------------------------------
# Copy requirements first (to leverage Docker layer cache)
# ------------------------------------------------------------
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

# ------------------------------------------------------------
# Copy entire project into image
# ------------------------------------------------------------
COPY . /app

# Ensure reports folder exists and is writable
RUN mkdir -p /app/reports \
    && chown -R appuser:appuser /app

# ------------------------------------------------------------
# Environment configuration
# ------------------------------------------------------------
# Make sure Python sees /app (so `import app` always works)
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Add local bin to PATH for appuser
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Unbuffered output for real-time logs
ENV PYTHONUNBUFFERED=1

# ------------------------------------------------------------
# Switch to non-root user
# ------------------------------------------------------------
USER appuser

# ------------------------------------------------------------
# Start the application
# ------------------------------------------------------------
# Render automatically provides $PORT
# --app-dir app ensures uvicorn loads correctly
CMD ["sh", "-c", "uvicorn astro_service_with_dasha:app --app-dir app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
