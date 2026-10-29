# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

ENV INSIGHTFACE_HOME=/app/.insightface
ENV MEDIAPIPE_MODEL_DIR=/app/models/mediapipe
ENV CORS_ALLOWED_ORIGINS=http://localhost:3000

# Install system dependencies for OpenCV and InsightFace
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir --require-hashes -r requirements.txt

# Download the ArcFace model during the image build so the service does not
# depend on network access when handling its first request.
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export REQUESTS_CA_BUNDLE=/run/secrets/proxy_ca SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', root='/app/.insightface', providers=['CPUExecutionProvider'])"

# Copy application code
COPY . .

RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    python -m app.prepare_models

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
