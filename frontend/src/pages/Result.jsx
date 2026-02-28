import { Link, useLocation, useNavigate } from "react-router-dom";
import Card from "../ui/Card";
import Banner from "../ui/Banner";
import Button from "../ui/Button";
import PageHeader from "../ui/PageHeader";

const DIFFICULTIES = ["easy", "medium", "hard"];

const TYPE_META = {
  entry: { title: "Kết quả bài kiểm tra đầu vào", subtitle: "Tổng hợp năng lực hiện tại của bạn." },
  final: { title: "Kết quả bài kiểm tra cuối kỳ", subtitle: "Đánh giá tổng thể sau quá trình học." },
  assessment: { title: "Kết quả bài assessment", subtitle: "Xem điểm số và các phần cần cải thiện." },
  homework: { title: "Kết quả bài tập", subtitle: "Phân tích nhanh theo độ khó và chủ đề." },
};

const LEVEL_META = {
  gioi: { label: "Giỏi", tone: "#15803d", bg: "#dcfce7" },
  kha: { label: "Khá", tone: "#1d4ed8", bg: "#dbeafe" },
  trung_binh: { label: "Trung bình", tone: "#b45309", bg: "#fef3c7" },
  yeu: { label: "Yếu", tone: "#b91c1c", bg: "#fee2e2" },
};

function toNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Math.round(toNumber(value, 0))));
}

function mapType(rawType) {
  const value = String(rawType || "").toLowerCase();
  if (["entry", "diagnostic", "diagnostic_pre"].includes(value)) return "entry";
  if (["final", "final_exam"].includes(value)) return "final";
  if (value === "homework") return "homework";
  return "assessment";
}

function deriveClassification(scorePercent, classificationRaw) {
  const normalized = String(classificationRaw || "").toLowerCase();
  if (["gioi", "excellent", "high"].includes(normalized)) return "gioi";
  if (["kha", "good", "medium_high"].includes(normalized)) return "kha";
  if (["trung_binh", "average", "medium"].includes(normalized)) return "trung_binh";
  if (["yeu", "weak", "low"].includes(normalized)) return "yeu";

  const score = clampPercent(scorePercent);
  if (score >= 85) return "gioi";
  if (score >= 70) return "kha";
  if (score >= 50) return "trung_binh";
  return "yeu";
}

function normalizeDifficultyBucket(raw) {
  const total = toNumber(raw?.total ?? raw?.count ?? 0, 0);
  const correct = toNumber(raw?.correct ?? raw?.correct_count ?? 0, 0);
  const pctFromCorrect = total > 0 ? (correct / total) * 100 : 0;
  const pct = clampPercent(raw?.percentage ?? raw?.percent ?? raw?.score_percent ?? pctFromCorrect);
  return { total, correct, percentage: pct };
}

function aggregateFromBreakdown(breakdown) {
  const byDifficulty = {
    easy: { total: 0, correct: 0 },
    medium: { total: 0, correct: 0 },
    hard: { total: 0, correct: 0 },
  };
  const byTopic = {};

  (Array.isArray(breakdown) ? breakdown : []).forEach((row) => {
    const difficulty = String(row?.difficulty || "medium").toLowerCase();
    const key = DIFFICULTIES.includes(difficulty) ? difficulty : "medium";
    const isCorrect = Boolean(row?.is_correct);

    byDifficulty[key].total += 1;
    if (isCorrect) byDifficulty[key].correct += 1;

    const topic = String(row?.topic || row?.topic_name || "Chưa phân loại").trim() || "Chưa phân loại";
    if (!byTopic[topic]) byTopic[topic] = { total: 0, correct: 0, wrong: 0 };
    byTopic[topic].total += 1;
    if (isCorrect) byTopic[topic].correct += 1;
    else byTopic[topic].wrong += 1;
  });

  return { byDifficulty, byTopic };
}

