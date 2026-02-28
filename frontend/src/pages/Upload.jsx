import { useState } from "react";
import { apiJson } from "../lib/api";

export default function Upload() {
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState("");
  const [title, setTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [topics, setTopics] = useState([]);
  const [topicsStatus, setTopicsStatus] = useState(null);

  const handleUpload = async () => {
    if (!file) {
      alert("Chọn file trước");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    // Backend expects multipart/form-data and supports these optional fields
    formData.append("user_id", localStorage.getItem("user_id") || "1");
    if (title) formData.append("title", title);

    try {
      setUploading(true);
      setMsg("Đang upload…");
      const res = await apiJson("/documents/upload", { method: "POST", body: formData });
      setTopics(res?.topics || []);
      setTopicsStatus(res?.topics_status || null);

      if ((res?.topics || []).length > 0) {
        setMsg(`Upload thành công. AI đã chia ${(res.topics || []).length} topic.`);
      } else {
        const st = res?.topics_status ? ` (topics_status: ${res.topics_status})` : "";
        setMsg(`Upload thành công nhưng chưa chia được topic${st}.`);
      }
    } catch (err) {
      setMsg(err?.message || "Không kết nối được backend");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <h3>Upload tài liệu (giảng viên)</h3>

      <div style={{ marginBottom: 8 }}>
        <label style={{ display: "block", fontWeight: 600 }}>Tiêu đề (tuỳ chọn)</label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="VD: Chương 1 - Python cơ bản"
          style={{ width: "100%", maxWidth: 520, padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
        />
      </div>

      <input type="file" disabled={uploading} onChange={(e) => setFile(e.target.files[0])} />
      <br /><br />
      <button onClick={handleUpload} disabled={uploading}>
        {uploading ? "Đang upload…" : "Upload"}
      </button>

      <p>{msg}</p>

      {topicsStatus && (
        <p style={{ opacity: 0.75, marginTop: 6 }}>
          Topics status: <b>{topicsStatus}</b>
        </p>
      )}

      {topics && topics.length > 0 && (
        <div style={{ marginTop: 12, maxWidth: 720 }}>
          <h4 style={{ marginBottom: 6 }}>📌 Topics trích từ tài liệu</h4>
          <ul style={{ listStyle: "disc", paddingLeft: 22 }}>
            {topics.map((t) => (
              <li key={t.topic_id || t.title} style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>{t.title}</div>
                {t.summary && <div style={{ opacity: 0.85 }}>{t.summary}</div>}
                {t.keywords && t.keywords.length > 0 && (
                  <div style={{ opacity: 0.75, fontSize: 13 }}>
                    Keywords: {t.keywords.slice(0, 8).join(", ")}
                  </div>
                )}

                {(t.outline || t.key_points || t.definitions || t.examples || t.formulas) && (
                  <details style={{ marginTop: 6 }}>
                    <summary style={{ cursor: "pointer", opacity: 0.9 }}>Xem chi tiết topic</summary>

                    {t.start_chunk_index !== undefined && t.end_chunk_index !== undefined && (
                      <div style={{ opacity: 0.75, fontSize: 13, marginTop: 6 }}>
                        Chunk range: {t.start_chunk_index} → {t.end_chunk_index}
                        {t.included_chunk_ids && t.included_chunk_ids.length > 0 ? ` (chunks: ${t.included_chunk_ids.length})` : ""}
                      </div>
                    )}

                    {t.outline && t.outline.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontWeight: 700 }}>Outline</div>
                        <ul style={{ marginTop: 4 }}>
                          {t.outline.slice(0, 20).map((x, i) => (
                            <li key={i} style={{ opacity: 0.9 }}>{x}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {t.key_points && t.key_points.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontWeight: 700 }}>Ý chính</div>
                        <ul style={{ marginTop: 4 }}>
                          {t.key_points.slice(0, 16).map((x, i) => (
                            <li key={i} style={{ opacity: 0.9 }}>{x}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {t.definitions && t.definitions.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontWeight: 700 }}>Khái niệm/Định nghĩa</div>
                        <ul style={{ marginTop: 4 }}>
                          {t.definitions.slice(0, 12).map((d, i) => (
                            <li key={i} style={{ opacity: 0.9 }}>
                              <b>{d.term}</b>: {d.definition}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {t.examples && t.examples.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontWeight: 700 }}>Ví dụ</div>
                        <ul style={{ marginTop: 4 }}>
                          {t.examples.slice(0, 8).map((x, i) => (
                            <li key={i} style={{ opacity: 0.9 }}>{x}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {t.formulas && t.formulas.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontWeight: 700 }}>Công thức / Biểu thức</div>
                        <ul style={{ marginTop: 4 }}>
                          {t.formulas.slice(0, 8).map((x, i) => (
                            <li key={i} style={{ opacity: 0.9, fontFamily: "monospace" }}>{x}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {t.content_preview && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontWeight: 700 }}>Nội dung (preview)</div>
                        <div style={{ opacity: 0.85, fontSize: 13, whiteSpace: "pre-wrap" }}>{t.content_preview}{t.has_more_content ? "…" : ""}</div>
                      </div>
                    )}

                  </details>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
