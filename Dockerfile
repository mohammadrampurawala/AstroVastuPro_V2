# Dockerfile — production-ready for Render (correct ordering & permissions)
FROM python:3.11-slim

# Use a stable WORKDIR early so COPY lands where we expect
WORKDIR /app

# Install minimal system packages required for building some wheels (kept small)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev libffi-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and create app directories before switching user
RUN useradd --create-home --home-dir /home/appuser --shell /bin/bash appuser

# Copy only requirements first (cache layer)
COPY requirements.txt /app/requirements.txt

# Install python deps as root (so .local for appuser still works later)
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the project into /app
COPY . /app

# Ensure reports dir exists and set ownership so appuser can write
RUN mkdir -p /app/reports \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser
ENV PATH="/home/appuser/.local/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

# Default command uses Render's $PORT (fallback 8000)
CMD ["sh", "-c", "uvicorn app.astro_service_with_dasha:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
