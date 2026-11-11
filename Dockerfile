# --- stage 1: build the single-page app -----------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
# vite writes to ../src/watchstreet/web/static/app
RUN mkdir -p /build/src/watchstreet/web/static && npm run build

# --- stage 2: the application ------------------------------------------------------
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WATCHSTREET_DATABASE_URL=sqlite:////data/watchstreet.db \
    WATCHSTREET_DOCS_DIR=/app/docs

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY --from=frontend /build/src/watchstreet/web/static/app ./src/watchstreet/web/static/app
RUN pip install .
COPY docs ./docs

RUN useradd --create-home --uid 10001 watchstreet && mkdir -p /data && chown watchstreet /data
USER watchstreet
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["uvicorn", "watchstreet.web.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
