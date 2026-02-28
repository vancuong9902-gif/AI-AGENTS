import { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../../lib/api";

function getQuestionId(question, index) {
  return question?.id ?? question?.question_id ?? `hw-q-${index}`;
}

export default function TopicHomework({ topicId, topicTitle, studentLevel }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [homework, setHomework] = useState(null);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const generateHomework = useCallback(async () => {
    if (!topicId) return;

    setLoading(true);
    setError("");
    setResult(null);
    setAnswers({});

    try {
      const res = await apiJson("/homework/generate", {
        method: "POST",
        body: {
          topic_id: topicId,
          topic: topicTitle,
          student_level: studentLevel,
        },
      });
      setHomework(res);
    } catch (e) {
      setError(e?.message || "Không tạo được bài tập");
    } finally {
      setLoading(false);
    }
  }, [studentLevel, topicId, topicTitle]);

  useEffect(() => {
    generateHomework();
  }, [generateHomework]);

  const questions = useMemo(() => {
    const list = homework?.questions || homework?.items || [];
    return Array.isArray(list) ? list : [];
  }, [homework]);

  const setMcqAnswer = (qid, answerIndex) => {
    setAnswers((prev) => ({ ...prev, [qid]: { ...(prev[qid] || {}), answer_index: answerIndex } }));
  };

  const setEssayAnswer = (qid, text) => {
    setAnswers((prev) => ({ ...prev, [qid]: { ...(prev[qid] || {}), answer_text: text } }));
  };

  const submitHomework = async () => {
    setSubmitting(true);
    setError("");

    try {
      const answerList = questions.map((question, index) => {
        const qid = getQuestionId(question, index);
        return {
          question_id: qid,
          answer_index: answers[qid]?.answer_index ?? null,
          answer_text: answers[qid]?.answer_text ?? null,
        };
      });

      const res = await apiJson("/homework/submit", {
        method: "POST",
        body: {
          homework_id: homework?.homework_id,
          topic_id: topicId,
          answers: answerList,
        },
      });
      setResult(res);
    } catch (e) {
      setError(e?.message || "Nộp bài thất bại");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 14, background: "#fff" }}>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Bài tập: {topicTitle || "Theo topic"}</h3>
        <button type="button" onClick={generateHomework} style={{ border: "1px solid #cbd5e1", borderRadius: 8, background: "#fff", padding: "6px 10px" }}>
          Tạo lại
        </button>
      </div>

      {loading && <div style={{ marginTop: 10 }}>Đang tạo bài tập...</div>}
      {error && <div style={{ marginTop: 10, color: "#dc2626" }}>{error}</div>}

      {!loading && !questions.length && <div style={{ marginTop: 10, color: "#64748b" }}>Chưa có câu hỏi.</div>}

      <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
        {questions.map((question, index) => {
          const qid = getQuestionId(question, index);
          const options = Array.isArray(question?.options) ? question.options : [];

          return (
            <div key={qid} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 12 }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>
                Câu {index + 1} ({question?.type === "essay" ? "Tự luận" : "MCQ"}): {question?.question || question?.content}
              </div>

              {question?.type === "essay" ? (
                <textarea
                  rows={4}
                  value={answers[qid]?.answer_text || ""}
                  onChange={(e) => setEssayAnswer(qid, e.target.value)}
                  style={{ width: "100%", border: "1px solid #cbd5e1", borderRadius: 8, padding: 10 }}
                />
              ) : (
                <div style={{ display: "grid", gap: 6 }}>
                  {(options.length ? options : ["A", "B", "C", "D"]).slice(0, 4).map((option, optionIndex) => (
                    <label key={`${qid}-${optionIndex}`} style={{ display: "flex", gap: 8 }}>
                      <input
                        type="radio"
                        name={`homework-${qid}`}
                        checked={answers[qid]?.answer_index === optionIndex}
                        onChange={() => setMcqAnswer(qid, optionIndex)}
                      />
                      <span>{option?.text || option?.label || option}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {questions.length > 0 && (
        <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={submitHomework}
            disabled={submitting}
            style={{ border: 0, borderRadius: 8, padding: "10px 14px", color: "#fff", background: "#2563eb" }}
          >
            {submitting ? "Đang nộp..." : "Nộp bài"}
          </button>
        </div>
      )}

      {result && (
        <div style={{ marginTop: 12, border: "1px solid #bbf7d0", background: "#f0fdf4", borderRadius: 10, padding: 10 }}>
          <div style={{ fontWeight: 700 }}>Kết quả ngay</div>
          <div>Điểm: <strong>{Number(result?.score ?? 0)}</strong></div>
          <div style={{ color: "#166534" }}>{result?.feedback || "Đã chấm xong bài tập."}</div>
        </div>
      )}
    </div>
  );
}
