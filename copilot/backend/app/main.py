"""FastAPI app - Hand Hygiene Compliance Copilot backend (MVP).

Endpoints:
  GET  /health
  POST /videos          upload a video, returns video_id, processing in background
  GET  /videos/{id}     job status + result (events, findings, score)
  POST /chat            copilot Q&A over stored analyses
"""
from __future__ import annotations

import shutil
import uuid

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, pipeline
from .schemas import ChatRequest, ChatResponse, VideoJob

app = FastAPI(title="Hand Hygiene Compliance Copilot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,  # "*" for MVP; set to Vercel URL in prod
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": config.GEMINI_MODEL}


@app.post("/videos")
async def upload_video(
    background: BackgroundTasks, file: UploadFile = File(...)
) -> dict:
    if not file.filename:
        raise HTTPException(400, "missing filename")
    video_id = uuid.uuid4().hex[:12]
    dest = config.UPLOAD_DIR / f"{video_id}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    db.create(video_id, file.filename)
    background.add_task(pipeline.run_job, str(dest), video_id)
    return {"video_id": video_id, "status": "queued"}


@app.get("/videos/{video_id}", response_model=VideoJob)
def get_video(video_id: str) -> VideoJob:
    job = db.get(video_id)
    if job is None:
        raise HTTPException(404, "video_id not found")
    return job


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.question.strip():
        raise HTTPException(400, "empty question")
    from . import chat as chat_mod

    return chat_mod.answer(req.question, req.video_id)
