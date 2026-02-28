import { useEffect, useMemo, useState } from "react";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

function tone(level) {
  if (level === "ALERT") return "bg-red-50 border-red-200 text-red-800";
  if (level === "WARN") return "bg-amber-50 border-amber-200 text-amber-800";
  return "bg-slate-50 border-slate-200 text-slate-800";
}

function fmtTs(s) {
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

function healthTone(failRate) {
  if (failRate > 0.1) return "bg-red-100 text-red-700";
  if (failRate > 0.03) return "bg-amber-100 text-amber-700";
  return "bg-emerald-100 text-emerald-700";
}

function healthLabel(failRate) {
  if (failRate > 0.1) return "red";
  if (failRate > 0.03) return "yellow";
  return "green";
}

export default function TeacherInfraDashboard() {
  const { role } = useAuth();

  const [days, setDays] = useState(7);
  const [jobId, setJobId] = useState("");
  const [jobStatus, setJobStatus] = useState(null);
  const [jobError, setJobError] = useState("");

  const [reports, setReports] = useState([]);
  const [selected, setSelected] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [dashboardError, setDashboardError] = useState("");

  async function refreshReports() {
    try {
      const res = await apiJson(`/jobs/drift/reports?limit=50`);
      setReports(res?.reports || []);
    } catch {
      // ignore
    }
  }

  async function refreshAgentDashboard() {
    try {
      const res = await apiJson(`/admin/agent-dashboard`);
      setDashboard(res || null);
      setDashboardError("");
    } catch (e) {
      setDashboardError(e?.message || "Failed to load agent dashboard");
    }
  }

  useEffect(() => {
    const t = setTimeout(() => {
      refreshReports();
      refreshAgentDashboard();
    }, 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      refreshAgentDashboard();
    }, 5000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let t = null;
    async function poll() {
      if (!jobId) return;
      try {
        const res = await apiJson(`/jobs/status/${encodeURIComponent(jobId)}`);
        setJobStatus(res || null);
        setJobError("");
      } catch (e) {
        setJobError(e?.message || "Failed to fetch job status");
      }
      t = setTimeout(poll, 2500);
    }
    poll();
    return () => t && clearTimeout(t);
  }, [jobId]);

  async function enqueueRebuild() {
    setSelected(null);
    setJobError("");
    setJobStatus(null);
    try {
      const res = await apiJson(`/jobs/index/rebuild`, { method: "POST" });
      const id = res?.job_id || "";
      setJobId(id);
      if (!id && res?.sync_executed) {
        // sync fallback result
        setJobStatus({ status: "finished", result: res?.result });
      }
    } catch (e) {
      setJobError(e?.message || "Failed to enqueue");
    }
  }

  async function enqueueDriftCheck() {
    setSelected(null);
    setJobError("");
    setJobStatus(null);
    try {
      const res = await apiJson(`/jobs/drift/check?days=${days}`, { method: "POST" });
      const id = res?.job_id || "";
      setJobId(id);
      if (!id && res?.sync_executed) {
        setJobStatus({ status: "finished", result: res?.result });
        refreshReports();
      }
    } catch (e) {
      setJobError(e?.message || "Failed to enqueue");
    }
  }

  async function openReport(id) {
    try {
      const res = await apiJson(`/jobs/drift/reports/${id}`);
      setSelected(res || null);
    } catch (e) {
      setJobError(e?.message || "Failed to load drift report");
    }
  }

  const alertAgents = useMemo(() => {
    const entries = Object.entries(dashboard?.agents || {});
    return entries.filter(([, stats]) => {
      const total = Number(stats?.success || 0) + Number(stats?.failed || 0) + Number(stats?.timeout || 0);
      if (!total) return false;
      return Number(stats?.failed || 0) / total > 0.1;
    });
  }, [dashboard]);

  if (role !== "teacher") {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <div className="p-4 rounded-lg border bg-white">
          <div className="font-semibold">Not authorized</div>
          <div className="text-sm text-slate-600">Teacher role required.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Event-driven Infra</h1>
          <div className="text-sm text-slate-600">
            Background indexing (RQ/Redis) + drift monitoring reports.
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <div className="p-4 rounded-lg border bg-white space-y-3 md:col-span-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold">MAS Agent Monitoring (24h)</div>
              <div className="text-xs text-slate-500">Auto refresh mỗi 5 giây</div>
            </div>
            <button onClick={refreshAgentDashboard} className="text-sm px-2 py-1 rounded-md border hover:bg-slate-50">Refresh</button>
          </div>

          {dashboardError ? <div className="text-sm text-red-700">{dashboardError}</div> : null}

          <div className="grid md:grid-cols-4 gap-3">
            <div className="p-3 rounded-md border bg-slate-50">
              <div className="text-xs text-slate-600">Events (24h)</div>
              <div className="text-2xl font-bold">{dashboard?.events_last_24h ?? 0}</div>
            </div>
            <div className="p-3 rounded-md border bg-slate-50">
              <div className="text-xs text-slate-600">Pending events</div>
              <div className="text-2xl font-bold">{dashboard?.pending_events ?? 0}</div>
            </div>
          </div>

          {alertAgents.length > 0 ? (
            <div className="rounded-md border border-red-200 bg-red-50 text-red-700 text-sm p-2">
              Alert: fail rate &gt; 10% ở {alertAgents.map(([name]) => name).join(", ")}
            </div>
          ) : null}

          <div className="grid md:grid-cols-2 gap-3">
            {Object.entries(dashboard?.agents || {}).map(([name, stats]) => {
              const total = Number(stats?.success || 0) + Number(stats?.failed || 0) + Number(stats?.timeout || 0);
              const failRate = total ? Number(stats?.failed || 0) / total : 0;
              return (
                <div key={name} className="p-3 rounded-md border bg-white space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="font-medium">{name}</div>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${healthTone(failRate)}`}>
                      {healthLabel(failRate)}
                    </span>
                  </div>
                  <div className="text-sm text-slate-600">
                    success: {stats?.success || 0} • failed: {stats?.failed || 0} • timeout: {stats?.timeout || 0}
                  </div>
                  <div className="text-sm text-slate-600">
                    avg latency: {stats?.avg_ms || 0} ms • fail rate: {(failRate * 100).toFixed(1)}%
                  </div>
                </div>
              );
            })}
          </div>

          <div>
            <div className="font-medium mb-2">Real-time event feed</div>
            <div className="space-y-2 max-h-72 overflow-auto pr-1">
              {(dashboard?.recent_events || []).map((ev) => (
                <div key={ev.id} className="p-2 rounded-md border bg-slate-50 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{ev.agent_name} • {ev.event_type}</span>
                    <span className="text-xs text-slate-500">{fmtTs(ev.created_at)}</span>
                  </div>
                  <div className="text-xs text-slate-600">status: {ev.status} • duration: {ev.duration_ms || 0} ms • user: {ev.user_id ?? "-"}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="p-4 rounded-lg border bg-white space-y-3">
          <div className="font-semibold">Queue actions</div>

          <button onClick={enqueueRebuild} className="w-full px-3 py-2 rounded-md bg-slate-900 text-white hover:bg-slate-800">
            Enqueue index rebuild
          </button>

          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-600">Drift window (days)</label>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="px-2 py-1 border rounded-md">
              <option value={7}>7</option>
              <option value={14}>14</option>
              <option value={30}>30</option>
            </select>
          </div>

          <button onClick={enqueueDriftCheck} className="w-full px-3 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-500">
            Enqueue drift check
          </button>

          {jobError ? <div className="text-sm text-red-700">{jobError}</div> : null}
        </div>

        <div className="p-4 rounded-lg border bg-white space-y-2">
          <div className="font-semibold">Last job</div>
          <div className="text-sm text-slate-600 break-all">job_id: {jobId || "(none)"}</div>

          <div className="text-sm">
            status: <span className="font-semibold">{jobStatus?.status || "(unknown)"}</span>
          </div>

          {jobStatus?.result ? (
            <pre className="text-xs bg-slate-50 border rounded-md p-2 overflow-auto max-h-64">
              {JSON.stringify(jobStatus.result, null, 2)}
            </pre>
          ) : null}

          {jobStatus?.exc_info ? (
            <pre className="text-xs bg-red-50 border border-red-200 rounded-md p-2 overflow-auto max-h-64">
              {jobStatus.exc_info}
            </pre>
          ) : null}
        </div>

        <div className="p-4 rounded-lg border bg-white space-y-2">
          <div className="flex items-center justify-between">
            <div className="font-semibold">Drift reports</div>
            <button onClick={refreshReports} className="text-sm px-2 py-1 rounded-md border hover:bg-slate-50">Refresh</button>
          </div>

          <div className="space-y-2 max-h-72 overflow-auto pr-1">
            {(reports || []).map((r) => {
              const lvl = r?.overall?.level || "OK";
              const score = r?.overall?.drift_score;
              return (
                <button
                  key={r.id}
                  onClick={() => openReport(r.id)}
                  className={`w-full text-left p-2 rounded-md border ${tone(lvl)} hover:opacity-90`}
                >
                  <div className="flex items-center justify-between">
                    <div className="font-semibold">#{r.id} • {lvl}</div>
                    <div className="text-sm">{typeof score === "number" ? score.toFixed(2) : ""}</div>
                  </div>
                  <div className="text-xs opacity-80">{fmtTs(r.created_at)}</div>
                </button>
              );
            })}
            {(!reports || reports.length === 0) ? (
              <div className="text-sm text-slate-600">No reports yet. Enqueue a drift check.</div>
            ) : null}
          </div>
        </div>
      </div>

      {selected ? (
        <div className="p-4 rounded-lg border bg-white space-y-2">
          <div className="font-semibold">Selected report #{selected.id}</div>
          <div className="text-sm text-slate-600">
            created_at: {fmtTs(selected.created_at)} • scope: {selected.scope}
          </div>
          <pre className="text-xs bg-slate-50 border rounded-md p-3 overflow-auto max-h-[520px]">
            {JSON.stringify(selected.report, null, 2)}
          </pre>
        </div>
      ) : null}

      <div className="text-xs text-slate-500">
        Note: If the async queue is disabled, jobs run synchronously and job_id will be empty.
      </div>
    </div>
  );
}
