import { useCallback, useMemo, useState } from "react";
import ExamResult from "../components/exam/ExamResult";
import TimedExam from "../components/exam/TimedExam";
import TopicHomework from "../components/homework/TopicHomework";
import PersonalizedMaterials from "../components/learning/PersonalizedMaterials";

const FLOW_STEPS = ["placement", "studying", "final", "done"];

const PLACEMENT_QUESTIONS = [
  {
    id: "p1",
    type: "mcq",
    question: "Trong JavaScript, hàm dùng để lặp qua mảng và trả về mảng mới là?",
    options: ["forEach", "map", "filter", "reduce"],
    correct: 1,
    topic: "JavaScript cơ bản",
    difficulty: "easy",
    explanation: "map trả về mảng mới sau khi biến đổi từng phần tử.",
  },
  {
    id: "p2",
    type: "mcq",
    question: "Hook nào dùng để quản lý state trong React function component?",
    options: ["useMemo", "useRef", "useState", "useCallback"],
    correct: 2,
    topic: "React hooks",
    difficulty: "medium",
    explanation: "useState tạo và cập nhật state cục bộ.",
  },
  {
    id: "p3",
    type: "essay",
    question: "Nêu ngắn gọn sự khác nhau giữa props và state trong React.",
    topic: "React foundations",
    difficulty: "hard",
    expectedKeywords: ["props", "state", "component", "immutable", "update"],
    explanation: "Props truyền từ cha, state do component tự quản lý và thay đổi nội bộ.",
  },
];

const FINAL_QUESTIONS = [
  {
    id: "f1",
    type: "mcq",
    question: "Khi nào nên dùng useMemo?",
    options: ["Mọi lúc", "Khi tính toán tốn kém cần memo", "Để gọi API", "Để thay useState"],
    correct: 1,
    topic: "Performance",
    difficulty: "medium",
    explanation: "useMemo tối ưu tính toán tốn kém và phụ thuộc dependencies.",
  },
  {
    id: "f2",
    type: "mcq",
    question: "Thuộc tính key trong list React giúp gì?",
    options: ["Ẩn phần tử", "Tối ưu reconcile", "Validate form", "Tạo style"],
    correct: 1,
    topic: "React rendering",
    difficulty: "easy",
    explanation: "Key giúp React nhận diện phần tử để cập nhật chính xác khi render lại.",
  },
  {
    id: "f3",
    type: "essay",
    question: "Mô tả cách bạn xử lý loading/error state trong một component fetch API.",
    topic: "Data fetching",
    difficulty: "hard",
    expectedKeywords: ["loading", "error", "useEffect", "retry"],
    explanation: "Dùng loading/error state tách bạch, hiển thị fallback rõ ràng và cho phép retry.",
  },
];

function levelFromScore(score) {
  if (score >= 85) return "Giỏi";
  if (score >= 70) return "Khá";
  if (score >= 50) return "Trung bình";
  return "Yếu";
}

function buildResult(questions, answers, timeSpent) {
  let total = 0;
  const topicMap = {};
  const diffMap = { easy: 0, medium: 0, hard: 0 };
  const wrongAnswers = [];

  questions.forEach((question) => {
    const answer = answers[question.id];
    const topic = question.topic || "Chung";
    const difficulty = question.difficulty || "easy";
    if (!topicMap[topic]) topicMap[topic] = { score: 0 };

    let isCorrect = false;
    if (question.type === "essay") {
      const text = String(answer?.answer_text || "").toLowerCase();
      const matchedKeywords = (question.expectedKeywords || []).filter((word) => text.includes(String(word).toLowerCase())).length;
      isCorrect = matchedKeywords >= 2;
    } else {
      isCorrect = answer?.answer_index === question.correct;
    }

    if (isCorrect) {
      total += 100 / questions.length;
      topicMap[topic].score += 1;
      if (difficulty in diffMap) diffMap[difficulty] += 1;
    } else {
      wrongAnswers.push({
        question_id: question.id,
        question: question.question,
        correct_answer: question.type === "essay" ? "Bao gồm các ý chính" : ["A", "B", "C", "D"][question.correct],
        explanation: question.explanation,
      });
    }
  });

  const normalizedScore = Math.round(total);
  const level = levelFromScore(normalizedScore);
  const topicList = Object.entries(topicMap)
    .map(([topic, value]) => ({ topic, score: value.score }))
    .sort((a, b) => a.score - b.score);

  return {
    score_breakdown: {
      total_score: normalizedScore,
      topics: topicList.reduce((acc, item, idx) => {
        acc[item.topic] = { score: item.score, priority: idx + 1 };
        return acc;
      }, {}),
      difficulty: diffMap,
      wrong_answers: wrongAnswers,
      time_spent: timeSpent,
    },
    student_level: level,
    recommendations: topicList.map((item, index) => ({
      id: `${item.topic}-${index}`,
      topic: item.topic,
      topic_id: item.topic,
      priority: index + 1,
      title: `Ôn luyện ${item.topic}`,
      reason: `Bạn cần củng cố thêm chủ đề ${item.topic}.`,
    })),
  };
}

