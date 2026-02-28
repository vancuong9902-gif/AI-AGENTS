import json

from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve backend root (…/backend/) regardless of current working directory
BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"

class Settings(BaseSettings):
    # Đọc đúng backend/.env và tránh BOM + key thừa làm chết app
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "AI Learning Agent"
    ENV: str = "dev"
    # Có thể set 1 origin hoặc nhiều origin, ngăn cách bằng dấu phẩy
    # Ví dụ: "http://localhost:5173,https://example.com"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    DATABASE_URL: str

    # ===== Async Queue (RQ/Redis) =====
    ASYNC_QUEUE_ENABLED: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    RQ_DEFAULT_TIMEOUT_SEC: int = 1800


    # ===== Optional Auth (Mode A default: disabled) =====
    # When AUTH_ENABLED=false, the frontend can still authenticate via demo headers:
    #   X-User-Id, X-User-Role
    # JWT endpoints remain available and can be enabled later by flipping AUTH_ENABLED=true.
    AUTH_ENABLED: bool = False
    JWT_SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # ===== LLM settings =====
    # OPENAI_API_KEY:
    # - Nếu dùng OpenAI API: set key thật.
    # - Nếu dùng LLM local (Ollama/LM Studio): có thể để trống và chỉ set OPENAI_BASE_URL.
    OPENAI_API_KEY: str | None = None

    # Dùng cho provider tương thích OpenAI (Ollama/LM Studio).
    # Ví dụ Ollama: http://localhost:11434/v1
    OPENAI_BASE_URL: str | None = None

    # Optional advanced knobs for OpenAI-compatible providers.
    # These are useful when you use non-OpenAI vendors (e.g., Alibaba Cloud Model Studio / DashScope)
    # that require extra headers/query/body parameters.
    #
    # NOTE: Values should be JSON strings (objects) in your .env, for example:
    #   OPENAI_EXTRA_HEADERS_JSON={"X-Foo":"bar"}
    #   OPENAI_EXTRA_QUERY_JSON={"foo":"bar"}
    #   OPENAI_EXTRA_BODY_JSON={"enable_thinking":false}
    OPENAI_EXTRA_HEADERS_JSON: str | None = None
    OPENAI_EXTRA_QUERY_JSON: str | None = None
    OPENAI_EXTRA_BODY_JSON: str | None = None

    # Backward/alias support: some env files use OPENAI_EMBED_MODEL
    OPENAI_EMBED_MODEL: str | None = None

    # Embeddings model name (for Semantic RAG).
    # - OpenAI default: text-embedding-3-small
    # - Alibaba Cloud Model Studio (DashScope) examples: text-embedding-v3 (intl), text-embedding-v4 (Beijing)
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    @model_validator(mode="after")
    def _apply_env_aliases(self):
        # If OPENAI_EMBEDDING_MODEL is left as default, but OPENAI_EMBED_MODEL is provided, prefer it.
        if (not (self.OPENAI_EMBEDDING_MODEL or '').strip()) or self.OPENAI_EMBEDDING_MODEL.strip() == 'text-embedding-3-small':
            if (self.OPENAI_EMBED_MODEL or '').strip():
                self.OPENAI_EMBEDDING_MODEL = self.OPENAI_EMBED_MODEL.strip()
        return self

    # Optional: improve content quality with an LLM.
    # - If OPENAI_API_KEY is missing (và không set OPENAI_BASE_URL), the app falls back to deterministic generators.
    # Default model id.
    # ✅ Default per request: OpenAI GPT-oss 20B
    # (On Azure OpenAI, set OPENAI_CHAT_MODEL to your *deployment name*.)
    # If you run behind an OpenAI-compatible gateway (e.g., MegaLLM), override this in .env.
    OPENAI_CHAT_MODEL: str = "openai-gpt-oss-20b"

    # Optional: a "JSON formatter" model used when the primary model tends to emit
    # chain-of-thought / <think> blocks or otherwise fails to output strict JSON.
    #
    # Recommended when using reasoning-heavy models like DeepSeek-R1:
    #   OPENAI_CHAT_MODEL=deepseek-r1-distill-llama-70b
    #   OPENAI_JSON_MODEL=openai-gpt-oss-20b
    #
    # Leave empty/None to disable explicit formatter selection.
    OPENAI_JSON_MODEL: str | None = None

    # ===== OpenAI SDK / Gateway timeouts =====
    # If your gateway/model is sometimes slow, increasing these can reduce false "unavailable"
    # states. Keep retries low to avoid long hangs.
    OPENAI_HTTP_TIMEOUT_SEC: int = 120
    OPENAI_MAX_RETRIES: int = 1

    # LLM status (Health page) should stay fast; we test with this shorter timeout.
    OPENAI_STATUS_TEST_TIMEOUT_SEC: int = 12
    OPENAI_STATUS_TEST_MAX_TOKENS: int = 64

    # ===== Azure OpenAI (optional) =====
    # If you are using Azure OpenAI instead of OpenAI Cloud/MegaLLM/Ollama, set:
    #   AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
    #   AZURE_OPENAI_API_KEY=<your key>
    #   AZURE_OPENAI_API_VERSION=2024-02-15-preview (or your chosen api-version)
    # and set OPENAI_CHAT_MODEL to your Azure deployment name.
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"

    # Optional: controls reasoning tokens for reasoning-capable models when using the Responses API
    # Values: none | low | medium | high | xhigh
    # For broad provider compatibility, keep this "none" by default.
    # (Some gateways don't support reasoning.* fields and may reject the request.)
    OPENAI_REASONING_EFFORT: str = "none"

    # ===== Alibaba Cloud Model Studio (DashScope) / Qwen (optional) =====
    # DashScope supports OpenAI-compatible APIs and exposes some non-standard parameters
    # via `extra_body` (OpenAI SDK).
    #
    # For Qwen3/Qwen3.5 hybrid-thinking models, you can control whether the model uses
    # thinking mode and how many tokens it can spend on thinking.
    #
    # IMPORTANT: These parameters are only sent automatically when OPENAI_BASE_URL
    # contains "dashscope" (so it won't break OpenAI Cloud).
    #
    # Valid values:
    # - QWEN_ENABLE_THINKING:
    #     true  => enable thinking (may increase latency and can reduce JSON stability)
    #     false => disable thinking (recommended for strict JSON outputs)
    #     empty => auto (project default: disable thinking for chat_json calls)
    QWEN_ENABLE_THINKING: bool | None = None
    # Optional cap for thinking tokens (DashScope param: thinking_budget)
    QWEN_THINKING_BUDGET: int | None = None

    QUIZ_GEN_MODE: str = "auto"    # auto | llm | offline
    LESSON_GEN_MODE: str = "auto"  # auto | llm | offline

    # Semantic RAG (FAISS + embeddings)
    # - Khi dùng Ollama local để chat, bạn có thể tắt semantic RAG để tránh gọi embeddings.
    # - Mặc định True để giữ hành vi cũ (nếu có OPENAI_API_KEY thật).
    SEMANTIC_RAG_ENABLED: bool = True

    # ===== Defaults / Agentic RAG knobs (demo-friendly) =====
    # Tài liệu thường do giáo viên upload theo user_id. Nếu UI không truyền document_ids,
    # hệ thống sẽ auto-scope theo DEFAULT_TEACHER_ID để tránh trộn tài liệu không liên quan.
    DEFAULT_TEACHER_ID: int = 1

    # Corrective RAG (CRAG): retrieve -> grade -> rewrite query -> retrieve (max N vòng)
    CRAG_MAX_ITERS: int = 2
    # Lexical relevance threshold (0..1). Thấp hơn -> dễ pass; cao hơn -> strict hơn.
    CRAG_MIN_RELEVANCE: float = 0.18
    # Tutor off-topic gate via LLM (strict JSON output). If False, fallback to CRAG flow.
    TUTOR_LLM_OFFTOPIC_ENABLED: bool = False

    # ===== Reranking (2nd-stage refinement) =====
    # Reference: "Reranking in RAG" (2-stage refinement), especially technique #5 (LLM-as-a-Judge).
    # Modes: off | llm_judge | auto
    # - auto: enable llm_judge when llm_available(); otherwise off.
    RERANK_MODE: str = "auto"

    # How many candidates to fetch before reranking (multiplied by requested top_k).
    # Example: top_k=6, multiplier=6 -> fetch up to 36 candidates (capped by RERANK_MAX_CANDIDATES).
    RERANK_CANDIDATE_MULTIPLIER: int = 6

    # Hard cap for rerank candidate list (keeps latency/cost stable).
    RERANK_MAX_CANDIDATES: int = 24

    # Truncate each chunk text before sending to the reranker.
    RERANK_MAX_CHARS_PER_CHUNK: int = 850

    # OCR/text-quality guard: nếu phần lớn chunk bị lỗi OCR thì KHÔNG sinh câu hỏi (trả NEED_CLEAN_TEXT)
    OCR_BAD_CHUNK_RATIO: float = 0.6
    OCR_MIN_QUALITY_SCORE: float = 0.45

    # PDF extraction: pick best extractor output (PyMuPDF/pdfplumber/pypdf).
    # If the best extracted text quality is still below this threshold, downstream guards may return NEED_CLEAN_TEXT.
    PDF_EXTRACT_MIN_QUALITY_SCORE: float = 0.35

    # ===== PDF OCR fallback (scanned/image-only PDFs) =====
    # When enabled, OCR is attempted if text-layer extraction quality is too low.
    PDF_OCR_ENABLED: bool = True
    # Tesseract language packs to use (install in Dockerfile).
    PDF_OCR_LANG: str = "vie+eng"
    # Safety cap for OCR pages.
    PDF_OCR_MAX_PAGES: int = 200
    # Render zoom for OCR; higher -> better accuracy but slower.
    PDF_OCR_ZOOM: float = 2.5
    # If best text-layer score is below this, try OCR.
    PDF_OCR_TRIGGER_MIN_QUALITY_SCORE: float = 0.22
    # Completeness guard: do not choose extraction outputs with much lower page coverage.
    PDF_EXTRACT_MIN_COVERAGE_RATIO: float = 0.83

    # ===== Optional quality loops (LLM refine passes) =====
    # Quiz refine: off | auto | always
    # - auto: only refine when llm_available()
    QUIZ_LLM_REFINE: str = "auto"
    QUIZ_LLM_REFINE_MAX_QUESTIONS: int = 20

    # Topic title rewrite: off | auto | always
    TOPIC_LLM_TITLES: str = "auto"

    # ===== Topic post-processing (optional) =====
    # Use an LLM to filter/merge/rename the extracted topic list.
    # Values: off | auto | always
    TOPIC_LLM_FILTER: str = "auto"

    # Keep the "Bài N." prefix in topic titles (default False).
    # If False, titles are de-numbered for cleaner teacher-style headings.
    TOPIC_KEEP_LESSON_PREFIX: bool = False

    # Max number of topics to store/display per document.
    TOPIC_MAX_TOPICS: int = 120

    # Numeric heading depth cap for topic boundaries.
    # Example: with depth=2 we allow "2.3" but NOT "2.3.1" to become a new topic.
    # This prevents over-splitting textbook PDFs into tiny, low-signal topics.
    TOPIC_NUM_HEADING_MAX_DEPTH: int = 3

    # Minimum body size (in chars) for a topic.
    # Topics below this threshold will be merged with adjacent topics so each topic
    # has enough evidence to generate study material + 3 difficulty levels of questions.
    # Minimum body size (in chars) for a topic.
    # Topics below this threshold will be merged with adjacent topics so each topic
    # has enough evidence for study material + multi-level question generation.
    TOPIC_MIN_BODY_CHARS: int = 1400

    # Thea-like Study Guide generation mode:
    # - json: strict structured output (may be brittle on some OpenAI-compatible servers)
    # - markdown: robust plain-text markdown guide (recommended for Ollama/OpenAI-compatible gateways)
    TOPIC_STUDY_GUIDE_MODE: str = "markdown"

    # When listing topics with detail=1, how many topics are allowed to call LLM for richer study guides.
    TOPIC_LLM_VIEW_MAX_TOPICS: int = 20

    # Lesson-mode splitting: off | auto | always
    # auto: nếu tài liệu có nhiều 'Bài 1..', chỉ split theo 'Bài', không split theo '1. Mục tiêu'...
    TOPIC_LESSON_MODE: str = "auto"

    # PDF heading level strategy for topic extraction:
    # - auto: try topic/heading split first; if it yields too few topics, fall back to chapter split
    # - topic: always use topic/heading-based splitting (best for study-guide style)
    # - chapter: always split only by chapters (coarser, but stable for some books)
    TOPIC_PDF_HEADING_LEVEL: str = "auto"

    # Hide appendix sections ("Phụ lục" / "Appendix") from UI topic lists.
    # They can still exist in raw documents for testing, but won't appear as learnable topics.
    TOPIC_HIDE_APPENDIX: bool = True

    # ===== Optional: external enrichment for "Ít dữ liệu" topics =====
    # Modes: off | auto | always
    # - auto: only enrich when a topic body is short or contains the marker "Ít dữ liệu".
    # This feature will try to fetch short, public educational snippets (e.g., Wikipedia summaries)
    # and attach them with explicit sources.
    TOPIC_EXTERNAL_ENRICH: str = "auto"
    TOPIC_EXTERNAL_MIN_BODY_CHARS: int = 900
    TOPIC_EXTERNAL_MAX_SOURCES: int = 2
    TOPIC_EXTERNAL_WIKI_LANG: str = "vi"  # vi | en
    TOPIC_EXTERNAL_TIMEOUT_SEC: int = 6

    # ===== Topic -> Exam readiness =====
    # Ensure every extracted topic has enough content to generate quizzes/exams.
    # We do this by expanding the topic's chunk-range (allowing overlaps) so each
    # topic has a minimum evidence pool.
    TOPIC_MIN_CHUNKS_FOR_QUIZ: int = 4
    TOPIC_MIN_CHARS_FOR_QUIZ: int = 1400
    TOPIC_MAX_EXPAND_CHUNKS: int = 6

    # Essay question refine: off | auto | always
    # - auto: only refine when llm_available()
    ESSAY_LLM_REFINE: str = "auto"
    ESSAY_LLM_REFINE_MAX_QUESTIONS: int = 10

    # Auto-grade essay answers (LLM): off | auto | always
    # - auto: only grade when llm_available()
    ESSAY_AUTO_GRADE: str = "always"
    ESSAY_AUTO_GRADE_MIN_CHARS: int = 40

    # ===== Teacher-style learning plan (7-day) =====
    # Learning plan generation: off | auto | llm | offline
    # - auto: use llm when available, else offline
    LEARNING_PLAN_MODE: str = "auto"
    LEARNING_PLAN_DAYS: int = 7
    LEARNING_PLAN_MINUTES_PER_DAY: int = 35

    # Homework generation + grading (LLM)
    HOMEWORK_LLM_GEN: str = "auto"   # auto | llm | offline
    HOMEWORK_AUTO_GRADE: str = "always"  # off | auto | always
    HOMEWORK_MIN_CHARS: int = 40
    HOMEWORK_MAX_POINTS: int = 10

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        if v is None or v == "":
            return []

        # Nếu đã là list thì giữ nguyên
        if isinstance(v, list):
            return v

        # Nếu là string: ưu tiên parse JSON list, fallback split by comma
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                try:
                    return json.loads(s)
                except Exception:
                    pass
            return [item.strip() for item in s.split(",") if item.strip()]

        return v


# QUAN TRỌNG: main.py đang import "settings"
settings = Settings()
