from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models.classroom import Classroom, ClassroomMember
from app.models.mvp import Course, Topic
from app.models.user import User


def _register_and_login(client: TestClient, email: str, role: str) -> str:
    payload = {"name": role, "email": email, "password": "password123", "role": role}
    client.post('/api/auth/register', json=payload)
    r = client.post('/api/login', json={"email": email, "password": "password123"})
    data = r.json()["data"]
    return data.get("access_token") or data.get("token", {}).get("access_token")


def _create_minimal_course(client: TestClient, teacher_token: str) -> int:
    mem = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(mem)
    mem.seek(0)
    up = client.post(
        '/api/mvp/courses/upload',
        headers={"Authorization": f"Bearer {teacher_token}"},
        files={"file": ("demo.pdf", mem.read(), "application/pdf")},
    )
    return int(up.json()['data']['course_id'])




def _create_classroom_membership(teacher_email: str, student_email: str) -> None:
    with SessionLocal() as db:
        teacher = db.query(User).filter(User.email == teacher_email).first()
        student = db.query(User).filter(User.email == student_email).first()
        classroom = Classroom(teacher_id=int(teacher.id), name='Lop test', join_code=f'TST{int(teacher.id)}{int(student.id)}')
        db.add(classroom)
        db.flush()
        db.add(ClassroomMember(classroom_id=int(classroom.id), user_id=int(student.id)))
        db.commit()

def test_student_guard_returns_404_without_material():
    User.__table__.create(bind=engine, checkfirst=True)
    Classroom.__table__.create(bind=engine, checkfirst=True)
    ClassroomMember.__table__.create(bind=engine, checkfirst=True)
    settings.AUTH_ENABLED = True

    app = create_app(auth_enabled=True)
    with TestClient(app) as client:
        teacher_token = _register_and_login(client, 'teacher.guard@test.local', 'teacher')
        student_token = _register_and_login(client, 'student.guard@test.local', 'student')

        _create_classroom_membership('teacher.guard@test.local', 'student.guard@test.local')

        blocked = client.get('/api/mvp/student/course', headers={"Authorization": f"Bearer {student_token}"})
        assert blocked.status_code == 404
        assert blocked.json()['detail'] == 'Lớp học chưa có tài liệu'


def test_student_status_reports_has_content_flag():
    User.__table__.create(bind=engine, checkfirst=True)
    Classroom.__table__.create(bind=engine, checkfirst=True)
    ClassroomMember.__table__.create(bind=engine, checkfirst=True)
    Course.__table__.create(bind=engine, checkfirst=True)
    Topic.__table__.create(bind=engine, checkfirst=True)
    settings.AUTH_ENABLED = True

    app = create_app(auth_enabled=True)
    with TestClient(app) as client:
        teacher_token = _register_and_login(client, 'teacher.content@test.local', 'teacher')
        student_token = _register_and_login(client, 'student.content@test.local', 'student')

        _create_classroom_membership('teacher.content@test.local', 'student.content@test.local')

        no_content = client.get('/api/mvp/student/status', headers={"Authorization": f"Bearer {student_token}"})
        assert no_content.status_code == 200
        assert no_content.json()['data']['has_content'] is False

        course_id = _create_minimal_course(client, teacher_token)
        client.post(f'/api/mvp/courses/{course_id}/generate-topics', headers={"Authorization": f"Bearer {teacher_token}"})

        has_content = client.get('/api/mvp/student/status', headers={"Authorization": f"Bearer {student_token}"})
        assert has_content.status_code == 200
        assert has_content.json()['data']['has_content'] is True
