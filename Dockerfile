FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the application.
RUN groupadd -r softstudio && useradd -r -g softstudio -d /app softstudio

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=softstudio:softstudio . .

RUN mkdir -p /app/app/static/images/uploads /data/protected \
    && chown -R softstudio:softstudio /app /data

USER softstudio

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/robots.txt || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "wsgi:app"]
