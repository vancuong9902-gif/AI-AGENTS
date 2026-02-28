from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from service import evaluate_answers
from questions import QUESTIONS

app = FastAPI(title="Learner Profiling Agent")

class Answer(BaseModel):
    question_id: int
    answer: int

class DiagnosticRequest(BaseModel):
    answers: List[Answer]

@app.get("/")
def root():
    return {"message": "Backend running"}

@app.get("/profile/diagnostic/questions")
def get_diagnostic_questions():
    return [{"id": q["id"], "question": q["question"]} for q in QUESTIONS]

@app.post("/profile/diagnostic")
def diagnostic_test(req: DiagnosticRequest):
    score, level = evaluate_answers(req.answers)
    return {"score": score, "level": level}
