import { useMemo, useState } from "react";
import { API_BASE } from "../lib/api";

const clamp = (n, min, max) => Math.max(min, Math.min(max, n));

export default function BatchExamGenerator({ classroomId, documentIds = [], topics = [] }) {
  const [title, setTitle] = useState("Đề kiểm tra in lớp");
  const [numPapers, setNumPapers] = useState(3);
  const [questionsPerPaper, setQuestionsPerPaper] = useState(20);
  const [mcqRatio, setMcqRatio] = useState(70);
  const [difficulty, setDifficulty] = useState({ easy: 30, medium: 40, hard: 30 });
  const [includeAnswerKey, setIncludeAnswerKey] = useState(true);
  const [paperCodeStyle, setPaperCodeStyle] = useState("ABC");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  const totalDifficulty = useMemo(() => difficulty.easy + difficulty.medium + difficulty.hard, [difficulty]);

  const updateDifficulty = (key, value) => {
    const next = { ...difficulty, [key]: clamp(Number(value) || 0, 0, 100) };
    const restKeys = ["easy", "medium", "hard"].filter((k) => k !== key);
    const restSum = restKeys.reduce((s, k) => s + next[k], 0);
    const targetRest = 100 - next[key];

    if (restSum <= 0) {
      next[restKeys[0]] = Math.max(0, targetRest);
      next[restKeys[1]] = 0;
    } else {
      next[restKeys[0]] = Math.round((next[restKeys[0]] / restSum) * targetRest);
      next[restKeys[1]] = targetRest - next[restKeys[0]];
    }
    setDifficulty(next);
  };

  const onGenerate = async () => {
    if (!classroomId) {
      setError("Vui lòng chọn lớp trước khi sinh đề.");
      return;
    }
    setError("");
    setDownloading(true);

    try {
      const url = `${API_BASE}/exams/batch-generate`;
      const headers = { "Content-Type": "application/json", "Cache-Control": "no-cache" };
      const uid = localStorage.getItem("user_id");
      const role = localStorage.getItem("role");
      if (uid) headers["X-User-Id"] = uid;
      if (role) headers["X-User-Role"] = role;

      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({
          classroom_id: Number(classroomId),
          title,
          document_ids: documentIds,
          topics,
          num_papers: Number(numPapers),
          questions_per_paper: Number(questionsPerPaper),
          mcq_ratio: Number(mcqRatio) / 100,
          difficulty_distribution: {
            easy: difficulty.easy / 100,
            medium: difficulty.medium / 100,
            hard: difficulty.hard / 100,
          },
          include_answer_key: includeAnswerKey,
          paper_code_style: paperCodeStyle,
        }),
      });

      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || "Sinh đề thất bại");
      }

      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `de_thi_batch_${classroomId}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(href);
    } catch (e) {
      setError(e?.message || "Không thể tạo file ZIP");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div style={{ marginTop: 12, background: "#fff", padding: 12, borderRadius: 12, border: "1px solid #e6f4ff" }}>
      <div style={{ fontWeight: 900, marginBottom: 10 }}>Sinh đề in (Word)</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10 }}>
        <label>
          Tiêu đề
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%", padding: 8 }} />
        </label>
        <label>
          Số đề
          <input type="number" min={1} max={10} value={numPapers} onChange={(e) => setNumPapers(clamp(e.target.value, 1, 10))} style={{ width: "100%", padding: 8 }} />
        </label>
        <label>
          Số câu / đề
          <input type="number" min={5} max={100} value={questionsPerPaper} onChange={(e) => setQuestionsPerPaper(clamp(e.target.value, 5, 100))} style={{ width: "100%", padding: 8 }} />
        </label>
        <label>
          Mã đề
          <select value={paperCodeStyle} onChange={(e) => setPaperCodeStyle(e.target.value)} style={{ width: "100%", padding: 8 }}>
            <option value="ABC">ABC (A/B/C...)</option>
            <option value="NUM">NUM (01/02...)</option>
          </select>
        </label>
      </div>

      <div style={{ marginTop: 10 }}>
        MCQ ratio: <b>{mcqRatio}%</b>
        <input type="range" min={0} max={100} value={mcqRatio} onChange={(e) => setMcqRatio(Number(e.target.value))} style={{ width: "100%" }} />
      </div>

      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 10 }}>
        {[
          ["easy", "Easy"],
          ["medium", "Medium"],
          ["hard", "Hard"],
        ].map(([k, label]) => (
          <label key={k}>
            {label}: <b>{difficulty[k]}%</b>
            <input type="range" min={0} max={100} value={difficulty[k]} onChange={(e) => updateDifficulty(k, e.target.value)} style={{ width: "100%" }} />
          </label>
        ))}
      </div>
      <div style={{ marginTop: 6, color: totalDifficulty === 100 ? "#389e0d" : "#cf1322" }}>Tổng phân bố độ khó: {totalDifficulty}%</div>

      <label style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8 }}>
        <input type="checkbox" checked={includeAnswerKey} onChange={(e) => setIncludeAnswerKey(e.target.checked)} />
        Kèm đáp án
      </label>

      <button onClick={onGenerate} disabled={downloading || totalDifficulty !== 100} style={{ marginTop: 12, padding: "10px 14px" }}>
        {downloading ? "Đang tạo ZIP..." : "Tạo & tải đề (ZIP)"}
      </button>

      {error ? <div style={{ marginTop: 10, color: "#cf1322" }}>{error}</div> : null}
    </div>
  );
}
