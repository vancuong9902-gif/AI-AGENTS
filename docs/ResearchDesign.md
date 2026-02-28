# Multi-Agent Based Adaptive Personalized Learning System using RAG and Reinforcement Learning

**Project Title:** *Multi-Agent Based Adaptive Personalized Learning System using RAG and Reinforcement Learning*

**Document Type:** Research-grade technical design (graduate / near IEEE conference standard)

**Scope:** This document specifies a complete end-to-end architecture for a personalized learning system that ingests arbitrary instructional PDFs, builds a curriculum representation via RAG, diagnoses learner proficiency, adapts instruction via a reinforcement-learning (RL) policy (with a contextual-bandit warm start), and provides longitudinal analytics with fairness and explainability constraints.

---

## Section 1 — Formal Problem Definition

### 1.1 Personalization as a Dynamic Optimization Problem

We model learning as a *sequential decision-making* problem over discrete time steps \(t=0,1,\dots\). At each step, the system chooses a pedagogical intervention \(a_t\) (e.g., adjust difficulty, switch topic, provide reinforcement) conditioned on observable interaction data \(o_{\le t}\) and latent learner knowledge \(K_t\).

#### Latent Learner State

Let \(\mathcal{S}\) be the latent skill space extracted from a document (or a predefined domain taxonomy). We represent learner knowledge at time \(t\) as a vector:

\[
K_t \in \mathbb{R}^n,\qquad n = |\mathcal{S}|,
\]

where \(K_{t,i}\) denotes proficiency for skill/topic \(i\) (e.g., mastery probability or ability estimate). The system does **not** observe \(K_t\) directly; it observes noisy evidence from assessments and behaviors.

#### Observation Model and Knowledge Gap Accumulation

Given an item \(q\) targeting a subset of skills \(\mathcal{S}(q)\subseteq\mathcal{S}\), the observed performance signal \(y_t\) (e.g., correctness, rubric score) is a noisy function of \(K_t\):

\[
P(y_t=1\mid K_t, q) = \sigma\left(\sum_{i\in \mathcal{S}(q)} w_{q,i} K_{t,i} - b_q\right),
\]

where \(\sigma\) is the logistic function, \(b_q\) is item difficulty, and \(w_{q,i}\) is a skill-to-item association weight.

Define the *knowledge gap* vector as:

\[
G_t = K^* - K_t,
\]

where \(K^*\) is the curriculum target vector (required mastery). Gap accumulation occurs when the instruction sequence fails to reduce \(\|G_t\|\), often due to topic misalignment or pacing mismatches.

### 1.2 Curriculum Rigidity as Constraint Optimization Failure

A rigid curriculum imposes a fixed ordering \(\pi_0\) over topics and fixed difficulty schedule \(d_t\). This can be interpreted as optimizing learning with constraints:

\[
\max_{\pi} \ \mathbb{E}[\text{LearningGain}(\pi)] \ \ \text{s.t.}\ \pi=\pi_0.
\]

When the constraint \(\pi=\pi_0\) is binding while the learner’s \(K_t\) deviates from the assumed baseline, the system cannot adapt to reduce gaps efficiently—manifesting as avoidable cognitive overload, disengagement, and inequity.

---

### 1.3 System Objectives (Mathematical Form)

We define a multi-objective optimization at each time step:

\[
\max_{\pi} \ \mathbb{E}\Bigg[\sum_{t=0}^{T} \gamma^t \Big( \lambda_1 \Delta L_t - \lambda_2 \Omega_t + \lambda_3 E_t - \lambda_4 F_t \Big)\Bigg]
\]

where:

- \(\Delta L_t\): expected learning gain (increase in mastery / ability).
- \(\Omega_t\): cognitive overload cost.
- \(E_t\): engagement measure.
- \(F_t\): fairness penalty (group-wise parity deviation).
- \(\gamma\in(0,1]\): discount factor.
- \(\lambda_i\ge 0\): trade-off weights.

#### Learning Gain
A practical proxy:
\[
\Delta L_t = \|K_{t+1}\|_1 - \|K_t\|_1
\]

#### Cognitive Overload
Overload is modeled as mismatch between difficulty \(d_t\) and the learner’s current competence:
\[
\Omega_t = \max\{0,\ d_t - \phi(K_t,\mathcal{S}(q_t))\}
\]
where \(\phi\) estimates effective competence on the item’s skill set.

#### Engagement
Engagement combines behavioral telemetry:\
\(E_t = f(\text{time\_on\_task}, \text{dropout\_risk}, \text{voluntary\_attempts}, \text{self-reports})\).

