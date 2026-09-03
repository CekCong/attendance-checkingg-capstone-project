FROM python:3.11-slim

WORKDIR /app

ENV INSIGHTFACE_HOME=/app/.insightface
ENV CORS_ALLOWED_ORIGINS=http://localhost:3000

# Install system dependencies for OpenCV and InsightFace
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopencv-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the ArcFace model during the image build so the service does not
# depend on network access when handling its first request.
RUN python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', root='/app/.insightface', providers=['CPUExecutionProvider'])"

# Copy application code
COPY . .

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