function normalizeResult(result) {
  const scorePercent = clampPercent(result?.total_score_percent ?? result?.score_percent ?? 0);
  const derived = aggregateFromBreakdown(result?.breakdown);
  const apiDiff = result?.score_breakdown?.by_difficulty || result?.breakdown_by_difficulty || {};
  const apiTopic = result?.score_breakdown?.by_topic || result?.breakdown_by_topic || {};

  const byDifficulty = {};
  DIFFICULTIES.forEach((difficulty) => {
    byDifficulty[difficulty] = normalizeDifficultyBucket(apiDiff[difficulty] || derived.byDifficulty[difficulty]);
  });

  const topicEntries = Object.entries(
    Array.isArray(apiTopic)
      ? apiTopic.reduce((acc, item) => {
          const name = String(item?.topic || item?.topic_name || item?.name || "Chưa phân loại").trim() || "Chưa phân loại";
          acc[name] = item;
          return acc;
        }, {})
      : apiTopic,
  ).map(([topic, value]) => {
    const total = toNumber(value?.total ?? value?.count ?? derived.byTopic[topic]?.total ?? 0, 0);
    const correct = toNumber(value?.correct ?? value?.correct_count ?? derived.byTopic[topic]?.correct ?? 0, 0);
    const wrong = toNumber(value?.wrong ?? value?.incorrect ?? Math.max(0, total - correct), 0);
    const percentage = clampPercent(
      value?.percentage ?? value?.percent ?? value?.score_percent ?? (total > 0 ? (correct / total) * 100 : 0),
    );
    return { topic, total, correct, wrong, percentage };
  });

  const fallbackTopicEntries = Object.entries(derived.byTopic).map(([topic, stats]) => ({
    topic,
    total: stats.total,
    correct: stats.correct,
    wrong: stats.wrong,
    percentage: clampPercent(stats.total > 0 ? (stats.correct / stats.total) * 100 : 0),
  }));

  const topics = (topicEntries.length ? topicEntries : fallbackTopicEntries)
    .sort((a, b) => a.percentage - b.percentage)
    .slice(0, 8);

  const recommendations = Array.isArray(result?.recommendations)
    ? result.recommendations
    : Array.isArray(result?.recommendations?.items)
      ? result.recommendations.items
      : result?.ai_recommendation
        ? [result.ai_recommendation]
        : [];

  return {
    scorePercent,
    mcqScorePercent: result?.mcq_score_percent,
    essayScorePercent: result?.essay_score_percent,
    classification: deriveClassification(scorePercent, result?.classification),
    timedOut: Boolean(result?.timed_out || result?.autoSubmitted),
    byDifficulty,
    weakTopics: topics,
    recommendations,
  };
}

function ProgressRing({ score }) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clampPercent(score) / 100) * circumference;
  return (
    <svg width="120" height="120" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r={radius} stroke="#e2e8f0" strokeWidth="10" fill="none" />
      <circle
        cx="60"
        cy="60"
        r={radius}
        stroke="#4f46e5"
        strokeWidth="10"
        fill="none"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform="rotate(-90 60 60)"
      />
      <text x="60" y="66" textAnchor="middle" fontSize="20" fontWeight="700" fill="#0f172a">
        {clampPercent(score)}%
      </text>
    </svg>
  );
}

