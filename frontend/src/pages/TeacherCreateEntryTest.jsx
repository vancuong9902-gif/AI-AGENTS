import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

export default function TeacherCreateEntryTest() {
  const { id } = useParams();
  const classroomId = Number(id);
  const teacherId = Number(localStorage.getItem("user_id") || 0);

  const [step, setStep] = useState(1);
  const [docs, setDocs] = useState([]);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [topicsByDoc, setTopicsByDoc] = useState({});
  const [selectedTopicIds, setSelectedTopicIds] = useState([]);

  const [title, setTitle] = useState("Entry Test Tổng Hợp");
  const [totalQuestions, setTotalQuestions] = useState(30);
  const [timeLimit, setTimeLimit] = useState(45);
  const [easyPct, setEasyPct] = useState(30);
  const [mediumPct, setMediumPct] = useState(40);
  const [hardPct, setHardPct] = useState(30);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);
  const [preview, setPreview] = useState(null);
  const [previewQuestions, setPreviewQuestions] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiJson("/documents");
        setDocs(data?.documents || []);
      } catch (e) {
        setError(e?.message || "Không tải được tài liệu");
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      const missing = selectedDocIds.filter((did) => !topicsByDoc[did]);
      if (!missing.length) return;
      const entries = await Promise.all(
        missing.map(async (did) => {
          const data = await apiJson(`/documents/${did}/topics`);
          return [did, data?.topics || []];
        })
      );
      setTopicsByDoc((prev) => {
        const next = { ...(prev || {}) };
        for (const [did, ts] of entries) next[did] = ts;
        return next;
      });
    })();
  }, [selectedDocIds, topicsByDoc]);

  const allTopics = useMemo(() => selectedDocIds.flatMap((did) => topicsByDoc[did] || []), [selectedDocIds, topicsByDoc]);

  const createForPreview = async () => {
    setLoading(true);
    setError("");
    try {
      const payload = {
        teacher_id: teacherId,
        document_ids: selectedDocIds,
        topic_ids: selectedTopicIds,
        title,
        time_limit_minutes: Number(timeLimit) || 45,
        distribution: { easy_pct: Number(easyPct), medium_pct: Number(mediumPct), hard_pct: Number(hardPct) },
        total_questions: Number(totalQuestions) || 30,
      };
      const data = await apiJson(`/classrooms/${classroomId}/entry-test`, { method: "POST", body: payload });
      setCreated(data);
      const assessment = await apiJson(`/assessments/${data.assessment_id}`);
      setPreview(assessment);
      setPreviewQuestions(assessment?.questions || []);
      setStep(4);
    } catch (e) {
      setError(e?.message || "Không tạo được đề");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 1100, margin: "20px auto", padding: 16 }}>
      <h2>Tạo Entry Test cho lớp</h2>
      <div style={{ marginBottom: 12 }}>Step {step}/5</div>
      {error ? <div style={{ color: "#b00020", marginBottom: 10 }}>{error}</div> : null}

      {step === 1 && (
        <div>
          <h3>Step 1: Chọn tài liệu đã upload</h3>
          {(docs || []).map((d) => (
            <label key={d.document_id} style={{ display: "block", marginBottom: 6 }}>
              <input
                type="checkbox"
                checked={selectedDocIds.includes(d.document_id)}
                onChange={(e) => setSelectedDocIds((prev) => (e.target.checked ? [...prev, d.document_id] : prev.filter((x) => x !== d.document_id)))}
              />{" "}
              {d.title}
            </label>
          ))}
          <button disabled={!selectedDocIds.length} onClick={() => setStep(2)}>Tiếp</button>
        </div>
      )}

      {step === 2 && (
        <div>
          <h3>Step 2: Chọn topic</h3>
          {(allTopics || []).map((t) => (
            <label key={t.topic_id} style={{ display: "block", marginBottom: 8 }}>
              <input
                type="checkbox"
                checked={selectedTopicIds.includes(t.topic_id)}
                onChange={(e) => setSelectedTopicIds((prev) => (e.target.checked ? [...prev, t.topic_id] : prev.filter((x) => x !== t.topic_id)))}
              />{" "}
              <b>{t.display_title || t.title}</b>
              <div style={{ color: "#666", marginLeft: 22 }}>{t.summary || "(Không có tóm tắt)"}</div>
            </label>
          ))}
          <button onClick={() => setStep(1)}>Quay lại</button>{" "}
          <button disabled={!selectedTopicIds.length} onClick={() => setStep(3)}>Tiếp</button>
        </div>
      )}

      {step === 3 && (
        <div>
          <h3>Step 3: Cấu hình đề</h3>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Tiêu đề" />
          <div>Tổng câu: <input type="number" value={totalQuestions} onChange={(e) => setTotalQuestions(e.target.value)} /></div>
          <div>Thời gian (phút): <input type="number" value={timeLimit} onChange={(e) => setTimeLimit(e.target.value)} /></div>
          <div>Dễ %: <input type="number" value={easyPct} onChange={(e) => setEasyPct(e.target.value)} /></div>
          <div>TB %: <input type="number" value={mediumPct} onChange={(e) => setMediumPct(e.target.value)} /></div>
          <div>Khó %: <input type="number" value={hardPct} onChange={(e) => setHardPct(e.target.value)} /></div>
          <button onClick={() => setStep(2)}>Quay lại</button>{" "}
          <button disabled={loading} onClick={createForPreview}>{loading ? "Đang tạo..." : "Tạo & xem preview"}</button>
        </div>
      )}

      {step === 4 && (
        <div>
          <h3>Step 4: Preview đề</h3>
          <div>Thời gian: {preview?.time_limit_minutes} phút</div>
          {(previewQuestions || []).map((q, idx) => (
            <div key={q.question_id} style={{ border: "1px solid #eee", borderRadius: 8, padding: 8, marginBottom: 8 }}>
              <div><b>Câu {idx + 1}:</b> {q.stem}</div>
              <button onClick={() => setPreviewQuestions((prev) => prev.filter((x) => x.question_id !== q.question_id))}>Xóa khỏi preview</button>
            </div>
          ))}
          <button onClick={() => setStep(3)}>Quay lại</button>{" "}
          <button onClick={() => setStep(5)}>Phát cho lớp</button>
        </div>
      )}

      {step === 5 && (
        <div>
          <h3>Step 5: Đã phát cho lớp</h3>
          <p>Assessment ID: <b>{created?.assessment_id}</b></p>
          <p>Preview URL: <code>{created?.preview_url}</code></p>
          {created?.assessment_id ? <Link to={`/teacher/assessments/${created.assessment_id}/leaderboard`}>Mở leaderboard</Link> : null}
        </div>
      )}
    </div>
  );
}
