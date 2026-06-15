"""Track B6: minimal SQLite store for jobs/results (MVP). Postgres later."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import config
from .schemas import JobStatus, VideoAnalysis, VideoJob


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS videos (
                   video_id    TEXT PRIMARY KEY,
                   filename    TEXT,
                   status      TEXT NOT NULL,
                   message     TEXT,
                   result_json TEXT,
                   created_at  TEXT
               )"""
        )


def create(video_id: str, filename: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?)",
            (video_id, filename, JobStatus.queued.value, None, None,
             datetime.now(timezone.utc).isoformat()),
        )


def set_status(video_id: str, status: JobStatus, message: str | None = None) -> None:
    with _conn() as c:
        c.execute("UPDATE videos SET status=?, message=? WHERE video_id=?",
                  (status.value, message, video_id))


def set_result(video_id: str, analysis: VideoAnalysis) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE videos SET status=?, message=NULL, result_json=? WHERE video_id=?",
            (JobStatus.done.value, analysis.model_dump_json(), video_id),
        )


def get(video_id: str) -> VideoJob | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
    if row is None:
        return None
    result = (VideoAnalysis.model_validate_json(row["result_json"])
              if row["result_json"] else None)
    return VideoJob(video_id=row["video_id"], status=JobStatus(row["status"]),
                    message=row["message"], result=result)


def list_results() -> list[VideoAnalysis]:
    with _conn() as c:
        rows = c.execute(
            "SELECT result_json FROM videos WHERE result_json IS NOT NULL"
        ).fetchall()
    return [VideoAnalysis.model_validate_json(r["result_json"]) for r in rows]
