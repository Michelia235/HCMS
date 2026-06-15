# Hand Hygiene Compliance Copilot - backend (FastAPI + Gemini VLM)
# Build context = copilot/ (this dir). Image preserves the repo layout so
# config.COPILOT_ROOT (= /app) finds uploads/, copilot.sqlite, agent/.
FROM python:3.11-slim

# OpenCV (opencv-python) needs libGL + glib at runtime even for headless decode.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps first for layer caching.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App code + runtime assets (protocol/schemas for chat RAG).
COPY backend/ backend/
COPY agent/ agent/

# `app` is the top-level package (see scripts/test_pipeline.py).
ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1

# Render injects $PORT; default to 8000 for local `docker run`.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
