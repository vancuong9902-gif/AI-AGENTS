import { useEffect, useState } from "react";
import { apiJson } from "../lib/api";

export default function LibraryPage() {
  const [file, setFile] = useState(null);
  const [docs, setDocs] = useState([]);

  const loadFiles = async () => {
    const data = await apiJson("/documents");
    setDocs(data?.documents || []);
  };

  useEffect(() => {
    loadFiles(); // load khi mở trang
  }, []);

  const uploadFile = async () => {
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    await apiJson("/documents/upload", { method: "POST", body: formData });

    setFile(null);
    loadFiles(); // ⭐ CỰC KỲ QUAN TRỌNG
  };

  return (
    <div style={{ padding: 20 }}>
      <h2>📤 Upload file</h2>

      <input type="file" onChange={e => setFile(e.target.files[0])} />
      <button onClick={uploadFile}>Upload</button>

      <hr />

      <h2>📁 Thư viện file</h2>

      {docs.length === 0 && <p>Chưa có tài liệu</p>}

      <ul>
        {docs.map((d) => (
          <li key={d.document_id} style={{ marginBottom: 10 }}>
            📄 <b>{d.title}</b> <span style={{ opacity: 0.7 }}>({d.filename})</span>
            {d.auto_topics && d.auto_topics.length > 0 && (
              <div style={{ opacity: 0.9, fontSize: 13, marginTop: 6 }}>
                <div style={{ fontWeight: 800, marginBottom: 4 }}>Topics (tóm tắt)</div>
                <ol style={{ margin: 0, paddingLeft: 18 }}>
                  {d.auto_topics.slice(0, 8).map((t, i) => (
                    <li key={i} style={{ marginBottom: 2 }}>
                      {t}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
