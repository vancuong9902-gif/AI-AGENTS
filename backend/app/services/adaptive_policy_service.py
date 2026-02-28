from __future__ import annotations

import math
import random
import datetime as _dt
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.attempt import Attempt
from app.models.learner_profile import LearnerProfile
from app.services.user_service import ensure_user_exists


Action = Literal[
    "increase_difficulty",
    "decrease_difficulty",
    "switch_topic",
    "reinforce_weak_skill",
    "continue",
]

Difficulty = Literal["easy", "medium", "hard"]
PolicyType = Literal["contextual_bandit", "q_learning"]


# -------------------------
# State representation
# -------------------------


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _difficulty_to_int(d: Optional[str]) -> int:
    if (d or "").lower() == "hard":
        return 2
    if (d or "").lower() == "medium":
        return 1
    return 0


def _int_to_difficulty(i: int) -> Difficulty:
    if int(i) >= 2:
        return "hard"
    if int(i) == 1:
        return "medium"
    return "easy"


def build_state(
    *,
    profile: LearnerProfile,
    topic: Optional[str],
    recent_accuracy: Optional[float],
    avg_time_per_item_sec: Optional[float],
    engagement: Optional[float],
    current_difficulty: Optional[str],
) -> Dict[str, Any]:
    """Build a compact learner state used by the adaptive policy.

    We mix:
      - continuous telemetry (accuracy/time/engagement)
      - coarse bins for stability
      - mastery priors from LearnerProfile.mastery_json

    The bins avoid oscillation and allow tabular Q-learning in early deployments.
    """

    mastery_json = profile.mastery_json or {}
    topic_key = (topic or "__global__").strip() or "__global__"
    mastery_topic = mastery_json.get("topic_mastery", {}).get(topic_key)
    mastery = _safe_float(mastery_topic, default=_safe_float(mastery_json.get("mastery", 0.0), 0.0))

    acc = _clip(_safe_float(recent_accuracy, default=0.0), 0.0, 1.0)
    tpi = max(0.0, _safe_float(avg_time_per_item_sec, default=_safe_float(mastery_json.get("avg_time_per_item_sec", 0.0), 0.0)))
    eng = _clip(_safe_float(engagement, default=_safe_float(mastery_json.get("engagement", 0.6), 0.6)), 0.0, 1.0)

    # Binning: deliberately low cardinality (stability, sparse data).
    acc_bin = 0 if acc < 0.55 else (1 if acc < 0.82 else 2)
    mastery_bin = 0 if mastery < 0.45 else (1 if mastery < 0.78 else 2)

    # Time bin: 0=fast, 1=normal, 2=slow
    # Defaults chosen for typical short problems (MCQ or short answer).
    time_bin = 0 if tpi <= 25 else (1 if tpi <= 70 else 2)

    eng_bin = 0 if eng < 0.45 else (1 if eng < 0.75 else 2)

    difficulty_i = _difficulty_to_int(current_difficulty or mastery_json.get("difficulty") or profile.level)

    return {
        "topic": topic_key,
        "acc": acc,
        "avg_time_per_item_sec": tpi,
        "engagement": eng,
        "mastery": _clip(mastery, 0.0, 1.0),
        "bins": {
            "acc": acc_bin,
            "time": time_bin,
            "eng": eng_bin,
            "mastery": mastery_bin,
            "difficulty": difficulty_i,
        },
    }


def _state_key(state: Dict[str, Any]) -> str:
    b = state.get("bins") or {}
    return f"a{b.get('acc',0)}_t{b.get('time',0)}_e{b.get('eng',0)}_m{b.get('mastery',0)}_d{b.get('difficulty',0)}"


# -------------------------
# Policy: contextual bandit (LinUCB-lite)
# -------------------------


def _ctx_features(state: Dict[str, Any]) -> List[float]:
    """Low-dimensional context vector x in R^d.

    We use a hand-designed feature set to keep compute tiny and avoid heavy deps.
    """

    b = state.get("bins") or {}
    # Normalized continuous signals
    acc = float(state.get("acc", 0.0))
    eng = float(state.get("engagement", 0.0))
    mastery = float(state.get("mastery", 0.0))
    tpi = float(state.get("avg_time_per_item_sec", 0.0))

    # Use log-time to reduce sensitivity to outliers.
    log_t = math.log1p(max(0.0, tpi)) / math.log1p(240.0)

    # Bins as weak signals
    return [
        1.0,
        acc,
        mastery,
        eng,
        log_t,
        float(b.get("difficulty", 0)) / 2.0,
    ]


