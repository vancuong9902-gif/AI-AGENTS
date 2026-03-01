import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Card from "../ui/Card";
import Banner from "../ui/Banner";
import Button from "../ui/Button";
import PageHeader from "../ui/PageHeader";
import { apiJson } from "../lib/api";

const DIFFICULTY_ORDER = ["easy", "medium", "hard"];
const PIE_COLORS = ["#6366f1", "#06b6d4", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#14b8a6", "#f97316"];

const LEVEL_META = {
  gioi: { label: "Giỏi", tone: "#15803d", bg: "#dcfce7" },
  kha: { label: "Khá", tone: "#1d4ed8", bg: "#dbeafe" },
  trung_binh: { label: "Trung bình", tone: "#b45309", bg: "#fef3c7" },
  yeu: { label: "Yếu", tone: "#b91c1c", bg: "#fee2e2" },
};

function clampPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  return Math.max(0, Math.min(100, Math.round(num)));
}

function classify(scorePercent) {
  const score = clampPercent(scorePercent);
  if (score >= 85) return "gioi";
  if (score >= 70) return "kha";
  if (score >= 50) return "trung_binh";
  return "yeu";
}

function normalizeSummary(result = {}) {
  const summary = result?.summary || {};
  const byTopicRaw = summary?.by_topic || {};
  const byDifficultyRaw = summary?.by_difficulty || {};

  const byTopic = Object.entries(byTopicRaw).map(([topic, stat]) => ({
    topic,
    earned: Number(stat?.earned || 0),
    total: Number(stat?.total || 0),
    percent: clampPercent(stat?.percent),
  }));

  const byDifficulty = DIFFICULTY_ORDER.map((difficulty) => {
    const stat = byDifficultyRaw[difficulty] || {};
    return {
      difficulty,
      earned: Number(stat?.earned || 0),
      total: Number(stat?.total || 0),
      percent: clampPercent(stat?.percent),
    };
  });

  return { byTopic, byDifficulty };
}

function difficultyLabel(value) {
  if (value === "easy") return "Dễ";
  if (value === "hard") return "Khó";
  return "Trung bình";
}

function buildWeakTopics(result, summaryByTopic) {
  if (Array.isArray(summaryByTopic) && summaryByTopic.length > 0) {
    return summaryByTopic
      .filter((item) => item.total > 0)
      .sort((a, b) => a.percent - b.percent)
      .slice(0, 5)
      .map((item) => item.topic);
  }

  const wrongMap = {};
  for (const row of result?.breakdown || []) {
    if (row?.is_correct) continue;
    const topic = String(row?.topic || "Chưa phân loại").trim() || "Chưa phân loại";
    wrongMap[topic] = (wrongMap[topic] || 0) + 1;
  }
  return Object.entries(wrongMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([topic]) => topic);
}

