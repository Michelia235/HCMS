"""Shared Gemini client + retry, used by vlm.py (detection) and chat.py (copilot).

Centralises the cached client and the backoff policy so both call sites get the
same handling for 429 (RPM) and transient 5xx. The `google` SDK is imported
lazily so the module loads even when the dependency is absent.
"""
from __future__ import annotations

import re
import time
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def client():
    from google import genai  # type: ignore

    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing (set it in copilot/.env)")
    return genai.Client(api_key=config.GEMINI_API_KEY)


def generate(contents, *, json_mode: bool = False, retries: int = 4):
    """generate_content with backoff for 429 (RPM) and transient 5xx/UNAVAILABLE.

    429 RESOURCE_EXHAUSTED honours the server-suggested retry delay; transient
    ServerError (503 UNAVAILABLE / 500 INTERNAL) uses exponential backoff.
    Neither helps the daily free-tier cap. `json_mode` forces strict JSON output.
    """
    from google.genai import types  # type: ignore
    from google.genai.errors import ClientError, ServerError  # type: ignore

    cfg = (types.GenerateContentConfig(response_mime_type="application/json", temperature=0)
           if json_mode else None)
    for attempt in range(retries + 1):
        try:
            return client().models.generate_content(
                model=config.GEMINI_MODEL, contents=contents, config=cfg)
        except ClientError as e:
            if "RESOURCE_EXHAUSTED" in str(e) and attempt < retries:
                m = re.search(r"retry in ([\d.]+)s", str(e))
                time.sleep(min(float(m.group(1)) if m else 20.0, 60.0))
                continue
            raise
        except ServerError:
            # 503 UNAVAILABLE / 500 INTERNAL: transient spikes -> exp backoff
            if attempt < retries:
                time.sleep(min(2.0 * (2 ** attempt), 30.0))
                continue
            raise
