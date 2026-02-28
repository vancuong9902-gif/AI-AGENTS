import { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

export default function FinalExam() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();

  const quizIdFromState = location.state?.quizId;
  const quizIdFromQuery = new URLSearchParams(location.search).get("quizId");
  const quizId = quizIdFromState || quizIdFromQuery;
  const studentId = location.state?.studentId || JSON.parse(localStorage.getItem("user") || "{}").id || localStorage.getItem("user_id") || 1;
  const classroomId = params.classroomId;

  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [timeLeft, setTimeLeft] = useState(null);
  const [attemptId, setAttemptId] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const timerRef = useRef(null);
  const autoSubmittedRef = useRef(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        let targetQuizId = quizId;
        if (!targetQuizId && classroomId) {
          const uid = Number(studentId || 1);
          const gen = await apiJson(`/v1/lms/final-exam/generate?classroomId=${classroomId}&userId=${uid}`, { method: "POST" });
          const status = await apiJson(`/v1/lms/final-exam/status?jobId=${gen.jobId}`);
          targetQuizId = status?.result?.quiz_id;
        }
        if (!targetQuizId) throw new Error("Thiếu quizId cho bài thi cuối kỳ.");

        const started = await apiJson("/attempts/start", {
          method: "POST",
          body: { quiz_id: parseInt(targetQuizId, 10), student_id: parseInt(studentId, 10) },
        });
        setAttemptId(started.attempt_id);

        const data = await apiJson(`/assessments/${targetQuizId}`);
        setQuestions(data.questions || []);
        setTimeLeft(data.duration_seconds || 3600);
      } catch (e) {
        setError(e?.message || "Không tải được đề thi cuối kỳ.");
      } finally {
        setLoading(false);
      }
    })();
  }, [quizId, classroomId, studentId]);

  useEffect(() => {
    if (timeLeft === null || submitted) return;
    if (timeLeft <= 0) {
      if (!autoSubmittedRef.current) {
        autoSubmittedRef.current = true;
        handleSubmit(true);
      }
      return;
    }
    timerRef.current = setTimeout(() => setTimeLeft((t) => t - 1), 1000);
    return () => clearTimeout(timerRef.current);
  }, [timeLeft, submitted]);

  const handleSubmit = async (autoSubmit = false) => {
    if (submitted || !attemptId) return;
    setSubmitted(true);
    const answersArr = Object.entries(answers).map(([qid, choice]) => ({
      question_id: parseInt(qid, 10),
      selected: choice,
    }));
    try {
      const data = await apiJson(`/attempts/${attemptId}/submit`, {
        method: "POST",
        body: { answers: answersArr },
      });
      setResult({ ...data, autoSubmit });
    } catch (e) {
      alert("Lỗi nộp bài: " + (e?.message || "Unknown error"));
      setSubmitted(false);
    }
  };

  const formatTime = (sec) => {
    const m = Math.floor(sec / 60)
      .toString()
      .padStart(2, "0");
    const s = (sec % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  if (loading) return <div className="p-8 text-center">Đang tải đề thi cuối kỳ...</div>;
  if (error) return <div className="p-8 text-center text-red-600">{error}</div>;

  if (result) {
    return (
      <div className="max-w-2xl mx-auto p-8">
        <h1 className="text-2xl font-bold text-green-700 mb-4">🎓 Kết Quả Bài Thi Cuối Kỳ</h1>
        {result.autoSubmit && <div className="bg-yellow-100 border border-yellow-400 p-3 rounded mb-4">⚠️ Bài thi đã được tự động nộp khi hết giờ.</div>}
        {result.is_late_submission && <div className="bg-red-100 border border-red-400 p-3 rounded mb-4">🚨 {result.notes}</div>}
        <div className="bg-white shadow rounded p-6 mb-4">
          <p className="text-4xl font-bold text-center text-blue-700 mb-2">{Number(result.score_breakdown?.overall?.percent || 0).toFixed(1)}%</p>
          <p className="text-center text-gray-600">
            Xếp loại: <strong className="capitalize">{String(result.classification?.level_label || result.classification?.level_key || "").replace("_", " ")}</strong>
          </p>
          <p className="text-center text-gray-500 text-sm mt-1">Thời gian làm bài: {Math.round(Number(result.time_spent_seconds || 0) / 60)} phút</p>
        </div>
        <button onClick={() => navigate("/classrooms")} className="w-full bg-blue-600 text-white py-3 rounded font-semibold hover:bg-blue-700">
          Về Trang Lớp Học
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6 bg-red-50 p-4 rounded-lg border border-red-200">
        <h1 className="text-xl font-bold text-red-800">🏁 Bài Kiểm Tra Cuối Kỳ</h1>
        <div className={`text-2xl font-mono font-bold ${timeLeft <= 300 ? "text-red-600 animate-pulse" : "text-gray-700"}`}>
          ⏱ {timeLeft !== null ? formatTime(timeLeft) : "--:--"}
        </div>
      </div>

      <div className="mb-4 text-sm text-gray-500">Đã trả lời: {Object.keys(answers).length}/{questions.length} câu</div>

      {questions.map((q, idx) => (
        <div key={q.id || q.question_id || idx} className="bg-white shadow rounded-lg p-5 mb-4 border-l-4 border-blue-400">
          <p className="font-medium mb-1 text-xs text-blue-500 uppercase">Câu {idx + 1}</p>
          <p className="font-semibold mb-3">{q.stem}</p>
          <div className="space-y-2">
            {(q.choices || q.options || []).map((choice, ci) => (
              <label key={ci} className={`flex items-center p-3 rounded cursor-pointer border transition ${answers[q.id || q.question_id] === choice ? "bg-blue-100 border-blue-400" : "bg-gray-50 border-gray-200 hover:bg-gray-100"}`}>
                <input
                  type="radio"
                  name={`q-${q.id || q.question_id}`}
                  value={choice}
                  checked={answers[q.id || q.question_id] === choice}
                  onChange={() => setAnswers((a) => ({ ...a, [q.id || q.question_id]: choice }))}
                  className="mr-3"
                />
                {choice}
              </label>
            ))}
          </div>
        </div>
      ))}

      <button
        onClick={() => {
          if (window.confirm(`Bạn đã trả lời ${Object.keys(answers).length}/${questions.length} câu. Xác nhận nộp bài?`)) {
            handleSubmit();
          }
        }}
        disabled={submitted}
        className="w-full bg-red-600 text-white py-4 rounded-lg font-bold text-lg hover:bg-red-700 disabled:opacity-50 mt-4"
      >
        📤 Nộp Bài Thi Cuối Kỳ
      </button>
    </div>
  );
}
