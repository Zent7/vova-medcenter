FROM python:3.11-slim-bookworm

ARG BUILD_REVISION=unknown

LABEL org.opencontainers.image.source="https://github.com/Zent7/vova-medcenter" \
      org.opencontainers.image.revision="${BUILD_REVISION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BUILD_REVISION="${BUILD_REVISION}"

RUN apt-get update \
    && apt-get install --no-install-recommends -y unixodbc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY assets /app/assets

WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=45s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).read()"

CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]

