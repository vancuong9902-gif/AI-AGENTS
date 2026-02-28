# Composite Analytics + Dashboard Metrics (Research Notes)

This module implements a **data-efficient**, **explainable** learning analytics layer on top of the existing
attempt logs, learner posterior (`topic_mastery`), and retention schedules.

## 1. Composite Score

We compute a scalar score per learner and scope (global or per-document):

\[
\text{FinalScore}=w_1\cdot\text{Knowledge}+w_2\cdot\text{Improvement}+w_3\cdot\text{Engagement}+w_4\cdot\text{Retention}.
\]

All terms are normalized to \([0,1]\).

### Knowledge

Let \(\hat K_t\) be the posterior topic mastery map (`topic_mastery`). Knowledge is the mean mastery across topics
in the scope:

\[
\text{Knowledge}=\frac{1}{|T|}\sum_{i\in T}\hat K_{t,i}.
\]

Fallback: latest exam score (if no posterior exists).

### Improvement

Let \(K_0\) be a baseline knowledge snapshot. Then improvement is a normalized gain:

\[
\text{Improvement}=\text{clip}\left(\frac{K_t-K_0}{\max(0.1,1-K_0)},0,1\right).
\]

### Engagement

Engagement is a convex combination of:

- session regularity (distinct active days)
- completion rate (attempts / quiz_sets created)
- time-on-task quality (heuristic based on seconds per question)

### Retention

Retention is computed from two components:

- empirical: mean ratio \(\text{score}/\text{baseline}\) over completed retention schedules
- model-based: predicted 7-day recall ratio using the fitted forgetting curve

\[
\text{Retention}=0.5\cdot\text{Empirical}+0.5\cdot\text{Predicted}_{7d}.
\]

## 2. Dropout Prediction (Explainable)

We estimate dropout risk via an interpretable logistic model:

\[
\Pr(\text{dropout})=\sigma(a_0+a_1x_{inactive}+a_2x_{lowEng}+a_3x_{fail}+a_4x_{stall}).
\]

Features are normalized to \([0,1]\):

- inactivity days since last attempt
- low engagement (1 - engagement)
- recent failures (<60% among last 5 attempts)
- learning stall (low/negative 7-day knowledge slope)

The service returns **drivers** sorted by contribution for dashboard explainability.

## 3. Persistence

The system stores computed analytics into `LearnerProfile.mastery_json`:

- `analytics`: latest composite metrics
- `analytics_history`: time-series of metrics for trend plots
- `topic_mastery_history`: small per-topic mastery series for slope estimation
- `analytics_weights`: user-configurable weights

## 4. API

- `GET /api/analytics/composite`
- `GET /api/analytics/dashboard`
- `POST /api/analytics/weights`