function Stepper({ currentStep }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8, marginBottom: 16 }}>
      {FLOW_STEPS.map((step, index) => {
        const isActive = step === currentStep;
        const currentIndex = FLOW_STEPS.indexOf(currentStep);
        const isCompleted = currentIndex > index;
        return (
          <div
            key={step}
            style={{
              borderRadius: 10,
              border: "1px solid #cbd5e1",
              padding: 10,
              background: isActive ? "#dbeafe" : isCompleted ? "#dcfce7" : "#fff",
              fontWeight: isActive ? 700 : 500,
              textTransform: "capitalize",
              textAlign: "center",
            }}
          >
            {step}
          </div>
        );
      })}
    </div>
  );
}

export default function StudentDashboard() {
  const [flowState, setFlowState] = useState("placement");
  const [placementResult, setPlacementResult] = useState(null);
  const [finalResult, setFinalResult] = useState(null);
  const [activeTopic, setActiveTopic] = useState(null);

  const recommendations = useMemo(() => placementResult?.recommendations || [], [placementResult]);

  const selectedTopic = useMemo(() => {
    return activeTopic || recommendations?.[0]?.topic;
  }, [activeTopic, recommendations]);

  const submitPlacement = useCallback((answers, timeSpent) => {
    const result = buildResult(PLACEMENT_QUESTIONS, answers, timeSpent);
    setPlacementResult(result);
    setFlowState("studying");
  }, []);

  const submitFinal = useCallback((answers, timeSpent) => {
    const result = buildResult(FINAL_QUESTIONS, answers, timeSpent);
    setFinalResult(result);
    setFlowState("done");
  }, []);

  return (
    <div style={{ maxWidth: 1080, margin: "0 auto", padding: 16 }}>
      <h1 style={{ marginTop: 0 }}>Student Learning Dashboard</h1>
      <Stepper currentStep={flowState} />

      {flowState === "placement" && (
        <TimedExam
          questions={PLACEMENT_QUESTIONS}
          durationSeconds={10 * 60}
          onSubmit={submitPlacement}
        />
      )}

      {flowState === "studying" && (
        <div style={{ display: "grid", gap: 12 }}>
          <ExamResult result={placementResult} />

          <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, background: "#fff", padding: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Chọn topic để luyện tập</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {recommendations.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveTopic(item.topic)}
                  style={{
                    border: selectedTopic === item.topic ? "1px solid #2563eb" : "1px solid #cbd5e1",
                    background: selectedTopic === item.topic ? "#dbeafe" : "#fff",
                    borderRadius: 999,
                    padding: "6px 12px",
                  }}
                >
                  {item.topic}
                </button>
              ))}
            </div>
          </div>

          <PersonalizedMaterials
            studentLevel={placementResult?.student_level}
            recommendations={recommendations}
            documentId={1}
          />

          <TopicHomework
            topicId={selectedTopic}
            topicTitle={selectedTopic}
            studentLevel={placementResult?.student_level}
          />

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={() => setFlowState("final")}
              style={{ border: 0, borderRadius: 8, padding: "10px 14px", background: "#16a34a", color: "#fff" }}
            >
              Bắt đầu bài kiểm tra cuối kỳ
            </button>
          </div>
        </div>
      )}

      {flowState === "final" && (
        <TimedExam
          questions={FINAL_QUESTIONS}
          durationSeconds={12 * 60}
          onSubmit={submitFinal}
        />
      )}

      {flowState === "done" && (
        <div style={{ display: "grid", gap: 12 }}>
          <ExamResult result={finalResult} />
          <div style={{ border: "1px solid #bbf7d0", background: "#f0fdf4", borderRadius: 12, padding: 14 }}>
            <h3 style={{ marginTop: 0 }}>Đánh giá cuối kỳ</h3>
            <div>
              Học sinh đạt mức <strong>{finalResult?.student_level || "-"}</strong> sau quá trình học.
            </div>
            <div style={{ marginTop: 8, color: "#166534" }}>
              Tiếp tục duy trì luyện tập theo các chủ đề còn yếu để nâng mức đánh giá trong kỳ tiếp theo.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
