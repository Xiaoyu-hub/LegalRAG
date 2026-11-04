# 基础阶段：先装系统依赖
FROM python:3.11-slim as base

WORKDIR /app

# 装 sentence-transformers 需要的系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 先拷 requirements，利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 后端阶段
FROM base as backend
COPY backend/ ./backend/
COPY configs/ ./configs/
RUN mkdir -p data/documents data/index
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# 前端阶段
FROM base as frontend
COPY app/ ./app/
COPY backend/ ./backend/
COPY configs/ ./configs/
EXPOSE 8501
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