def _dot(a: List[float], b: List[float]) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _mat_vec(A: List[List[float]], x: List[float]) -> List[float]:
    return [_dot(row, x) for row in A]


def _outer(x: List[float]) -> List[List[float]]:
    return [[float(xi) * float(xj) for xj in x] for xi in x]


def _mat_add_inplace(A: List[List[float]], B: List[List[float]]):
    for i in range(len(A)):
        for j in range(len(A[i])):
            A[i][j] = float(A[i][j]) + float(B[i][j])


def _vec_add_inplace(a: List[float], b: List[float]):
    for i in range(len(a)):
        a[i] = float(a[i]) + float(b[i])


def _identity(d: int) -> List[List[float]]:
    return [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]


def _sherman_morrison_update(Ainv: List[List[float]], x: List[float]) -> None:
    """Update A^{-1} for rank-1 update: A <- A + x x^T.

    Sherman–Morrison:
      A^{-1} <- A^{-1} - (A^{-1} x x^T A^{-1}) / (1 + x^T A^{-1} x)

    With small d (<=10) this is fast and numerically stable enough for a demo.
    """

    Ax = _mat_vec(Ainv, x)
    denom = 1.0 + float(_dot(x, Ax))
    if abs(denom) < 1e-9:
        return
    scale = 1.0 / denom
    # Ainv = Ainv - (Ax Ax^T) / denom
    for i in range(len(Ainv)):
        for j in range(len(Ainv[i])):
            Ainv[i][j] = float(Ainv[i][j]) - float(Ax[i]) * float(Ax[j]) * float(scale)


def _linucb_select(
    bandit: Dict[str, Any],
    state: Dict[str, Any],
    epsilon: float,
    alpha: float = 1.25,
) -> Tuple[Action, Dict[str, Any]]:
    actions: List[Action] = [
        "increase_difficulty",
        "decrease_difficulty",
        "switch_topic",
        "reinforce_weak_skill",
        "continue",
    ]

    x = _ctx_features(state)
    d = len(x)

    # Initialize per-action params.
    per = bandit.setdefault("per_action", {})
    for a in actions:
        if a not in per:
            per[a] = {
                "Ainv": _identity(d),  # (A + I)^{-1} initialized as I (ridge prior)
                "b": [0.0 for _ in range(d)],
                "n": 0,
            }

    if random.random() < float(epsilon):
        a = random.choice(actions)
        return a, {"strategy": "epsilon_random", "epsilon": float(epsilon)}

    # Full inverse via Sherman–Morrison updates (fast for small d).
    scores: Dict[str, float] = {}
    for a in actions:
        Ainv = per[a]["Ainv"]
        b = per[a]["b"]
        theta = _mat_vec(Ainv, b)
        mean = _dot(theta, x)
        # UCB term: sqrt(x^T A^{-1} x)
        Ax = _mat_vec(Ainv, x)
        ucb = math.sqrt(max(0.0, _dot(x, Ax)))
        scores[a] = float(mean) + float(alpha) * float(ucb)

    best = max(scores.items(), key=lambda kv: kv[1])[0]
    dbg = {"strategy": "linucb_diag", "scores": scores, "alpha": float(alpha)}
    return best, dbg


def _linucb_update(bandit: Dict[str, Any], state: Dict[str, Any], action: Action, reward: float):
    x = _ctx_features(state)
    per = bandit.setdefault("per_action", {})
    if action not in per:
        return
    Ainv = per[action].get("Ainv")
    b = per[action].get("b")
    if not isinstance(Ainv, list) or not isinstance(b, list):
        return

    # Update inverse with Sherman–Morrison (rank-1)
    _sherman_morrison_update(Ainv, x)

    # Update b (ridge regression target)
    _vec_add_inplace(b, [float(reward) * float(xi) for xi in x])

    per[action]["Ainv"] = Ainv
    per[action]["b"] = b
    per[action]["n"] = int(per[action].get("n", 0)) + 1


# -------------------------
# Policy: tabular Q-learning
# -------------------------


