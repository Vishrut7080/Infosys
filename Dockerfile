# Use a multi-stage build for a smaller final image
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies using uv
# We use --no-cache to keep the image slim
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime system dependencies (sqlite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Environment variables
ENV FLASK_APP=main:app
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Production: threading mode (no eventlet/gevent monkey-patching needed)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --threads 4 --workers 1 main:app"]
# CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--threads", "4", "--workers", "1", "main:app"]
# Development:
# CMD ["flask", "--app", "main:app", "run", "--host=127.0.0.1", "--port=5000", "--debug"]
