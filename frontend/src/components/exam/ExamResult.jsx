import { useMemo } from "react";

const LEVEL_MAP = {
  gioi: { label: "Giỏi", color: "#16a34a" },
  kha: { label: "Khá", color: "#0284c7" },
  tb: { label: "Trung bình", color: "#f59e0b" },
  yeu: { label: "Yếu", color: "#dc2626" },
};

function normalizeLevel(rawLevel) {
  const key = String(rawLevel || "").toLowerCase();
  if (key.includes("giỏi") || key.includes("gioi")) return LEVEL_MAP.gioi;
  if (key.includes("khá") || key.includes("kha")) return LEVEL_MAP.kha;
  if (key.includes("trung") || key.includes("tb")) return LEVEL_MAP.tb;
  return LEVEL_MAP.yeu;
}

function TopicBars({ data }) {
  const max = Math.max(1, ...data.map((d) => d.score));

  return (
    <div style={{ display: "grid", gap: 8 }}>
      {data.map((item) => (
        <div key={item.name}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span>{item.name}</span>
            <strong>{item.score}</strong>
          </div>
          <div style={{ height: 10, borderRadius: 999, background: "#e2e8f0", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${(item.score / max) * 100}%`, background: "#2563eb" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function DifficultyBars({ data }) {
  const max = Math.max(1, ...data.map((d) => d.score));
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 10, alignItems: "end", minHeight: 180 }}>
      {data.map((item, idx) => (
        <div key={item.name} style={{ textAlign: "center" }}>
          <div style={{ fontSize: 12, marginBottom: 6 }}>{item.score}</div>
          <div style={{ height: 130, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
            <div
              style={{
                width: "60%",
                minWidth: 24,
                borderRadius: "6px 6px 0 0",
                background: ["#16a34a", "#0284c7", "#dc2626"][idx % 3],
                height: `${Math.max(8, (item.score / max) * 100)}%`,
              }}
            />
          </div>
          <div style={{ marginTop: 8, fontWeight: 600 }}>{item.name}</div>
        </div>
      ))}
    </div>
  );
}

export default function ExamResult({ result }) {
  const score = Number(result?.score_breakdown?.total_score ?? result?.total_score ?? 0);
  const level = normalizeLevel(result?.student_level);

  const topicData = useMemo(() => {
    return Object.entries(result?.score_breakdown?.topics || {}).map(([topic, value]) => ({
      name: topic,
      score: Number(value?.score ?? value ?? 0),
    }));
  }, [result]);

  const difficultyData = useMemo(() => {
    const diff = result?.score_breakdown?.difficulty || {};
    return [
      { name: "Easy", score: Number(diff.easy ?? 0) },
      { name: "Medium", score: Number(diff.medium ?? 0) },
      { name: "Hard", score: Number(diff.hard ?? 0) },
    ];
  }, [result]);

  const wrongAnswers = result?.score_breakdown?.wrong_answers || [];
  const recommendations = result?.recommendations || [];

  return (
    <div style={{ maxWidth: 1040, margin: "0 auto", padding: 16, display: "grid", gap: 14 }}>
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 16, background: "#fff" }}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
          <div>
            <div style={{ color: "#64748b", marginBottom: 6 }}>Điểm tổng</div>
            <div style={{ fontSize: 44, lineHeight: 1.1, fontWeight: 800, color: level.color }}>{score}</div>
          </div>
          <span
            style={{
              background: `${level.color}1a`,
              color: level.color,
              border: `1px solid ${level.color}66`,
              borderRadius: 999,
              padding: "8px 14px",
              fontWeight: 700,
            }}
          >
            {level.label}
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12 }}>
        <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, background: "#fff", minHeight: 240 }}>
          <h3 style={{ marginTop: 0 }}>Điểm theo topic</h3>
          <TopicBars data={topicData} />
        </div>

        <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, background: "#fff", minHeight: 240 }}>
          <h3 style={{ marginTop: 0 }}>Điểm theo độ khó</h3>
          <DifficultyBars data={difficultyData} />
        </div>
      </div>

      <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 14, background: "#fff" }}>
        <h3 style={{ marginTop: 0 }}>Câu sai cần xem lại</h3>
        {!wrongAnswers.length ? (
          <div style={{ color: "#64748b" }}>Không có câu sai.</div>
        ) : (
          <div style={{ display: "grid", gap: 8 }}>
            {wrongAnswers.map((item, index) => (
              <div key={item?.question_id || index} style={{ border: "1px solid #fee2e2", background: "#fff7f7", borderRadius: 10, padding: 10 }}>
                <div style={{ fontWeight: 700 }}>Câu {index + 1}: {item?.question || "(nội dung câu hỏi)"}</div>
                <div><strong>Đáp án đúng:</strong> {item?.correct_answer || "-"}</div>
                <div><strong>Giải thích:</strong> {item?.explanation || "Chưa có giải thích."}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 14, background: "#fff" }}>
        <h3 style={{ marginTop: 0 }}>Tài liệu và bài tập được gợi ý</h3>
        {!recommendations.length ? (
          <div style={{ color: "#64748b" }}>Chưa có gợi ý.</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
            {recommendations.map((item, idx) => (
              <li key={item?.id || idx}>
                <strong>{item?.title || item?.topic || "Nội dung"}</strong>
                {item?.reason ? <span style={{ color: "#475569" }}> — {item.reason}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
