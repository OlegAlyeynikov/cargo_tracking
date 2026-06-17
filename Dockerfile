# Stage 1: Build frontend
FROM node:20-alpine AS node-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build
# vite outDir is '../app/static/ui' → resolves to /app/static/ui inside this stage

# Stage 2: Install Python dependencies
FROM python:3.12-slim AS python-builder
WORKDIR /app
RUN pip install uv --no-cache-dir
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Stage 3: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=python-builder /app/.venv .venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# Install Playwright system deps and Chromium as root, then make world-readable
RUN playwright install-deps chromium \
    && playwright install chromium \
    && chmod -R 755 /opt/playwright

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY app/ app/
COPY data/ data/
COPY --from=node-builder /app/static/ui/ app/static/ui/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
