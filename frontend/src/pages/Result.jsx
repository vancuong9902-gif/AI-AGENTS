import { Link, useLocation } from "react-router-dom";

function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds || 0)));
  const minutes = Math.floor(total / 60);
  const sec = total % 60;
  return `${minutes} phút ${sec} giây`;
}

function percent(value) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? Math.max(0, Math.min(100, num)) : 0;
}

const CLASS_THEME = {
  gioi: {
    hero: "linear-gradient(135deg, #15803d, #22c55e)",
    stars: "⭐⭐⭐",
  },
  kha: {
    hero: "linear-gradient(135deg, #1d4ed8, #38bdf8)",
    stars: "⭐⭐",
  },
  trung_binh: {
    hero: "linear-gradient(135deg, #d97706, #fb923c)",
    stars: "⭐",
  },
  yeu: {
    hero: "linear-gradient(135deg, #ef4444, #fda4af)",
    stars: "⭐",
  },
};

function DifficultyCard({ label, item }) {
  const p = percent(item?.percentage);
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, background: "#fff" }}>
      <div style={{ fontWeight: 700 }}>{label}</div>
      <div style={{ marginTop: 6, fontSize: 22, fontWeight: 800 }}>{item?.correct || 0}/{item?.total || 0}</div>
      <div style={{ marginTop: 8, height: 8, background: "#e5e7eb", borderRadius: 999, overflow: "hidden" }}>
        <div style={{ width: `${p}%`, height: "100%", background: "#4f46e5" }} />
      </div>
      <div style={{ marginTop: 6, fontSize: 13, color: "#475569" }}>{p}%</div>
    </div>
  );
}

export default function Result({ result: propResult, quizType: propQuizType = "diagnostic", diagnosticScore: propDiagnosticScore }) {
  const { state } = useLocation();
  const result = propResult || state?.quizResult || null;
  const quizType = propQuizType || state?.quizType || "diagnostic";
  const diagnosticScore = Number(propDiagnosticScore ?? state?.diagnosticScore ?? 0);

  if (!result) {
    return <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>Không có dữ liệu kết quả.</div>;
  }

  const classification = String(result.classification || "trung_binh").toLowerCase();
  const theme = CLASS_THEME[classification] || CLASS_THEME.trung_binh;
  const scorePct = percent(result.percentage);
  const byDiff = result.breakdown_by_difficulty || {};
  const topics = Array.isArray(result.breakdown_by_topic) ? result.breakdown_by_topic : [];
  const finalImprovement = Number(result.improvement_vs_diagnostic || 0);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16, display: "grid", gap: 16 }}>
      <section style={{ background: theme.hero, color: "white", borderRadius: 16, padding: 20 }}>
        <div style={{ fontSize: 34, fontWeight: 900 }}>🎯 {result.score} / {result.max_score}</div>
        <div style={{ marginTop: 12, height: 12, background: "rgba(255,255,255,0.4)", borderRadius: 999, overflow: "hidden" }}>
          <div style={{ width: `${scorePct}%`, height: "100%", background: "#fff" }} />
        </div>
        <div style={{ marginTop: 8, fontWeight: 700 }}>{scorePct}%</div>
        <div style={{ marginTop: 8, fontSize: 18, fontWeight: 700 }}>
          Phân loại: {String(result.classification_label || "").toUpperCase()} {theme.stars}
        </div>
        <div style={{ marginTop: 6, opacity: 0.95 }}>Thời gian: {formatDuration(result.time_taken_seconds)}</div>
      </section>

      <section>
        <h3>Độ khó</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
          <DifficultyCard label="Dễ" item={byDiff.easy} />
          <DifficultyCard label="Trung bình" item={byDiff.medium} />
          <DifficultyCard label="Khó" item={byDiff.hard} />
        </div>
      </section>

      <section>
        <h3>Theo topic</h3>
        <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, overflow: "hidden", background: "#fff" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead style={{ background: "#f8fafc" }}>
              <tr>
                <th style={{ textAlign: "left", padding: 10 }}>Topic</th>
                <th style={{ textAlign: "left", padding: 10 }}>Điểm</th>
                <th style={{ textAlign: "left", padding: 10 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {topics.map((t) => {
                const p = percent(t.percentage);
                const weak = p < 50 || t.weak;
                const strong = p >= 80;
                return (
                  <tr key={t.topic} style={{ background: weak ? "#fef2f2" : "#fff", borderTop: "1px solid #f1f5f9" }}>
                    <td style={{ padding: 10 }}>{t.topic}</td>
                    <td style={{ padding: 10 }}>{t.correct}/{t.total} ({p}%)</td>
                    <td style={{ padding: 10 }}>
                      {weak && <span style={{ background: "#fee2e2", color: "#b91c1c", borderRadius: 999, padding: "3px 10px", fontSize: 12 }}>Cần ôn thêm</span>}
                      {strong && <span style={{ background: "#dcfce7", color: "#15803d", borderRadius: 999, padding: "3px 10px", fontSize: 12 }}>Đã nắm vững</span>}
                      {!weak && !strong && <span style={{ color: "#64748b" }}>Đang tiến bộ</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {quizType === "final" && (
        <section style={{ border: "1px solid #bfdbfe", background: "#eff6ff", borderRadius: 14, padding: 16 }}>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>📈 Tiến bộ của bạn</div>
          <div>Đầu vào: {diagnosticScore}% → Cuối kỳ: {scorePct}%</div>
          <div style={{ marginTop: 4, fontWeight: 700 }}>Cải thiện: {finalImprovement >= 0 ? "+" : ""}{finalImprovement}% 🚀</div>
        </section>
      )}

      <section style={{ border: "1px solid #ddd6fe", background: "#f5f3ff", borderRadius: 14, padding: 16 }}>
        <div style={{ fontWeight: 800 }}>💡 AI đề xuất cho bạn:</div>
        <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{result.ai_recommendation}</div>
      </section>

      <section style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {quizType === "diagnostic" ? (
          <>
            <Link to="/learning-path"><button style={{ padding: "10px 14px", fontWeight: 700 }}>Xem lộ trình học cá nhân hóa →</button></Link>
            <Link to="/assessments"><button style={{ padding: "10px 14px" }}>Làm lại bài kiểm tra</button></Link>
          </>
        ) : (
          <>
            <button style={{ padding: "10px 14px", fontWeight: 700 }}>Xem báo cáo đầy đủ</button>
            <button style={{ padding: "10px 14px" }}>Chia sẻ kết quả</button>
          </>
        )}
      </section>
    </div>
  );
}
