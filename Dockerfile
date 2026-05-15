# Base stage
FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies for sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend stage
FROM base as backend
COPY backend/ ./backend/
COPY configs/ ./configs/
RUN mkdir -p data/documents data/index
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Frontend stage
FROM base as frontend
RUN pip install --no-cache-dir streamlit
COPY app/ ./app/
COPY backend/ ./backend/
COPY configs/ ./configs/
EXPOSE 8501
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
