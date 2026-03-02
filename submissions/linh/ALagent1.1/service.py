from questions import QUESTIONS

MASTERY_THRESHOLD = 70.0


def _assign_level(score):
    if score < 40:
        return "Beginner"
    if score < 60:
        return "Elementary"
    if score < 80:
        return "Intermediate"
    return "Advanced"


def evaluate_answers(answers):
    """Evaluate learner answers and return a structured profile."""

    # Keep only 1 answer per question_id (last answer wins)
    answer_map = {a.question_id: a.answer for a in answers}

    correct = 0
    total = len(QUESTIONS)
    topic_stats = {}

    for q in QUESTIONS:
        topic = q.get("topic", "general")
        if topic not in topic_stats:
            topic_stats[topic] = {"correct": 0, "total": 0}
        topic_stats[topic]["total"] += 1

        if answer_map.get(q["id"]) == q["correct"]:
            correct += 1
            topic_stats[topic]["correct"] += 1

    score = round((correct / total) * 100, 2)
    level = _assign_level(score)

    weak_topics = []
    strong_topics = []
    for topic, stats in topic_stats.items():
        topic_score = (stats["correct"] / stats["total"]) * 100 if stats["total"] else 0
        if topic_score >= MASTERY_THRESHOLD:
            strong_topics.append(topic)
        else:
            weak_topics.append(topic)

    if weak_topics:
        recommendation = (
            "Focus on weak topics first, then retake a short quiz after targeted practice."
        )
    else:
        recommendation = "Great work. Maintain mastery with mixed-topic challenge sets."

    return {
        "score": score,
        "level": level,
        "weak_topics": sorted(weak_topics),
        "strong_topics": sorted(strong_topics),
        "recommendation": recommendation,
    }
