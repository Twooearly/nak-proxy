# Multi-stage build für kleinen Container
FROM python:3.11-slim as builder

WORKDIR /app

# Install dependencies minimal
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir --user -e .

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Copy nur die notwendigen dependencies vom builder
COPY --from=builder /root/.local /root/.local

# Set PATH
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

COPY main.py .

EXPOSE 8000

# Gunicorn mit 4 Workers (angepasst für kleine Container)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "main:app"]
