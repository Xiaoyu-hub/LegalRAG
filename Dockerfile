# LegalRAG 镜像：一个容器同时提供 API 与前端静态站点
#
# 四个阶段：
#   base   —— 系统依赖 + Python 依赖（requirements 变了才重建这一层）
#   web    —— Node 构建前端，产物只有几十 KB，node 不进最终镜像
#   backend—— 只放后端代码，便于单独跑 API
#   app    —— 生产镜像：backend + web/dist，由 FastAPI 直接托管静态文件
#
# 为什么不给前端再起一个 nginx：静态站点就三个文件，多一个容器只是多一个
# 会挂的地方；同源部署还顺手省掉 CORS。
#
# 国内直连 docker.io / pypi 常常超时，所以基础镜像与包源都可覆盖：
#   docker build --target app \
#     --build-arg PY_BASE=docker.m.daocloud.io/library/python:3.11-slim \
#     --build-arg NODE_BASE=docker.m.daocloud.io/library/node:20-slim \
#     --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
#     --build-arg NPM_REGISTRY=https://registry.npmmirror.com .

ARG PY_BASE=python:3.11-slim
ARG NODE_BASE=node:20-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG NPM_REGISTRY=https://registry.npmjs.org

FROM ${PY_BASE} AS base

# 舞台内重新声明一次才能拿到全局 ARG 的值（Docker 的硬规则）
ARG PIP_INDEX_URL

WORKDIR /app

# sentence-transformers / faiss 需要编译期头文件；装完就删，别留在层里
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt

# ── 前端构建 ──
FROM ${NODE_BASE} AS web

ARG NPM_REGISTRY

WORKDIR /web
# 先只拷依赖清单：源码改动不会让 npm ci 这一层失效
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund --registry "$NPM_REGISTRY"
COPY web/ ./
RUN npm run build

# ── 后端 ──
FROM base AS backend
COPY backend/ ./backend/
COPY configs/ ./configs/
RUN mkdir -p data/documents data/index
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── 生产镜像 ──
FROM backend AS app
COPY --from=web /web/dist ./web/dist
