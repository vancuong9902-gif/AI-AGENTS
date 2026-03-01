import { useCallback, useEffect, useState } from "react";
import { apiJson } from "../lib/api";

const stepStyle = {
  display: "flex",
  gap: 8,
  alignItems: "flex-start",
  padding: "6px 0",
};

export default function LibraryPage() {
  const [file, setFile] = useState(null);
  const [docs, setDocs] = useState([]);
  const [status, setStatus] = useState(null);

  const loadFiles = useCallback(async () => {
    const data = await apiJson("/documents?limit=100&offset=0");
    return Array.isArray(data?.items) ? data.items : data?.documents || [];
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const next = await loadFiles();
      if (!cancelled) setDocs(next);
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [loadFiles]);

  const uploadFile = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    const data = await apiJson("/documents/upload", { method: "POST", body: formData });
    if (data?.document_id) {
      const st = await apiJson(`/documents/${data.document_id}/status`);
      setStatus(st || null);
    }

    setFile(null);
    const next = await loadFiles();
    setDocs(next);
  };

  return (
    <div style={{ padding: 20 }}>
      <h2>📤 Upload file</h2>

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <button onClick={uploadFile}>Upload</button>
      </div>

      {status ? (
        <div style={{ marginTop: 12, fontSize: 13, border: "1px solid #ddd", borderRadius: 10, padding: 12 }}>
          <div style={stepStyle}><span>{status?.steps?.upload ? "✅" : "⬛"}</span><span>Đang tải lên...</span></div>
          <div style={stepStyle}><span>{status?.steps?.parse_structure ? "✅" : "⬛"}</span><span>Phân tích cấu trúc...</span></div>
          <div style={stepStyle}><span>{status?.steps?.extract_text ? "✅" : "⬛"}</span><span>Trích xuất văn bản...{status?.ocr_used ? " Đang chạy OCR (có thể mất 1-2 phút)..." : ""}</span></div>
          <div style={stepStyle}><span>{status?.steps?.split_topics ? "✅" : "⬛"}</span><span>Chia topic...</span></div>
          <div style={stepStyle}><span>{status?.steps?.completed ? "✅" : "⬛"}</span><span>{status?.steps?.completed ? `Hoàn tất! ${status?.topics_count || 0} topics đã được tạo` : "Hoàn tất"}</span></div>
          {status?.ocr_used ? <div style={{ color: "#9a6700", marginTop: 6 }}>⚠️ PDF ảnh đã được OCR — chất lượng phụ thuộc độ rõ bản scan</div> : null}
        </div>
      ) : null}

      <hr />

      <h2>📁 Thư viện file</h2>

      {docs.length === 0 && <p>Chưa có tài liệu</p>}

      <ul>
        {docs.map((d) => (
          <li key={d.document_id} style={{ marginBottom: 10 }}>
            📄 <b>{d.title}</b> <span style={{ opacity: 0.7 }}>({d.filename})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
