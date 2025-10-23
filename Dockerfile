# Dockerfile — production-ready for Render
FROM python:3.11-slim

# set a deterministic working dir
WORKDIR /app

# system deps needed for some Python packages (geopy, weasyprint optional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev libffi-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# create non-root user
RUN useradd --create-home appuser
ENV PATH="/home/appuser/.local/bin:${PATH}"

# copy only requirements first to leverage cache
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy project
COPY . /app

# ensure packages installed as non-root user can write to .local
RUN chown -R appuser:appuser /app
USER appuser

# Use PORT environment variable provided by Render
ENV PYTHONUNBUFFERED=1

# Start command
CMD ["sh", "-c", "uvicorn app.astro_service_with_dasha:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
