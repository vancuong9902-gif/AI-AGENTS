from __future__ import annotations

"""Lightweight external-source fetchers.

This module is intentionally small and dependency-free.

Goal:
- When a topic is marked "Ít dữ liệu" or too short to be quiz-ready, we may enrich it
  with *short* public snippets and attach explicit sources.

Currently supported:
- Wikipedia (REST summary endpoint), via https://{lang}.wikipedia.org/api/rest_v1/page/summary/<title>
"""

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


def _http_get_json(url: str, *, timeout_sec: int = 6, headers: Optional[dict[str, str]] = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "ai-learning-agent/1.0"})
    with urllib.request.urlopen(req, timeout=float(timeout_sec)) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def wiki_summary(
    title_or_query: str,
    *,
    lang: str = "vi",
    timeout_sec: int = 6,
) -> Optional[Dict[str, str]]:
    """Fetch a Wikipedia summary for a given page title.

    Returns:
      {"title": ..., "url": ..., "extract": ..., "source": "wikipedia"}
    """
    q = (title_or_query or "").strip()
    if not q:
        return None
    safe = urllib.parse.quote(q.replace(" ", "_"), safe="")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{safe}"
    try:
        obj = _http_get_json(url, timeout_sec=timeout_sec)
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None
    extract = str(obj.get("extract") or "").strip()
    title = str(obj.get("title") or q).strip()
    page_url = ""
    content_urls = obj.get("content_urls")
    if isinstance(content_urls, dict):
        desktop = content_urls.get("desktop") if isinstance(content_urls.get("desktop"), dict) else None
        if isinstance(desktop, dict):
            page_url = str(desktop.get("page") or "").strip()

    # Keep it short and safe for UI.
    if not extract or len(extract) < 80:
        return None
    if len(extract) > 900:
        extract = extract[:897].rstrip() + "…"

    return {
        "title": title[:120],
        "url": page_url,
        "extract": extract,
        "source": "wikipedia",
    }


def fetch_external_snippets(
    query: str,
    *,
    lang: str = "vi",
    max_sources: int = 2,
    timeout_sec: int = 6,
) -> List[Dict[str, str]]:
    """Fetch a small set of external snippets for a query.

    Current strategy:
    - Try Wikipedia in preferred language.
    - If empty and lang != 'en', try English Wikipedia.
    """
    out: List[Dict[str, str]] = []
    q = (query or "").strip()
    if not q:
        return out

    # 1) Preferred language
    s1 = wiki_summary(q, lang=lang, timeout_sec=timeout_sec)
    if s1:
        out.append(s1)

    # 2) Fallback to English
    if len(out) < int(max_sources) and (lang or "").lower() != "en":
        s2 = wiki_summary(q, lang="en", timeout_sec=timeout_sec)
        if s2:
            # Avoid duplicates
            key = (s2.get("title") or "").strip().lower()
            if key and all((x.get("title") or "").strip().lower() != key for x in out):
                out.append(s2)

    return out[: max(0, int(max_sources))]
