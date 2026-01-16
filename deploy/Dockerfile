# Dockerfile for OCR Pipeline Cloud Function
# Python 3.11 runtime for Cloud Functions 2nd Gen

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy source code
COPY src/ ./src/
COPY config/ ./config/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Entry point for Cloud Functions
ENV FUNCTION_TARGET=process_document

# Run the function framework
CMD ["functions-framework", "--target=process_document", "--port=8080"]
