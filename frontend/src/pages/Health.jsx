import { useEffect, useState } from "react";
import { API_BASE, apiJson } from "../lib/api";

export default function Health() {
  const [status, setStatus] = useState("Checking...");
  const [vector, setVector] = useState(null);
  const [llm, setLlm] = useState(null);
  const [llmError, setLlmError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        // /api/health returns {status, vector}
        const data = await apiJson("/health");
        setStatus(data?.status ?? "ok");
        setVector(data?.vector ?? null);
      } catch {
        setStatus("Backend OFF");
        setVector(null);
      }

      try {
        const s = await apiJson("/llm/status");
        setLlm(s);
        setLlmError(null);
      } catch (e) {
        setLlm(null);
        setLlmError(e?.message || "Không kiểm tra được LLM");
      }
    })();
  }, []);

  return (
    <div>
      <h3>Health Check</h3>
      <p>Status: {status}</p>
      <p style={{ opacity: 0.8, marginTop: 6 }}>
        API_BASE: <code>{API_BASE}</code>
      </p>
      {vector && (
        <p style={{ opacity: 0.8, marginTop: 6 }}>
          Vector: <code>{JSON.stringify(vector)}</code>
        </p>
      )}

      <div style={{ marginTop: 14, padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
        <div style={{ fontWeight: 900 }}>LLM Status</div>
        {llmError && <div style={{ color: "#b00020", marginTop: 6 }}>{llmError}</div>}
        {!llm && !llmError && <div style={{ color: "#666", marginTop: 6 }}>Đang kiểm tra…</div>}
        {llm && (
          <div style={{ opacity: 0.9, marginTop: 6, lineHeight: 1.6 }}>
            <div>
              Available: <b>{String(llm.llm_available)}</b>
            </div>
            <div>
              Provider: <b>{llm.provider}</b> • Model: <b>{llm.model}</b>
            </div>
            <div>
              Base URL: <code>{llm.base_url || "(default)"}</code>
            </div>
            <div>
              SDK: <code>{llm.sdk_version || "unknown"}</code>
            </div>
            {llm.test_response && (
              <div>
                Test: <code>{JSON.stringify(llm.test_response)}</code>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
