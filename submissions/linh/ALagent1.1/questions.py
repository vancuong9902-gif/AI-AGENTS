# questions.py
QUESTIONS = [
    # ===== Beginner =====
    {"id": 1, "question": "1 + 1 = ?", "correct": 2, "topic": "addition"},
    {"id": 2, "question": "5 - 3 = ?", "correct": 2, "topic": "subtraction"},
    {"id": 3, "question": "2 * 4 = ?", "correct": 8, "topic": "multiplication"},
    {"id": 4, "question": "10 / 2 = ?", "correct": 5, "topic": "division"},
    {"id": 5, "question": "3 + 6 - 4 = ?", "correct": 5, "topic": "mixed_arithmetic"},

    # ===== Intermediate =====
    {"id": 6, "question": "2 * 5 + 7 - 9 = ?", "correct": 8, "topic": "order_of_operations"},
    {"id": 7, "question": "15 + 25 - 10 = ?", "correct": 30, "topic": "mixed_arithmetic"},
    {"id": 8, "question": "12 / 3 + 6 = ?", "correct": 10, "topic": "order_of_operations"},
    {"id": 9, "question": "7 * 8 - 20 = ?", "correct": 36, "topic": "mixed_arithmetic"},
    {"id": 10, "question": "(5 + 3) * 4 = ?", "correct": 32, "topic": "order_of_operations"},

    # ===== Advanced =====
    {"id": 11, "question": "√144 = ?", "correct": 12, "topic": "square_roots"},
    {"id": 12, "question": "2^5 = ?", "correct": 32, "topic": "exponents"},
    {"id": 13, "question": "3^4 + 2^3 = ?", "correct": 89, "topic": "exponents"},
    {"id": 14,
        "question": "[20 * (7 - 9 * 2) + 5 * 29] / 3 = ?", "correct": -25, "topic": "order_of_operations"},
    {"id": 15, "question": "1 + 2 + 3 + ... + 99 + 100 = ?", "correct": 5050, "topic": "series"},

    # ===== Very Hard (challenge) =====
    {"id": 16, "question": "Giải phương trình: x - 15 = 30. x = ?", "correct": 45, "topic": "linear_equations"},
    {"id": 17, "question": "Giải phương trình: 3x + 5 = 20. x = ?", "correct": 5, "topic": "linear_equations"},
    {"id": 18, "question": "Giải: 2x^2 = 50, với x > 0. x = ?", "correct": 5, "topic": "quadratic_equations"},
    {"id": 19, "question": "log10(1000) = ?", "correct": 3, "topic": "logarithms"},
    {"id": 20, "question": "2^3 + 3^3 + 4^3 = ?", "correct": 99, "topic": "exponents"},
]