#### Fairness & Explainability
Fairness is enforced via constraints such as equalized expected gain:
\[
\mathbb{E}[\Delta L_t\mid g=a] \approx \mathbb{E}[\Delta L_t\mid g=b]
\]
for protected groups \(g\). Explainability requires that decisions \(a_t\) can be mapped to interpretable drivers (skill gaps, difficulty mismatch, evidence quality).

---

### 1.4 Constraints

1. **Limited labeled data:** sparse item parameters and grading rubrics; cold-start for new PDFs.
2. **Noisy assessment signals:** short quizzes provide high-variance estimates of \(K_t\).
3. **LLM hallucination risk:** generation must be grounded in retrieved evidence.
4. **Real-time inference cost:** latency and budget constraints at scale; policy must be lightweight.

---

## Section 2 — Multi-Agent System Design

### 2.1 Agents and Responsibilities

We propose a Multi-Agent System (MAS) where each agent is a specialized decision module with explicit contracts.

#### Agent 1: Content Agent
- **Responsibility:** Convert PDF \(\to\) topic graph; generate explanations/examples/exercises using RAG-grounded generation.
- **Input space:** \((D, \mathcal{T}, K_t, a_t)\), where \(D\) is document corpus; \(\mathcal{T}\) is topic scope.
- **Output space:** structured learning objects \(\{\text{recap},\text{examples},\text{exercises}\}\) + citations.
- **Internal state:** document index metadata; chunk quality scores; generation templates.
- **Decision policy:** deterministic template selection + LLM generation constrained by evidence.
- **Failure modes:** weak retrieval, missing citations, overlong outputs.
- **Monitoring:** retrieval relevance, citation coverage, chunk quality, refusal rate.

#### Agent 2: Learner Modeling Agent
- **Responsibility:** Maintain posterior over \(K_t\) from assessment/behavior.
- **Input space:** item interactions \((q_t, y_t, \tau_t)\) and RAG topic mapping.
- **Output space:** updated \(\hat{K}_{t+1}\), mastery per topic, uncertainty estimates.
- **Internal state:** posterior parameters (BKT/IRT/Elo) per skill.
- **Decision policy:** Bayesian update or online gradient update.
- **Failure modes:** drift from noisy signals, skill mis-tagging.
- **Monitoring:** calibration curves, uncertainty growth, anomaly detection.

#### Agent 3: Assessment Agent
- **Responsibility:** Generate diagnostic tests and formative exercises; grade responses; explain mistakes.
- **Input space:** topic scope \(\mathcal{T}\), difficulty \(d\), learner level estimate.
- **Output space:** assessment objects + grading breakdown.
- **Internal state:** item bank, difficulty calibration stats.
- **Decision policy:** constrained sampling and item generation via RAG.
- **Failure modes:** ambiguous questions, leakage beyond evidence.
- **Monitoring:** item discrimination, answer key validity, rubric completeness.

#### Agent 4: Adaptive Policy Agent
- **Responsibility:** Choose \(a_t\) (difficulty/topic/reinforcement) maximizing long-term reward.
- **Input space:** state \(S_t\) (knowledge + performance + engagement).
- **Output space:** next action and difficulty recommendation.
- **Internal state:** policy parameters (contextual bandit / Q-table / function approximator).
- **Decision policy:** contextual bandit warm-start \(\to\) RL refinement.
- **Failure modes:** oscillation, exploitation bias, unfair pacing.
- **Monitoring:** action entropy, oscillation frequency, regret estimates.

#### Agent 5: Evaluation & Analytics Agent
- **Responsibility:** Longitudinal analytics, retention modeling, dropout risk, instructor dashboard metrics.
- **Input space:** full event log and learner posteriors.
- **Output space:** composite scores, trend plots, actionable insights.
- **Internal state:** historical aggregates; drift detectors.
- **Failure modes:** misleading metrics; Simpson’s paradox.
- **Monitoring:** cohort-level sanity checks, metric stability.

#### Agent 6: Orchestrator Agent
- **Responsibility:** route events, enforce contracts, manage budgets, handle fallback strategies.
- **Input space:** events (doc upload, quiz submit, timer ticks).
- **Output space:** workflow decisions + agent calls.
- **Internal state:** execution trace, retry/circuit-breaker status.
- **Failure modes:** deadlocks, runaway loops.
- **Monitoring:** event throughput, failure rates by agent, SLA metrics.

---

### 2.2 Text-based Architecture Diagram

