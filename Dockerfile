# =========================================================================
# Production Dockerfile
# =========================================================================

FROM python:3.12-slim as builder

# Setup Environment Variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies using requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root system group and user
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser

# Copy application code into container
COPY . /app

# Secure filesystem ownership
RUN chown -R appuser:appgroup /app

# Switch to standard, unprivileged user
USER appuser

# Expose Uvicorn Port (Default to 8000 but allow override)
EXPOSE 8000

# Server execution utilizing UVLoop and HTTPTools for performance
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