def _q_table(profile: LearnerProfile) -> Dict[str, Any]:
    mj = profile.mastery_json or {}
    rl = mj.setdefault("rl", {})
    q = rl.setdefault("q_table", {})
    if not isinstance(q, dict):
        rl["q_table"] = {}
        q = rl["q_table"]
    return q


def _q_select(state: Dict[str, Any], q_table: Dict[str, Any], epsilon: float) -> Tuple[Action, Dict[str, Any]]:
    actions: List[Action] = [
        "increase_difficulty",
        "decrease_difficulty",
        "switch_topic",
        "reinforce_weak_skill",
        "continue",
    ]
    sk = _state_key(state)
    row = q_table.get(sk) or {}

    if random.random() < float(epsilon):
        return random.choice(actions), {"strategy": "epsilon_random", "epsilon": float(epsilon)}

    best_a = None
    best_q = -1e18
    scores: Dict[str, float] = {}
    for a in actions:
        v = float(row.get(a, 0.0))
        scores[a] = v
        if v > best_q:
            best_q = v
            best_a = a

    return (best_a or "continue"), {"strategy": "greedy_q", "scores": scores}


def _q_update(
    q_table: Dict[str, Any],
    state: Dict[str, Any],
    action: Action,
    reward: float,
    next_state: Optional[Dict[str, Any]],
    alpha: float,
    gamma: float,
):
    sk = _state_key(state)
    row = q_table.setdefault(sk, {})
    cur = float(row.get(action, 0.0))

    target = float(reward)
    if next_state is not None:
        nk = _state_key(next_state)
        nrow = q_table.get(nk) or {}
        max_next = max([float(nrow.get(a, 0.0)) for a in nrow] + [0.0])
        target = float(reward) + float(gamma) * float(max_next)

    new_q = (1.0 - float(alpha)) * float(cur) + float(alpha) * float(target)
    row[action] = float(new_q)


# -------------------------
# Reward shaping (proxy)
# -------------------------


def derive_reward_from_attempt(attempt: Attempt) -> float:
    """Reward proxy in [-1, +1] using only attempt telemetry.

    A research deployment would incorporate retention (delayed), engagement (fine-grained),
    and item-level learning gain. Here we implement a stable proxy:
      - positive for high score and short duration
      - negative when score is low and duration is high
    """

    score = _clip(_safe_float(attempt.score_percent, 0.0) / 100.0, 0.0, 1.0)
    dur = max(0.0, _safe_float(attempt.duration_sec, 0.0))

    # Time normalization: assume 10-15 minutes typical, cap at 45 minutes.
    time_penalty = _clip(dur / (45.0 * 60.0), 0.0, 1.0)

    # Reward: score dominates, time penalty moderates.
    r = 1.25 * score - 0.35 * time_penalty - 0.25
    return _clip(r, -1.0, 1.0)


# -------------------------
# Public API
# -------------------------


