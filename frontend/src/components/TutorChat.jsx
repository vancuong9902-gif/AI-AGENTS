import React from 'react';
import { mvpApi } from '../api';

function isOnTopic(text, topics) {
  const lowered = String(text || '').toLowerCase();
  if (!lowered) return true;
  return topics.some((t) => lowered.includes(String(t || '').toLowerCase()));
}

export default function TutorChat({ topicTitle, sessionKey }) {
  const storageKey = `tutor-chat-${sessionKey || 'default'}`;
  const [messages, setMessages] = React.useState(() => {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || '[]');
    } catch {
      return [];
    }
  });
  const [input, setInput] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const suggestions = [
    `Tóm tắt nhanh chủ đề ${topicTitle}`,
    `${topicTitle} có lỗi nào học sinh hay mắc?`,
    `Cho em 1 bài tập ngắn về ${topicTitle}`,
  ];

  React.useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(messages));
  }, [messages, storageKey]);

  const send = async (text) => {
    const q = text.trim();
    if (!q || loading) return;

    setMessages((prev) => [...prev, { role: 'user', text: q }]);
    setInput('');

    if (!isOnTopic(q, [topicTitle, 'bài học', 'topic', 'bài tập'])) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'bot',
          text: 'Mình chỉ hỗ trợ các câu hỏi liên quan đến chủ đề đang học. Bạn có thể hỏi về khái niệm, ví dụ, bài tập hoặc cách làm nhé.',
        },
      ]);
      return;
    }

    setLoading(true);
    try {
      const res = await mvpApi.askTutor(q);
      const answer = res.data?.data?.answer || res.data?.data?.message || 'Mình chưa có câu trả lời phù hợp.';
      setMessages((prev) => [...prev, { role: 'bot', text: answer }]);
    } catch {
      setMessages((prev) => [...prev, { role: 'bot', text: 'Không thể kết nối AI tutor. Vui lòng thử lại.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <div className="row-between">
        <h3>Tutor AI</h3>
        <button className="ghost sm" onClick={() => setMessages([])}>Xóa lịch sử</button>
      </div>

      <div className="row">
        <button className="outline sm" onClick={() => send(suggestions[0])}>Gợi ý câu hỏi</button>
        <span className="badge gray">{suggestions[0]}</span>
        <span className="badge gray">{suggestions[1]}</span>
        <span className="badge gray">{suggestions[2]}</span>
      </div>

      <div className="chat-box">
        <div className="chat-messages">
          {messages.map((m, idx) => (
            <div key={idx} className={`chat-bubble ${m.role}`}>{m.text}</div>
          ))}
          {loading && <div className="chat-bubble bot typing">Đang trả lời...</div>}
        </div>
        <div className="chat-input-row">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Hỏi AI về chủ đề đang học..."
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
          />
          <button onClick={() => send(input)} disabled={!input.trim() || loading}>Gửi</button>
        </div>
      </div>
    </div>
  );
}