```
+---------------------------+         +------------------------------+
|        Frontend UI        |         |         Instructor UI         |
| (chat, quiz, analytics)   |         | (dashboards, cohorts)         |
+------------+--------------+         +---------------+--------------+
             |                                |
             v                                v
+--------------------------------------------------------------------+
|                         API Gateway (FastAPI)                      |
+-----------+----------------+-------------------+-------------------+
            |                |                   |
            v                v                   v
+----------------+   +----------------+   +------------------------+
|  Orchestrator  |-->|  Assessment    |-->| Learner Modeling Agent  |
|     Agent      |   |     Agent      |   | (BKT/IRT/Elo updates)   |
+-------+--------+   +-------+--------+   +-----------+------------+
        |                    |                        |
        v                    v                        |
+----------------+   +----------------+                |
|  Content Agent |<--|     RAG Core   |<---------------+
| (explain/exer) |   | (hybrid+rerank)|
+-------+--------+   +-------+--------+
        |                    |
        v                    v
+----------------+   +----------------+   +------------------------+
| Adaptive Policy|   | Evaluation &   |   | Storage/Telemetry Stack |
|     Agent      |   | Analytics Agent|   | (DB, Vector DB, Logs)   |
+----------------+   +----------------+   +------------------------+
```

---

### 2.3 Agent Interaction Protocol

**Contract primitives** (per call):
- `context`: learner scope (user_id, document_ids, topic)
- `input`: strictly typed request payload
- `output`: typed response + `citations[]` + `confidence`
- `trace`: deterministic event id, timestamps, budgets

**Protocol steps (example):**
1. `DOC_UPLOADED` → Content Agent builds topic graph.
2. Orchestrator emits `PHASE1_COMPLETED` and triggers Entry Test via Assessment Agent.
3. Learner submits → Assessment Agent grades; Learner Modeling Agent updates \(K_t\).
4. Adaptive Policy Agent selects next action; Orchestrator schedules next learning step.

---

### 2.4 Event-driven vs Request-response

- **Request-response:** simplest; synchronous chain; best for MVP, low concurrency.
  - Pros: easier debugging; lower infra complexity.
  - Cons: long tail latency when LLM or reranking is slow.

- **Event-driven (recommended at scale):** events appended to queue; agents consume asynchronously.
  - Pros: isolates failures; supports retries; enables batch embedding/re-ranking.
  - Cons: requires idempotency, ordering guarantees, and eventual consistency.

---

### 2.5 Communication Contract Design

Each agent call must include:
- `schema_version`
- `evidence_bundle`: chunk ids + relevance + quality score
- `budget`: max_tokens, max_latency_ms
- `safety`: constraints (no external knowledge; citations required)

This enables **auditable** decisions and mitigates hallucination propagation.

---

## Section 3 — Advanced RAG Architecture

### 3.1 Document Preprocessing

1. **Normalization:**
   - Unicode normalization (NFC), whitespace canonicalization.
   - Remove OCR artifacts (broken diacritics), normalize hyphenation.

2. **Semantic Chunking Strategy:**
   - Chunk by discourse boundaries (headings, bullet blocks, equation blocks).
   - Target chunk length \(\approx 300\text{–}800\) tokens, with overlap \(\approx 10\%\).

**Justification:**
- Too small → retrieval misses context; too large → context window waste + higher hallucination risk.
- Equation-heavy sections require slightly larger chunks to keep symbol definitions local.

3. **Metadata enrichment:**
   - `(document_id, page_range, section_path, topic_id, language, ocr_quality)`
   - estimated difficulty, Bloom level tags for exercises.

### 3.2 Embedding Model Comparison

- **Sentence-BERT:**
  - Pros: local inference, low cost, good for general similarity.
  - Cons: may underperform on specialized STEM notation.

- **OpenAI embeddings (API):**
  - Pros: strong semantic richness; robust multilingual.
  - Cons: cost + privacy + rate limits.

- **Instructor models:**
  - Pros: instruction-conditioned embeddings improve task alignment.
  - Cons: heavier compute; needs GPU for latency.

**Design choice:** hybrid strategy: local SBERT (baseline) + optional API embeddings when available; fall back to lexical retrieval for offline mode.

### 3.3 Retrieval Architecture

We use a four-stage pipeline:

1. **Dense retrieval:** FAISS ANN over embeddings.
2. **Sparse retrieval:** BM25 (or heuristic lexical scoring) for robustness to rare terms.
3. **Hybrid fusion:** Reciprocal Rank Fusion (RRF):
\[
\text{RRF}(d) = \sum_{m\in\{\text{dense,sparse}\}} \frac{w_m}{k + r_m(d)}
\]
4. **Re-ranking:** LLM-as-a-judge (small, constrained) or cross-encoder reranker.

### 3.4 Hallucination Mitigation