def recommend_next_action(
    db: Session,
    *,
    user_id: int,
    document_id: Optional[int],
    topic: Optional[str],
    last_attempt_id: Optional[int],
    recent_accuracy: Optional[float],
    avg_time_per_item_sec: Optional[float],
    engagement: Optional[float],
    current_difficulty: Optional[str],
    policy_type: PolicyType,
    epsilon: float,
) -> Dict[str, Any]:
    ensure_user_exists(db, int(user_id), role="student")

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    if not profile:
        profile = LearnerProfile(user_id=int(user_id), level="beginner", mastery_json={})
        db.add(profile)
        db.commit()
        db.refresh(profile)

    # Optional: derive telemetry from attempt.
    if last_attempt_id is not None:
        at = db.query(Attempt).filter(Attempt.id == int(last_attempt_id), Attempt.user_id == int(user_id)).first()
        if at:
            # Use attempt score as accuracy proxy.
            recent_accuracy = recent_accuracy if recent_accuracy is not None else _clip(_safe_float(at.score_percent) / 100.0, 0.0, 1.0)
            # Mean time per item: if breakdown has n questions, use that; else fallback to total.
            n_items = 0
            try:
                n_items = len(at.breakdown_json or [])
            except Exception:
                n_items = 0
            if n_items > 0 and avg_time_per_item_sec is None:
                avg_time_per_item_sec = float(max(0.0, _safe_float(at.duration_sec)) / float(n_items))

    state = build_state(
        profile=profile,
        topic=topic,
        recent_accuracy=recent_accuracy,
        avg_time_per_item_sec=avg_time_per_item_sec,
        engagement=engagement,
        current_difficulty=current_difficulty,
    )

    mj = profile.mastery_json or {}
    mj.setdefault("difficulty", current_difficulty or mj.get("difficulty") or "easy")
    rl = mj.setdefault("rl", {})

    # Select action.
    if policy_type == "q_learning":
        a, dbg = _q_select(state, _q_table(profile), epsilon=float(epsilon))
    else:
        bandit = rl.setdefault("bandit", {})
        a, dbg = _linucb_select(bandit, state, epsilon=float(epsilon))

    # Translate (action, current difficulty) -> recommended difficulty.
    d_i = int(state.get("bins", {}).get("difficulty", 0))
    if a == "increase_difficulty":
        d_i = min(2, d_i + 1)
    elif a == "decrease_difficulty":
        d_i = max(0, d_i - 1)

    # Policy-safe guardrails (stability constraints):
    # - If accuracy is low, avoid increasing difficulty.
    if float(state.get("acc", 0.0)) < 0.50 and a == "increase_difficulty":
        a = "reinforce_weak_skill"
        dbg["guardrail"] = "low_accuracy_blocked_inc_difficulty"
        d_i = max(0, d_i - 1)

    # Persist updated difficulty prior.
    mj["difficulty"] = _int_to_difficulty(d_i)

    # Store last decision for delayed-reward credit assignment (e.g., retention checks).
    # This is intentionally lightweight and lives in mastery_json to avoid schema changes.
    try:
        rl["last_decision"] = {
            "policy_type": str(policy_type),
            "action": str(a),
            "recommended_difficulty": str(_int_to_difficulty(d_i)),
            "state": state,
            "document_id": int(document_id) if document_id is not None else None,
            "topic": str(topic or "").strip() or None,
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
    except Exception:
        pass

    profile.mastery_json = mj
    db.add(profile)
    db.commit()

    rationale = (
        f"Policy={policy_type}. acc={state['acc']:.2f}, mastery={state['mastery']:.2f}, "
        f"eng={state['engagement']:.2f}, time/bin={state['bins']['time']}. "
        f"Action={a} -> difficulty={_int_to_difficulty(d_i)}."
    )

    return {
        "user_id": int(user_id),
        "policy_type": policy_type,
        "recommended_action": a,
        "recommended_difficulty": _int_to_difficulty(d_i),
        "rationale": rationale,
        "state": state,
        "policy_debug": dbg,
    }


def apply_feedback(
    db: Session,
    *,
    user_id: int,
    policy_type: PolicyType,
    state: Dict[str, Any],
    action: Action,
    reward: Optional[float],
    attempt_id: Optional[int],
    next_state: Optional[Dict[str, Any]],
    alpha: float,
    gamma: float,
) -> Dict[str, Any]:
    ensure_user_exists(db, int(user_id), role="student")

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == int(user_id)).first()
    if not profile:
        profile = LearnerProfile(user_id=int(user_id), level="beginner", mastery_json={})
        db.add(profile)
        db.commit()
        db.refresh(profile)

    mj = profile.mastery_json or {}
    rl = mj.setdefault("rl", {})

    # Reward derivation (if omitted)
    r = reward
    if r is None and attempt_id is not None:
        at = db.query(Attempt).filter(Attempt.id == int(attempt_id), Attempt.user_id == int(user_id)).first()
        if at:
            r = derive_reward_from_attempt(at)
    if r is None:
        r = 0.0

    r = _clip(_safe_float(r), -1.0, 1.0)

    debug: Dict[str, Any] = {"reward": float(r)}

    if policy_type == "q_learning":
        q = _q_table(profile)
        _q_update(q, state=state, action=action, reward=float(r), next_state=next_state, alpha=float(alpha), gamma=float(gamma))
        rl["q_table"] = q
        debug["updated"] = "q_table"
    else:
        bandit = rl.setdefault("bandit", {})
        _linucb_update(bandit, state=state, action=action, reward=float(r))
        debug["updated"] = "bandit"

    profile.mastery_json = mj
    db.add(profile)
    db.commit()

    return {"user_id": int(user_id), "updated": True, "policy_type": policy_type, "debug": debug}