export default function Result() {
  const location = useLocation();
  const navigate = useNavigate();

  const state = location.state || {};
  const resultRaw = state?.result || state?.quizResult || null;
  const resolvedType = mapType(state?.type || state?.quizType);
  const header = TYPE_META[resolvedType] || TYPE_META.assessment;

  if (!resultRaw) {
    return (
      <div style={{ maxWidth: 980, margin: "0 auto", padding: 16, display: "grid", gap: 12 }}>
        <PageHeader title="Kết quả" subtitle="Không tìm thấy dữ liệu kết quả trong phiên hiện tại." />
        <Banner tone="warning">Bạn vừa refresh trang hoặc truy cập trực tiếp nên state kết quả đã mất.</Banner>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link to="/quiz"><Button>Làm quiz</Button></Link>
          <Link to="/assessments"><Button>Bài assessments</Button></Link>
          <Link to="/learning-path"><Button variant="primary">Đến lộ trình học</Button></Link>
        </div>
      </div>
    );
  }

  const normalized = normalizeResult(resultRaw);
  const level = LEVEL_META[normalized.classification] || LEVEL_META.trung_binh;
  const weakestTopicName = normalized.weakTopics[0]?.topic || "Nền tảng";

  const gotoTutor = () => {
    localStorage.setItem("tutor_topic_prefill", weakestTopicName);
    navigate("/tutor");
  };

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16, display: "grid", gap: 16 }}>
      <PageHeader title={header.title} subtitle={header.subtitle} breadcrumbs={["Học sinh", "Kết quả"]} />

      {normalized.timedOut && <Banner tone="warning">⏱ Hết thời gian làm bài. Hệ thống đã tự nộp bài.</Banner>}

      <Card className="stack" style={{ padding: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 14, color: "#64748b" }}>Điểm tổng</div>
            <div style={{ fontSize: 34, fontWeight: 800 }}>{normalized.scorePercent}%</div>
            <div style={{ marginTop: 8, width: 220, height: 10, borderRadius: 999, background: "#e2e8f0", overflow: "hidden" }}>
              <div style={{ width: `${normalized.scorePercent}%`, background: "#4f46e5", height: "100%" }} />
            </div>
          </div>
          <ProgressRing score={normalized.scorePercent} />
        </div>
        {(normalized.mcqScorePercent != null || normalized.essayScorePercent != null) && (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {normalized.mcqScorePercent != null && <span>MCQ: <b>{clampPercent(normalized.mcqScorePercent)}%</b></span>}
            {normalized.essayScorePercent != null && <span>Essay: <b>{clampPercent(normalized.essayScorePercent)}%</b></span>}
          </div>
        )}
      </Card>

      <Card style={{ padding: 16 }}>
        <span style={{ padding: "4px 12px", borderRadius: 999, background: level.bg, color: level.tone, fontWeight: 700 }}>
          Phân loại: {level.label}
        </span>
      </Card>

      <Card style={{ padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>Breakdown theo độ khó</h3>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
              <th style={{ padding: "8px 4px" }}>Độ khó</th>
              <th style={{ padding: "8px 4px" }}>Đúng/Tổng</th>
              <th style={{ padding: "8px 4px" }}>Tỷ lệ</th>
            </tr>
          </thead>
          <tbody>
            {DIFFICULTIES.map((difficulty) => {
              const row = normalized.byDifficulty[difficulty];
              const label = difficulty === "easy" ? "Dễ" : difficulty === "medium" ? "Trung bình" : "Khó";
              return (
                <tr key={difficulty} style={{ borderBottom: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "10px 4px" }}>{label}</td>
                  <td style={{ padding: "10px 4px" }}>{row.correct}/{row.total}</td>
                  <td style={{ padding: "10px 4px" }}>{row.percentage}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <Card style={{ padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>Topic yếu nhất (top 8)</h3>
        {normalized.weakTopics.length ? (
          <div style={{ display: "grid", gap: 8 }}>
            {normalized.weakTopics.map((topic) => (
              <div key={topic.topic} style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #f1f5f9", paddingBottom: 6 }}>
                <span>{topic.topic}</span>
                <span><b>{topic.percentage}%</b> ({topic.correct}/{topic.total})</span>
              </div>
            ))}
          </div>
        ) : (
          <p>Chưa có dữ liệu theo topic.</p>
        )}
      </Card>

      {normalized.recommendations.length > 0 && (
        <Card style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Gợi ý học tập</h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {normalized.recommendations.map((item, idx) => (
              <li key={`rec-${idx}`}>{typeof item === "string" ? item : item?.text || item?.title || JSON.stringify(item)}</li>
            ))}
          </ul>
        </Card>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link to="/learning-path"><Button variant="primary">Đi đến lộ trình học</Button></Link>
        <Button onClick={gotoTutor}>Học với AI Tutor theo topic yếu nhất</Button>
      </div>
    </div>
  );
}
