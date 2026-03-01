import { Link, useNavigate, useParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Bar,
} from "recharts";

import Card from "../ui/Card";
import Banner from "../ui/Banner";
import Button from "../ui/Button";
import PageHeader from "../ui/PageHeader";
import { Accordion, AccordionItem } from "../ui/Accordion";
import { apiJson } from "../lib/api";

const DIFFICULTY_LABELS = {
  easy: "Dễ",
  medium: "Trung bình",
  hard: "Khó",
};

const PIE_COLORS = ["#6366f1", "#14b8a6", "#f59e0b", "#ef4444", "#8b5cf6", "#0ea5e9"];

function asNumber(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function levelTone(levelKey) {
  const key = String(levelKey || "").toLowerCase();
  if (key === "gioi") return { label: "Giỏi", bg: "#dcfce7", fg: "#15803d" };
  if (key === "kha") return { label: "Khá", bg: "#dbeafe", fg: "#1d4ed8" };
  if (key === "trung_binh") return { label: "Trung bình", bg: "#fef3c7", fg: "#b45309" };
  return { label: "Yếu", bg: "#fee2e2", fg: "#b91c1c" };
}

export default function Result() {
  const { attemptId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    let mounted = true;
    async function loadResult() {
      if (!attemptId) {
        setError("Thiếu attemptId trong URL.");
        setLoading(false);
        return;
      }
      setLoading(true);
      setError("");
      try {
        const data = await apiJson(`/attempts/${encodeURIComponent(attemptId)}/result`);
        if (!mounted) return;
        setDetail(data?.result_detail || null);
      } catch (e) {
        if (!mounted) return;
        setError(e?.message || "Không thể tải kết quả.");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadResult();
    return () => {
      mounted = false;
    };
  }, [attemptId]);

  const topicChartData = useMemo(() => {
    const rows = detail?.summary?.by_topic || {};
    return Object.entries(rows)
      .map(([topic, value]) => ({
        name: topic,
        percent: asNumber(value?.percent, 0),
      }))
      .sort((a, b) => b.percent - a.percent)
      .slice(0, 8);
  }, [detail]);

  const difficultyChartData = useMemo(() => {
    const rows = detail?.summary?.by_difficulty || {};
    return ["easy", "medium", "hard"].map((key) => ({
      key,
      name: DIFFICULTY_LABELS[key],
      percent: asNumber(rows?.[key]?.percent, 0),
      earned: asNumber(rows?.[key]?.earned, 0),
      total: asNumber(rows?.[key]?.total, 0),
    }));
  }, [detail]);

  const weakestTopic = topicChartData?.[topicChartData.length - 1]?.name || "nội dung vừa làm";
  const level = levelTone(detail?.classification);

  if (loading) {
    return (
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
        <PageHeader title="Kết quả" subtitle="Đang tải kết quả bài làm..." />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16, display: "grid", gap: 12 }}>
        <PageHeader title="Kết quả" subtitle="Không thể hiển thị chi tiết kết quả." />
        <Banner tone="warning">{error || "Không có dữ liệu kết quả."}</Banner>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link to="/quiz"><Button>Làm quiz</Button></Link>
          <Link to="/assessments"><Button>Bài assessments</Button></Link>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16, display: "grid", gap: 16 }}>
      <PageHeader
        title={`Kết quả: ${detail.quiz_title || `Quiz #${detail.quiz_id}`}`}
        subtitle={`Điểm ${Math.round(asNumber(detail.total_score_percent, detail.score_percent))}% · ${detail.level_label || level.label}`}
        breadcrumbs={["Học sinh", "Kết quả"]}
      />

      {detail.timed_out && <Banner tone="warning">⏱ Bài làm đã quá thời gian cho phép, hệ thống ghi nhận là nộp trễ.</Banner>}

      <Card style={{ padding: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "#64748b", fontSize: 14 }}>Điểm tổng</div>
            <div style={{ fontSize: 36, fontWeight: 800 }}>{Math.round(asNumber(detail.total_score_percent, detail.score_percent))}%</div>
            <div style={{ color: "#334155" }}>
              {asNumber(detail.score_points, 0)} / {asNumber(detail.max_points, 0)} điểm
            </div>
          </div>
          <span style={{ padding: "6px 12px", borderRadius: 999, fontWeight: 700, background: level.bg, color: level.fg }}>
            Level: {detail.level_label || level.label}
          </span>
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
        <Card style={{ padding: 16, minHeight: 320 }}>
          <h3 style={{ marginTop: 0 }}>Phân bố theo chủ đề</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={topicChartData} dataKey="percent" nameKey="name" outerRadius={95} label={(v) => `${v.name}: ${Math.round(v.percent)}%`}>
                {topicChartData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        <Card style={{ padding: 16, minHeight: 320 }}>
          <h3 style={{ marginTop: 0 }}>Kết quả theo độ khó</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={difficultyChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis domain={[0, 100]} />
              <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
              <Bar dataKey="percent" fill="#4f46e5" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card style={{ padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>Chi tiết từng câu</h3>
        <Accordion>
          {(Array.isArray(detail.questions_detail) ? detail.questions_detail : []).map((q, idx) => {
            const selectedIdx = q.student_answer_idx;
            const correctIdx = q.correct_answer_idx;
            const isMcq = String(q.type || "").toLowerCase() === "mcq";
            return (
              <AccordionItem
                key={q.question_id || idx}
                defaultOpen={idx === 0}
                title={`Câu ${q.order_no || idx + 1}: ${q.question_text || ""}`}
                right={q.is_correct == null ? "Tự luận" : q.is_correct ? "✅ Đúng" : "❌ Sai"}
              >
                <div style={{ display: "grid", gap: 8 }}>
                  <div style={{ fontSize: 13, color: "#64748b" }}>
                    Topic: <b>{q.topic || "N/A"}</b> · Bloom: <b>{q.bloom_level || "understand"}</b> · Difficulty: <b>{DIFFICULTY_LABELS[q.difficulty] || q.difficulty}</b>
                  </div>

                  {isMcq ? (
                    <div style={{ display: "grid", gap: 6 }}>
                      {(Array.isArray(q.options) ? q.options : []).map((opt, optIdx) => {
                        const isSelected = selectedIdx === optIdx;
                        const isCorrect = correctIdx === optIdx;
                        const bg = isCorrect ? "#dcfce7" : isSelected ? "#fee2e2" : "#f8fafc";
                        const border = isCorrect ? "1px solid #16a34a" : isSelected ? "1px solid #dc2626" : "1px solid #e2e8f0";
                        return (
                          <div key={optIdx} style={{ padding: "8px 10px", borderRadius: 10, background: bg, border }}>
                            <b>{String.fromCharCode(65 + optIdx)}.</b> {opt}
                            {isSelected && <span style={{ marginLeft: 8 }}>(Bạn chọn)</span>}
                            {isCorrect && <span style={{ marginLeft: 8 }}>(Đáp án đúng)</span>}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ display: "grid", gap: 6 }}>
                      <div><b>Bài làm của bạn:</b> {q.student_answer_text || "(Không có nội dung)"}</div>
                      <div><b>Điểm:</b> {q.score_earned}/{q.score_max}</div>
                    </div>
                  )}

                  {q.explanation && (
                    <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", padding: 10, borderRadius: 10 }}>
                      <b>Giải thích:</b> {q.explanation}
                    </div>
                  )}

                  {Array.isArray(q.sources) && q.sources.length > 0 && (
                    <div style={{ fontSize: 13, color: "#334155" }}>
                      <b>Nguồn tham chiếu:</b>
                      <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                        {q.sources.map((s, sourceIdx) => (
                          <li key={sourceIdx}>chunk_id: {s?.chunk_id ?? "N/A"}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </AccordionItem>
            );
          })}
        </Accordion>
      </Card>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link to="/learning-path"><Button variant="primary">Đi tới Learning Path</Button></Link>
        <Button
          onClick={() => {
            localStorage.setItem("tutor_topic_prefill", weakestTopic);
            navigate("/tutor");
          }}
        >
          Hỏi Tutor
        </Button>
      </div>
    </div>
  );
}
