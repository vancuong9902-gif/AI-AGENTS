from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.db.session import engine
from app.core.config import settings
from app.main import create_app
from app.models.mvp import Course, Exam, Question, Result, Topic
from app.models.user import User


def _register_and_login(client: TestClient, email: str, role: str):
    payload = {"email": email, "password": "password123", "role": role, "full_name": role}
    if role == "student":
        payload["student_code"] = "S001"
    client.post('/api/auth/register', json=payload)
    r = client.post('/api/login', json={"email": email, "password": "password123"})
    body = r.json()["data"]
    return body.get("access_token") or body.get("token", {}).get("access_token")


def test_teacher_results_pagination():
    User.__table__.create(bind=engine, checkfirst=True)
    Course.__table__.create(bind=engine, checkfirst=True)
    Topic.__table__.create(bind=engine, checkfirst=True)
    Exam.__table__.create(bind=engine, checkfirst=True)
    Question.__table__.create(bind=engine, checkfirst=True)
    Result.__table__.create(bind=engine, checkfirst=True)
    settings.AUTH_ENABLED = True
    app = create_app(auth_enabled=True)
    with TestClient(app) as client:
        teacher_token = _register_and_login(client, 'teacher.mvp@test.local', 'teacher')
        student_token = _register_and_login(client, 'student.mvp@test.local', 'student')

        # create exam + 3 results
        mem = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(mem)
        mem.seek(0)
        up = client.post('/api/mvp/courses/upload', headers={"Authorization": f"Bearer {teacher_token}"}, files={"file": ("demo.pdf", mem.read(), "application/pdf")})
        cid = up.json()['data']['course_id']
        exam = client.post(f'/api/mvp/courses/{cid}/generate-entry-test', headers={"Authorization": f"Bearer {teacher_token}"}).json()['data']
        for _ in range(3):
            sr = client.post(f"/api/mvp/student/exams/{exam['exam_id']}/submit", headers={"Authorization": f"Bearer {student_token}"}, json={"answers": {}})
            assert sr.status_code == 200

        resp = client.get('/api/mvp/teacher/results?page=2&page_size=2', headers={"Authorization": f"Bearer {teacher_token}"})
        data = resp.json()['data']
        assert resp.status_code == 200
        assert data['pagination']['page'] == 2
        assert data['pagination']['total'] >= 3
        assert len(data['items']) >= 1
