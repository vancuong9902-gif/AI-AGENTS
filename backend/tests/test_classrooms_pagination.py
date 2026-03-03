from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import engine
from app.main import create_app
from app.models.classroom import Classroom, ClassroomStudent
from app.models.user import User


def test_teacher_and_student_classrooms_pagination():
    User.__table__.create(bind=engine, checkfirst=True)
    Classroom.__table__.create(bind=engine, checkfirst=True)
    ClassroomStudent.__table__.create(bind=engine, checkfirst=True)

    settings.AUTH_ENABLED = False
    settings.DEMO_SEED = True
    app = create_app(auth_enabled=False)

    with TestClient(app) as client:
        teacher_headers = {"X-User-Id": "101", "X-User-Role": "teacher"}
        student_headers = {"X-User-Id": "202", "X-User-Role": "student"}

        for i in range(3):
            r = client.post('/api/teacher/classrooms', headers=teacher_headers, json={"name": f"Class {i+1}"})
            assert r.status_code == 200
            code = r.json()['data']['invite_code']
            j = client.post('/api/student/classrooms/join', headers=student_headers, json={"invite_code": code})
            assert j.status_code == 200

        t = client.get('/api/teacher/classrooms?page=2&page_size=2', headers=teacher_headers)
        assert t.status_code == 200
        t_data = t.json()['data']
        assert t_data['pagination']['page'] == 2
        assert t_data['pagination']['total'] >= 3
        assert len(t_data['items']) == 1

        s = client.get('/api/student/classrooms?page=1&page_size=2', headers=student_headers)
        assert s.status_code == 200
        s_data = s.json()['data']
        assert s_data['pagination']['total'] >= 3
        assert len(s_data['items']) == 2