export default function Result() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const assessmentId = Number(searchParams.get("assessmentId") || location.state?.assessmentId || location.state?.assessment?.assessment_id || 0);
  const attemptId = Number(searchParams.get("attemptId") || location.state?.attemptId || location.state?.result?.attempt_id || 0);

  const [result, setResult] = useState(location.state?.result || null);
  const [assessment, setAssessment] = useState(location.state?.assessment || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const loadFallback = async () => {
      if (result || !assessmentId) return;
      setLoading(true);
      setError("");
      try {
        const meta = await apiJson(`/assessments/${assessmentId}`, { method: "GET" });
        if (!cancelled) {
          setAssessment(meta || null);
          setError("Không tìm thấy dữ liệu kết quả trong state. Hãy mở trang này ngay sau khi nộp bài.");
        }
      } catch (e) {
        if (!cancelled) {
          setError(e?.message || "Không tải được thông tin bài assessment.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadFallback();
    return () => {
      cancelled = true;
    };
  }, [assessmentId, result]);

  const scorePercent = clampPercent(result?.total_score_percent ?? result?.score_percent ?? 0);
  const levelKey = classify(scorePercent);
  const level = LEVEL_META[levelKey];

  const summary = useMemo(() => normalizeSummary(result || {}), [result]);
  const weakTopics = useMemo(() => buildWeakTopics(result || {}, summary.byTopic), [result, summary.byTopic]);

  const handleLearningPath = () => {
    navigate("/learning-path", { state: { weak_topics: weakTopics } });
  };

  if (!result) {
    return (
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: 16, display: "grid", gap: 12 }}>
        <PageHeader title="Kết quả assessment" subtitle="Không có dữ liệu kết quả để hiển thị." />
        {error ? <Banner tone="warning">{error}</Banner> : null}
        {loading ? <Banner>Đang tải thông tin assessment…</Banner> : null}
        {assessment ? (
          <Card style={{ padding: 14 }}>
            <div><b>Bài:</b> {assessment?.title || assessment?.topic || `Assessment #${assessmentId}`}</div>
            {attemptId > 0 ? <div><b>Attempt:</b> #{attemptId}</div> : null}
          </Card>
        ) : null}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link to="/assessments"><Button>Quay lại assessments</Button></Link>
          <Link to="/learning-path"><Button variant="primary">Đến lộ trình học</Button></Link>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1080, margin: "0 auto", padding: 16, display: "grid", gap: 16 }}>
      <PageHeader title="Kết quả assessment" subtitle={assessment?.title || assessment?.topic || "Tổng hợp chi tiết bài làm"} />

      <Card style={{ padding: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "#64748b" }}>Điểm tổng</div>
            <div style={{ fontWeight: 800, fontSize: 34 }}>{result?.score_points ?? 0}/{result?.max_points ?? 0}</div>
            <div style={{ marginTop: 6, fontSize: 20, fontWeight: 700 }}>{scorePercent}%</div>
          </div>
          <span style={{ padding: "6px 12px", borderRadius: 999, background: level.bg, color: level.tone, fontWeight: 700 }}>
            Xếp loại: {level.label}
          </span>
        </div>
      </Card>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        <Card style={{ padding: 16, minHeight: 320 }}>
          <h3 style={{ margin: "0 0 12px" }}>Tỷ lệ theo topic</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={summary.byTopic} dataKey="percent" nameKey="topic" outerRadius={95} label={({ percent }) => `${percent}%`}>
                {summary.byTopic.map((entry, index) => (
                  <Cell key={`${entry.topic}-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value, _name, row) => [`${value}%`, `${row?.payload?.topic || "Topic"}`]} />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        <Card style={{ padding: 16, minHeight: 320 }}>
          <h3 style={{ margin: "0 0 12px" }}>Điểm theo độ khó</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={summary.byDifficulty}>
              <XAxis dataKey="difficulty" tickFormatter={difficultyLabel} />
              <YAxis domain={[0, 100]} />
              <Tooltip formatter={(value) => [`${value}%`, "Tỷ lệ đúng"]} labelFormatter={difficultyLabel} />
              <Bar dataKey="percent" fill="#4f46e5" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card style={{ padding: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>Chi tiết từng câu</h3>
          <Button variant="primary" onClick={handleLearningPath}>Ôn luyện ngay</Button>
        </div>
        <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
          {(result?.breakdown || []).map((item, idx) => {
            const isCorrect = Boolean(item?.is_correct);
            const cardBg = isCorrect ? "#f0fdf4" : "#fef2f2";
            const borderColor = isCorrect ? "#86efac" : "#fca5a5";
            const studentAnswer = item?.student_answer_text ?? item?.answer_text ?? "(không trả lời)";
            return (
              <details key={item?.question_id || idx} style={{ border: `1px solid ${borderColor}`, background: cardBg, borderRadius: 10, padding: 10 }}>
                <summary style={{ cursor: "pointer", fontWeight: 700 }}>
                  {isCorrect ? "✓" : "✗"} Câu {idx + 1}: {item?.stem || `Câu hỏi #${item?.question_id}`}
                </summary>
                <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
                  <div><b>Chủ đề:</b> {item?.topic || "Chưa phân loại"} • <b>Độ khó:</b> {difficultyLabel(item?.difficulty)}</div>
                  {Array.isArray(item?.options) && item.options.length > 0 ? (
                    <div>
                      <b>Lựa chọn:</b>
                      <ul style={{ margin: "6px 0 0 16px" }}>
                        {item.options.map((opt, optionIdx) => <li key={`${item.question_id}-opt-${optionIdx}`}>{opt}</li>)}
                      </ul>
                    </div>
                  ) : null}
                  <div><b>Đáp án học sinh:</b> {studentAnswer}</div>
                  <div><b>Đáp án đúng:</b> {item?.correct_answer_text || item?.correct}</div>
                  {!isCorrect ? <div><b>Giải thích:</b> {item?.explanation || "Chưa có giải thích."}</div> : null}
                  {!isCorrect && Array.isArray(item?.sources) && item.sources.length > 0 ? (
                    <div>
                      <b>Nguồn:</b> {item.sources.map((s, sIdx) => `#${s?.chunk_id ?? sIdx + 1}`).join(", ")}
                    </div>
                  ) : null}
                </div>
              </details>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
