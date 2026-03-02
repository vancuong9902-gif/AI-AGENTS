-- Normalized PostgreSQL schema (3NF) for LMS domain
-- Entities requested: users, teachers, students, courses, topics, tests,
-- questions, answers, test_results, learning_paths, progress_tracking.

BEGIN;

-- ------------------------------------------------------------
-- Utility: updated_at trigger
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- Users and role-specific profiles
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id              BIGSERIAL PRIMARY KEY,
  email           VARCHAR(255) NOT NULL UNIQUE,
  password_hash   TEXT NOT NULL,
  full_name       VARCHAR(150) NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS teachers (
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  employee_code   VARCHAR(50) NOT NULL UNIQUE,
  specialization  VARCHAR(120),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS students (
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  student_code    VARCHAR(50) NOT NULL UNIQUE,
  grade_level     SMALLINT CHECK (grade_level BETWEEN 1 AND 12),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Course and topic catalog
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS courses (
  id              BIGSERIAL PRIMARY KEY,
  course_code     VARCHAR(30) NOT NULL UNIQUE,
  title           VARCHAR(255) NOT NULL,
  description     TEXT,
  created_by_teacher_id BIGINT REFERENCES teachers(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS topics (
  id              BIGSERIAL PRIMARY KEY,
  topic_code      VARCHAR(50) NOT NULL UNIQUE,
  title           VARCHAR(255) NOT NULL,
  description     TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Many-to-many course <-> topic
CREATE TABLE IF NOT EXISTS course_topics (
  course_id       BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  topic_id        BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  topic_order     INTEGER NOT NULL CHECK (topic_order > 0),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (course_id, topic_id),
  UNIQUE (course_id, topic_order)
);

-- Many-to-many teacher <-> course (teaching assignments)
CREATE TABLE IF NOT EXISTS teacher_courses (
  teacher_id      BIGINT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  course_id       BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (teacher_id, course_id)
);

-- ------------------------------------------------------------
-- Tests, questions, answers
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tests (
  id              BIGSERIAL PRIMARY KEY,
  course_id       BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  topic_id        BIGINT REFERENCES topics(id) ON DELETE SET NULL,
  created_by_teacher_id BIGINT REFERENCES teachers(id) ON DELETE SET NULL,
  title           VARCHAR(255) NOT NULL,
  description     TEXT,
  duration_minutes INTEGER CHECK (duration_minutes > 0),
  total_points    NUMERIC(8,2) NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questions (
  id              BIGSERIAL PRIMARY KEY,
  test_id         BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
  topic_id        BIGINT REFERENCES topics(id) ON DELETE SET NULL,
  question_text   TEXT NOT NULL,
  question_type   VARCHAR(20) NOT NULL CHECK (question_type IN ('single_choice','multiple_choice','true_false','short_answer')),
  points          NUMERIC(6,2) NOT NULL DEFAULT 1 CHECK (points >= 0),
  display_order   INTEGER NOT NULL CHECK (display_order > 0),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (test_id, display_order)
);

CREATE TABLE IF NOT EXISTS answers (
  id              BIGSERIAL PRIMARY KEY,
  question_id     BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  answer_text     TEXT NOT NULL,
  is_correct      BOOLEAN NOT NULL DEFAULT FALSE,
  display_order   INTEGER NOT NULL CHECK (display_order > 0),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (question_id, display_order)
);

-- ------------------------------------------------------------
-- Test results and per-question responses (normalized)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_results (
  id              BIGSERIAL PRIMARY KEY,
  test_id         BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
  student_id      BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  attempt_no      INTEGER NOT NULL DEFAULT 1 CHECK (attempt_no > 0),
  score           NUMERIC(8,2) NOT NULL DEFAULT 0,
  max_score       NUMERIC(8,2) NOT NULL DEFAULT 0,
  started_at      TIMESTAMPTZ,
  submitted_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (test_id, student_id, attempt_no)
);

CREATE TABLE IF NOT EXISTS test_result_answers (
  id              BIGSERIAL PRIMARY KEY,
  test_result_id  BIGINT NOT NULL REFERENCES test_results(id) ON DELETE CASCADE,
  question_id     BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  answer_id       BIGINT REFERENCES answers(id) ON DELETE SET NULL,
  free_text_answer TEXT,
  is_correct      BOOLEAN,
  awarded_points  NUMERIC(6,2) NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (test_result_id, question_id)
);

-- ------------------------------------------------------------
-- Learning paths and progress tracking
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS learning_paths (
  id              BIGSERIAL PRIMARY KEY,
  student_id      BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  title           VARCHAR(255) NOT NULL,
  goal            TEXT,
  created_by_teacher_id BIGINT REFERENCES teachers(id) ON DELETE SET NULL,
  status          VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','completed','archived')),
  start_date      DATE,
  target_end_date DATE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ordered courses in a learning path
CREATE TABLE IF NOT EXISTS learning_path_courses (
  learning_path_id BIGINT NOT NULL REFERENCES learning_paths(id) ON DELETE CASCADE,
  course_id        BIGINT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
  position         INTEGER NOT NULL CHECK (position > 0),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (learning_path_id, course_id),
  UNIQUE (learning_path_id, position)
);

CREATE TABLE IF NOT EXISTS progress_tracking (
  id              BIGSERIAL PRIMARY KEY,
  student_id      BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  course_id       BIGINT REFERENCES courses(id) ON DELETE CASCADE,
  topic_id        BIGINT REFERENCES topics(id) ON DELETE CASCADE,
  learning_path_id BIGINT REFERENCES learning_paths(id) ON DELETE CASCADE,
  progress_percent NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
  mastery_level   VARCHAR(20) CHECK (mastery_level IN ('beginner','intermediate','advanced')),
  last_activity_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- at least one scope to track progress on
  CHECK (course_id IS NOT NULL OR topic_id IS NOT NULL OR learning_path_id IS NOT NULL)
);

-- ------------------------------------------------------------
-- Indexes
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_teachers_user_id ON teachers(user_id);
CREATE INDEX IF NOT EXISTS idx_students_user_id ON students(user_id);
CREATE INDEX IF NOT EXISTS idx_courses_creator_teacher ON courses(created_by_teacher_id);
CREATE INDEX IF NOT EXISTS idx_course_topics_topic_id ON course_topics(topic_id);
CREATE INDEX IF NOT EXISTS idx_teacher_courses_course_id ON teacher_courses(course_id);
CREATE INDEX IF NOT EXISTS idx_tests_course_id ON tests(course_id);
CREATE INDEX IF NOT EXISTS idx_tests_topic_id ON tests(topic_id);
CREATE INDEX IF NOT EXISTS idx_questions_test_id ON questions(test_id);
CREATE INDEX IF NOT EXISTS idx_questions_topic_id ON questions(topic_id);
CREATE INDEX IF NOT EXISTS idx_answers_question_id ON answers(question_id);
CREATE INDEX IF NOT EXISTS idx_test_results_student_test ON test_results(student_id, test_id);
CREATE INDEX IF NOT EXISTS idx_test_result_answers_result_id ON test_result_answers(test_result_id);
CREATE INDEX IF NOT EXISTS idx_learning_paths_student_id ON learning_paths(student_id);
CREATE INDEX IF NOT EXISTS idx_learning_path_courses_course_id ON learning_path_courses(course_id);
CREATE INDEX IF NOT EXISTS idx_progress_student_id ON progress_tracking(student_id);
CREATE INDEX IF NOT EXISTS idx_progress_learning_path_id ON progress_tracking(learning_path_id);
CREATE INDEX IF NOT EXISTS idx_progress_last_activity_at ON progress_tracking(last_activity_at);

-- ------------------------------------------------------------
-- updated_at triggers
-- ------------------------------------------------------------
DO $$
DECLARE
  t TEXT;
BEGIN
  FOR t IN
    SELECT unnest(ARRAY[
      'users','teachers','students','courses','topics','course_topics','teacher_courses',
      'tests','questions','answers','test_results','test_result_answers',
      'learning_paths','learning_path_courses','progress_tracking'
    ])
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_%I_updated_at ON %I;', t, t);
    EXECUTE format(
      'CREATE TRIGGER trg_%I_updated_at BEFORE UPDATE ON %I
       FOR EACH ROW EXECUTE FUNCTION set_updated_at();',
      t, t
    );
  END LOOP;
END $$;

-- ------------------------------------------------------------
-- Sample seed data
-- ------------------------------------------------------------
INSERT INTO users (email, password_hash, full_name) VALUES
  ('teacher.alice@example.edu', 'hashed_pw_1', 'Alice Nguyen'),
  ('student.bob@example.edu', 'hashed_pw_2', 'Bob Tran'),
  ('student.chi@example.edu', 'hashed_pw_3', 'Chi Le');

INSERT INTO teachers (user_id, employee_code, specialization)
SELECT id, 'TCH-001', 'Mathematics'
FROM users WHERE email = 'teacher.alice@example.edu';

INSERT INTO students (user_id, student_code, grade_level)
SELECT id, 'STD-001', 10 FROM users WHERE email = 'student.bob@example.edu';

INSERT INTO students (user_id, student_code, grade_level)
SELECT id, 'STD-002', 10 FROM users WHERE email = 'student.chi@example.edu';

INSERT INTO courses (course_code, title, description, created_by_teacher_id)
VALUES ('MATH-ALG-10', 'Algebra 10', 'Core algebra for grade 10', 1);

INSERT INTO topics (topic_code, title, description) VALUES
  ('ALG-LINEAR', 'Linear Equations', 'Solve one-variable linear equations'),
  ('ALG-FACTOR', 'Factoring', 'Factor quadratic expressions');

INSERT INTO course_topics (course_id, topic_id, topic_order) VALUES
  (1, 1, 1),
  (1, 2, 2);

INSERT INTO teacher_courses (teacher_id, course_id) VALUES (1, 1);

INSERT INTO tests (course_id, topic_id, created_by_teacher_id, title, description, duration_minutes, total_points)
VALUES (1, 1, 1, 'Linear Equations Quiz', 'Quick check on solving linear equations', 20, 10);

INSERT INTO questions (test_id, topic_id, question_text, question_type, points, display_order) VALUES
  (1, 1, 'Solve: 2x + 3 = 11', 'single_choice', 5, 1),
  (1, 1, 'Which value satisfies x - 4 = 10?', 'single_choice', 5, 2);

INSERT INTO answers (question_id, answer_text, is_correct, display_order) VALUES
  (1, 'x = 4', TRUE, 1),
  (1, 'x = 7', FALSE, 2),
  (2, 'x = 14', TRUE, 1),
  (2, 'x = 6', FALSE, 2);

INSERT INTO test_results (test_id, student_id, attempt_no, score, max_score, started_at, submitted_at)
VALUES (1, 1, 1, 10, 10, NOW() - INTERVAL '25 minutes', NOW() - INTERVAL '5 minutes');

INSERT INTO test_result_answers (test_result_id, question_id, answer_id, is_correct, awarded_points)
VALUES
  (1, 1, 1, TRUE, 5),
  (1, 2, 3, TRUE, 5);

INSERT INTO learning_paths (student_id, title, goal, created_by_teacher_id, status, start_date, target_end_date)
VALUES (1, 'Algebra Foundations', 'Master linear equations and factoring', 1, 'active', CURRENT_DATE, CURRENT_DATE + 30);

INSERT INTO learning_path_courses (learning_path_id, course_id, position)
VALUES (1, 1, 1);

INSERT INTO progress_tracking (student_id, course_id, topic_id, learning_path_id, progress_percent, mastery_level, last_activity_at)
VALUES
  (1, 1, 1, 1, 60.00, 'intermediate', NOW() - INTERVAL '1 day'),
  (1, 1, 2, 1, 20.00, 'beginner', NOW());

COMMIT;
