import { useEffect, useState } from "react";
import { API_BASE, apiJson } from "../lib/api";

export default function Health() {
  const [status, setStatus] = useState("Checking...");
  const [vector, setVector] = useState(null);
  const [llm, setLlm] = useState(null);
  const [llmError, setLlmError] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [llmLoading, setLlmLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    const withTimeout = async (promise, timeoutMs = 10000) =>
      Promise.race([
        promise,
        new Promise((_, reject) => setTimeout(() => reject(new Error("Request timeout")), timeoutMs)),
      ]);

    (async () => {
      try {
        // /api/health returns {status, vector}
        const data = await withTimeout(apiJson("/health"));
        if (!mounted) return;
        setStatus(data?.status ?? "ok");
        setVector(data?.vector ?? null);
      } catch {
        if (!mounted) return;
        setStatus("Backend OFF");
        setVector(null);
      } finally {
        if (mounted) setHealthLoading(false);
      }

      try {
        const s = await withTimeout(apiJson("/llm/health"));
        if (!mounted) return;
        setLlm(s);
        setLlmError(null);
      } catch (e) {
        if (!mounted) return;
        setLlm(null);
        if (e?.status === 404) {
          setLlmError("LLM chưa được cấu hình trên môi trường này");
        } else {
          setLlmError(e?.message || "Không kiểm tra được LLM");
        }
      } finally {
        if (mounted) setLlmLoading(false);
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div>
      <h3>Health Check</h3>
      <p>Status: {healthLoading ? "Checking..." : status}</p>
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
        {llmLoading && <div style={{ color: "#666", marginTop: 6 }}>Đang kiểm tra…</div>}
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
