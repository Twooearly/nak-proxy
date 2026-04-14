# Multi-stage build fuer kleinen Container
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

WORKDIR /app

# Build deps are pure Python; force MarkupSafe without C extension
# so copied site packages stay architecture-neutral.
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MARKUPSAFE_NO_SPEEDUPS=1

COPY pyproject.toml README.md main.py ./

# Install Python dependencies
RUN pip install --user .

# Final stage
FROM python:3.11-slim AS runtime

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
