FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WATCHSTREET_DATABASE_URL=sqlite:////data/watchstreet.db \
    WATCHSTREET_DOCS_DIR=/app/docs

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .
COPY docs ./docs

RUN useradd --create-home --uid 10001 watchstreet && mkdir -p /data && chown watchstreet /data
USER watchstreet
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["uvicorn", "watchstreet.web.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
