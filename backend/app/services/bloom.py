from __future__ import annotations

import re
from typing import Dict, List

# Bloom (simplified 6-level taxonomy)
BLOOM_LEVELS: List[str] = [
    "remember",   # nhận biết/ghi nhớ
    "understand", # hiểu
    "apply",      # vận dụng
    "analyze",    # phân tích
    "evaluate",   # so sánh/đánh giá
    "create",     # thiết kế/đề xuất giải pháp
]

# Level blueprints requested by the team
# (Beginner/Intermediate/Advanced difficulty mix)
LEVEL_BLOOM_DISTRIBUTIONS: Dict[str, Dict[str, float]] = {
    "beginner": {
        "remember": 0.60,
        "understand": 0.30,
        "apply": 0.10,
        "analyze": 0.00,
        "evaluate": 0.00,
        "create": 0.00,
    },
    "intermediate": {
        # 30% nhận biết, 50% vận dụng/phân tích, 20% so sánh/đánh giá
        # We split the 50% by default into apply 30% + analyze 20%.
        "remember": 0.30,
        "understand": 0.00,
        "apply": 0.30,
        "analyze": 0.20,
        "evaluate": 0.20,
        "create": 0.00,
    },
    "advanced": {
        # 20% phân tích, 50% vận dụng tình huống, 30% đánh giá/thiết kế giải pháp
        # We split 30% into evaluate 15% + create 15%.
        "remember": 0.00,
        "understand": 0.00,
        "apply": 0.50,
        "analyze": 0.20,
        "evaluate": 0.15,
        "create": 0.15,
    },
}


def get_level_distribution(level: str) -> Dict[str, float]:
    lv = (level or "").strip().lower()
    dist = LEVEL_BLOOM_DISTRIBUTIONS.get(lv)
    if not dist:
        # reasonable default
        dist = {"remember": 0.25, "understand": 0.25, "apply": 0.25, "analyze": 0.15, "evaluate": 0.10, "create": 0.00}
    # ensure all keys exist
    out = {k: float(dist.get(k, 0.0)) for k in BLOOM_LEVELS}
    # normalize if needed
    s = sum(out.values())
    if s <= 0:
        out = {k: (1.0 / len(BLOOM_LEVELS)) for k in BLOOM_LEVELS}
        s = 1.0
    if abs(s - 1.0) > 1e-6:
        out = {k: v / s for k, v in out.items()}
    return out


def allocate_bloom_counts(total: int, distribution: Dict[str, float]) -> Dict[str, int]:
    """Allocate integer counts that sum to total based on a distribution."""
    total = max(0, int(total))
    if total == 0:
        return {k: 0 for k in BLOOM_LEVELS}

    dist = {k: float(distribution.get(k, 0.0)) for k in BLOOM_LEVELS}
    # normalize
    s = sum(dist.values())
    if s <= 0:
        dist = {k: 1.0 / len(BLOOM_LEVELS) for k in BLOOM_LEVELS}
        s = 1.0
    dist = {k: v / s for k, v in dist.items()}

    # floor counts then distribute remainder by largest fractional parts
    raw = {k: dist[k] * total for k in BLOOM_LEVELS}
    base = {k: int(raw[k]) for k in BLOOM_LEVELS}
    rem = total - sum(base.values())

    frac = sorted(((raw[k] - base[k], k) for k in BLOOM_LEVELS), reverse=True)
    i = 0
    while rem > 0 and i < len(frac) * 3:
        _, k = frac[i % len(frac)]
        base[k] += 1
        rem -= 1
        i += 1

    # final fix
    drift = total - sum(base.values())
    if drift != 0:
        base["remember"] += drift

    return base


def normalize_bloom_level(value: str | None) -> str:
    v = (value or "").strip().lower()
    # Backward-compat mapping
    legacy = {
        "recall": "remember",
        "nhớ": "remember",
        "ghi_nhớ": "remember",
        "ghi nhớ": "remember",
        "nhận biết": "remember",
        "understand": "understand",
        "hiểu": "understand",
        "apply": "apply",
        "vận dụng": "apply",
        "analyze": "analyze",
        "phân tích": "analyze",
        "evaluate": "evaluate",
        "đánh giá": "evaluate",
        "so sánh": "evaluate",
        "create": "create",
        "thiết kế": "create",
    }
    if v in legacy:
        v = legacy[v]
    if v in BLOOM_LEVELS:
        return v
    return "understand"


_RX = {
    "create": re.compile(r"\b(thiết\s*kế|đề\s*xuất|xây\s*dựng|tạo\s*giải\s*pháp|thiết\s*kế\s*giải\s*pháp|kế\s*hoạch|kiến\s*trúc|design)\b", re.IGNORECASE),
    "evaluate": re.compile(r"\b(đánh\s*giá|nhận\s*xét|lựa\s*chọn\s*phương\s*án|tối\s*ưu|so\s*sánh|phê\s*bình|ưu\s*nhược\s*điểm|trade\-?off)\b", re.IGNORECASE),
    "analyze": re.compile(r"\b(phân\s*tích|nguyên\s*nhân|chẩn\s*đoán|phân\s*rã|lỗi\s*thường\s*gặp|tại\s*sao\s*sai|so\s*sát|analy(sis|ze))\b", re.IGNORECASE),
    "apply": re.compile(r"\b(vận\s*dụng|áp\s*dụng|tình\s*huống|triển\s*khai|thực\s*hiện|sử\s*dụng|giải\s*quyết|apply)\b", re.IGNORECASE),
    "understand": re.compile(r"\b(giải\s*thích|diễn\s*giải|phân\s*biệt|vì\s*sao|hiểu|understand)\b", re.IGNORECASE),
}


def infer_bloom_level(text: str, *, default: str = "understand") -> str:
    t = (text or "").strip()
    if not t:
        return normalize_bloom_level(default)

    # Order matters: create -> evaluate -> analyze -> apply -> understand -> remember
    for lvl in ["create", "evaluate", "analyze", "apply", "understand"]:
        if _RX[lvl].search(t):
            return lvl
    return "remember"
