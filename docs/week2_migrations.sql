-- Week 2 migrations (DDL) - PostgreSQL
-- Bạn có thể chuyển sang Alembic op.create_table tương ứng.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE,
  full_name text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learner_profiles (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  level text NOT NULL DEFAULT 'beginner',
  mastery_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text,
  filename text NOT NULL,
  mime_type text NOT NULL,
  tags text[],
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index int NOT NULL,
  text text NOT NULL,
  meta jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS rag_queries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  query text NOT NULL,
  top_k int NOT NULL DEFAULT 5,
  filters jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_chunk_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quiz_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic text NOT NULL,
  level text NOT NULL,
  source_query_id uuid REFERENCES rag_queries(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS questions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quiz_set_id uuid NOT NULL REFERENCES quiz_sets(id) ON DELETE CASCADE,
  type text NOT NULL DEFAULT 'mcq',
  stem text NOT NULL,
  options jsonb NOT NULL,
  correct_index int NOT NULL,
  explanation text,
  sources jsonb NOT NULL DEFAULT '[]'::jsonb,
  order_no int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_questions_quiz_order ON questions(quiz_set_id, order_no);

CREATE TABLE IF NOT EXISTS attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quiz_set_id uuid NOT NULL REFERENCES quiz_sets(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  score_percent int NOT NULL,
  answers_json jsonb NOT NULL,
  breakdown_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  duration_sec int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attempts_quiz ON attempts(quiz_set_id);
CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id);
