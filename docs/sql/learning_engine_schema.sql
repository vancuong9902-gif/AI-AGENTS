-- AI Teacher Platform schema (PostgreSQL)

create table if not exists le_documents (
  id uuid primary key,
  owner_id bigint not null,
  filename text not null,
  storage_url text not null,
  created_at timestamptz not null default now()
);

create table if not exists le_topics (
  id uuid primary key,
  document_id uuid not null references le_documents(id) on delete cascade,
  title text not null,
  summary text not null,
  difficulty numeric(4,3) not null,
  keywords jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists le_entrance_tests (
  id uuid primary key,
  student_id bigint not null,
  document_id uuid not null references le_documents(id) on delete cascade,
  adaptive_version int not null default 1,
  questions jsonb not null,
  score numeric(5,4),
  level text,
  created_at timestamptz not null default now()
);

create table if not exists le_learning_paths (
  id uuid primary key,
  student_id bigint not null,
  document_id uuid not null references le_documents(id) on delete cascade,
  level text not null,
  steps jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists le_exercise_attempts (
  id uuid primary key,
  student_id bigint not null,
  topic_id uuid not null references le_topics(id) on delete cascade,
  difficulty text not null,
  score numeric(5,4),
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists le_progress_snapshots (
  id uuid primary key,
  student_id bigint not null,
  completion_rate numeric(5,4) not null,
  mastery_by_topic jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists le_final_exams (
  id uuid primary key,
  student_id bigint not null,
  document_id uuid not null references le_documents(id) on delete cascade,
  payload jsonb not null,
  score numeric(5,4),
  created_at timestamptz not null default now()
);

create table if not exists le_performance_reports (
  id uuid primary key,
  student_id bigint not null,
  level text not null,
  strengths jsonb not null,
  weaknesses jsonb not null,
  recommendations jsonb not null,
  metrics jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_le_topics_document_id on le_topics(document_id);
create index if not exists idx_le_tests_student_id on le_entrance_tests(student_id);
create index if not exists idx_le_progress_student_id on le_progress_snapshots(student_id);
