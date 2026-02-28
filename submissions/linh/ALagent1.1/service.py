from questions import QUESTIONS


def evaluate_answers(answers):
    """Evaluate learner answers.

    Important: Avoid double-counting when the client sends duplicate answers
    for the same question_id.
    """

    # Keep only 1 answer per question_id (last answer wins)
    answer_map = {a.question_id: a.answer for a in answers}

    correct = 0
    total = len(QUESTIONS)

    for q in QUESTIONS:
        if answer_map.get(q["id"]) == q["correct"]:
            correct += 1

    score = (correct / total) * 100

    if score < 40:
        level = "Beginner"
    elif score <= 70:
        level = "Intermediate"
    else:
        level = "Advanced"

    return round(score, 2), level