1. **Grounded generation:** output must cite chunk ids; no citation → refusal or low-confidence.
2. **Context filtering:** remove low-quality OCR chunks; reject contradictory evidence.
3. **Confidence scoring:**
   - retrieval confidence = max relevance
   - generation confidence = citation coverage × retrieval confidence
4. **Source attribution:** include inline references to chunk ids + previews.

---

## Section 4 — Dynamic Learner Modeling

We treat \(K_t\) as a latent variable updated online.

### 4.1 Bayesian Knowledge Tracing (BKT)
For binary skills, each skill has mastery probability \(p_t\). Update uses slip/guess parameters.

\[
P(M_t\mid y_t) \propto P(y_t\mid M_t)P(M_t)
\]

BKT is interpretable and data-efficient but assumes binary mastery.

### 4.2 Item Response Theory (IRT)
For learner ability \(\theta_t\) and item difficulty \(b_q\):
\[
P(y=1\mid \theta, q)=\sigma(\theta-b_q)
\]

Extends naturally to multidimensional IRT where \(\theta\equiv K_t\). Requires more data; benefits from priors and pooling.

### 4.3 Elo Rating Adaptation
Online update:
\[
\theta_{t+1}=\theta_t + \eta (y_t - \hat{p}_t),\quad \hat{p}_t=\sigma(\theta_t-b_q)
\]

Elo is simple, stable, and suited to low-labeled regimes.

### 4.4 Real-time Posterior Update and Mastery Thresholds
We maintain \(\hat{K}_t\) and an uncertainty estimate \(\Sigma_t\) (diagonal in MVP). Mastery is declared when:
\[
\hat{K}_{t,i} - z\sqrt{\Sigma_{t,i}} \ge \tau
\]
which prevents premature mastery under uncertainty.

### 4.5 Cold-start
Use priors from:
- entry test results
- document-level difficulty
- cohort priors (teacher-defined)
- language/reading level signals

---

## Section 5 — Adaptive Policy via Reinforcement Learning

### 5.1 MDP Formulation

State \(S_t\) aggregates:
- knowledge \(\hat{K}_t\) or mastery bins
- recent accuracy \(\bar{y}\)
- time spent \(\tau\)
- engagement \(e\)

Action \(A_t\):
- increase difficulty
- decrease difficulty
- switch topic
- reinforce weak skill

Reward \(R_t\):
\[
R_t = \alpha_1 \Delta L_t + \alpha_2 \Delta \text{Retention}_t + \alpha_3 \Delta e_t - \alpha_4 \Omega_t
\]

### 5.2 Q-learning Update
\[
Q(S_t,A_t) \leftarrow (1-\eta)Q(S_t,A_t) + \eta\left(R_t + \gamma \max_a Q(S_{t+1},a)\right)
\]

### 5.3 Exploration Strategy
- **\(\epsilon\)-greedy:** stable for tabular Q-learning.
- **UCB (bandits):** preferred when reward is sparse and state is high-dimensional.

### 5.4 Convergence and Oscillation Risk
Oscillation arises when the policy alternates difficulty/topic due to noisy rewards. Stability constraints:
- hysteresis on difficulty changes (require \(k\) consecutive high/low signals)
- bounded action rate: \(\Delta d\in\{-1,0,+1\}\)
- guardrail: block difficulty increase when \(\bar{y}<0.5\)

### 5.5 Why Contextual Bandits First
In early deployments, a contextual bandit optimizes immediate reward with fewer assumptions:
\[
A_t = \arg\max_a \ \mu_a(x_t) + \beta\cdot \text{UCB}_a(x_t)
\]

Bandits often outperform full RL when:
- long-horizon returns are hard to estimate (sparse delayed rewards)
- state transitions are partially observed
- data is limited (cold-start)

We therefore propose: **bandit warm-start → RL refinement** as data accumulates.

---

## Section 6 — Learning Analytics & Evaluation Model

### 6.1 Composite Scoring

\[
\text{FinalScore} = w_1\cdot \text{Knowledge} + w_2\cdot \text{Improvement} + w_3\cdot \text{Engagement} + w_4\cdot \text{Retention}
\]

- **Knowledge:** \(\|\hat{K}_T\|_1/n\) or final exam score calibrated by IRT.
- **Improvement:** \(\|\hat{K}_T-\hat{K}_0\|_1/n\) or \(\Delta\) exam scores.
- **Engagement:** normalized behavioral index (time-on-task regularity, completion rates).
- **Retention:** delayed post-test accuracy or predicted retention via forgetting curve.

### 6.2 Longitudinal Trend Modeling
Use learning curve slope per topic:
\[
\text{slope}_i = \frac{d}{dt} \hat{K}_{t,i}
\]

### 6.3 Dropout Risk Prediction
Model hazard \(h_t\) with logistic regression / survival models using engagement decay features.

### 6.4 Instructor Dashboard Metrics
- topic mastery heatmap
- cohort difficulty distribution
- action policy logs (explainability)
- hallucination/refusal rate

---

## Section 7 — Infrastructure & Scalability

### 7.1 Microservice Architecture
- **API gateway:** FastAPI
- **RAG service:** chunk store + vector DB + reranker
- **Policy service:** RL/bandit selection + guardrails
- **Analytics service:** batch aggregation

### 7.2 Async Task Queue
Use Celery/RQ/Temporal for:
- PDF preprocessing and embedding
- index rebuild
- periodic analytics

### 7.3 Vector Database Scaling
- 1k users: FAISS local ok
- 10k users: sharded FAISS / pgvector
- 100k users: managed vector DB (HNSW), multi-tenant isolation

### 7.4 GPU Inference Server
Host local reranker / small LLM for cost control and latency stability.

### 7.5 Monitoring & Drift Detection
- retrieval drift: relevance score distribution shift
- policy drift: action entropy collapse
- model drift: calibration error increase

### 7.6 Cost Comparison
- **Local LLM:** higher fixed cost (GPU), low marginal per token
- **API LLM:** zero infra, variable cost, rate limits

Hybrid recommendation: local small models for reranking/grading; API LLM for high-value generation.

---

## Section 8 — Risk & Ethics Analysis

1. **Hallucination propagation:** enforce citation requirements, refusal on low confidence, evidence audits.
2. **Bias amplification:** group-wise evaluation, constraint-based policy learning, careful reward shaping.
3. **Over-adaptation risk:** avoid narrowing curriculum too early; keep exploration; ensure coverage constraints.
4. **Privacy/data protection:** minimize PII, encrypt at rest, access control, per-tenant isolation.
5. **Transparency:** store action rationales and evidence bundles; instructor-readable explanations.
6. **Explainability:** expose drivers: “weak skill X”, “overload detected”, “low retrieval confidence”.

---

## Appendix — Implementation Notes (Mapped to Repository)

- `backend/app/services/rag_service.py`: hybrid retrieval + reranking + quality filtering.
- `backend/app/services/agent_service.py`: Phase-1 topic structure + exam generation/grading.
- `backend/app/services/adaptive_policy_service.py`: contextual bandit + Q-learning scaffolding (policy warm start).
- `backend/app/mas/*`: MAS contracts and orchestrator skeleton.


---

## Appendix A — Prototype Implementation Mapping (This Repository)

This repository includes a **research-prototype** implementation of the architecture above. The prototype prioritizes:
- interpretability and stability under sparse/noisy signals,
- strict evidence-grounding for LLM generation,
- low-footprint online adaptation (bandit warm start; tabular Q-learning option).

### A.1 Key Services

- `backend/app/services/rag_service.py`  
  Hybrid retrieval (keyword + dense) fused via **RRF**, optional LLM re-ranking.

- `backend/app/services/corrective_rag.py`  
  Retrieval grading + query rewrite loop (CRAG-style) for robustness when initial retrieval fails.

- `backend/app/services/agent_service.py`  
  Implements Phase 1 (Document Analysis), Phase 2 (Entry Test), Phase 4 (Topic Exercises), Phase 5 (Final Exam).

- `backend/app/services/learner_modeling_service.py`  
  Online Bayesian mastery update per topic using **Beta posterior** with fractional correctness.

- `backend/app/services/adaptive_policy_service.py`  
  Contextual bandit (LinUCB with Sherman–Morrison inverse updates) + tabular Q-learning.

### A.2 Teaching-Agent API Endpoints

- `GET /api/agent/documents/{document_id}/phase1`
- `POST /api/agent/entry-test/generate`
- `POST /api/agent/entry-test/{quiz_id}/submit`
- `POST /api/agent/topic-exercises/generate`  *(Phase 4 — 10 exercises for a topic)*
- `POST /api/agent/topic-exercises/{quiz_id}/submit`  *(Phase 4 scoring + difficulty scaling)*
- `POST /api/agent/final-exam/generate`
- `POST /api/agent/final-exam/{quiz_id}/submit`

### A.3 Multi-Agent Orchestration Scaffold

- `backend/app/mas/orchestrator.py` coordinates Content → Assessment → LearnerModel → Policy (thin orchestrator).
- `backend/app/mas/agents.py` defines agent wrappers around the above services.

