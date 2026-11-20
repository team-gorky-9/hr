/** Fetch adapter for any browser or server. Pass the address of the reporting API or your proxy. */
export function reportingClient(base = "/api/v1/reports/annual", fetcher = globalThis.fetch) {
  const url = base.replace(/\/$/, "");
  async function request(path, signal, body, binary = false) {
    const response = await fetcher(url + path, body === undefined
      ? { signal }
      : { method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = new Error(payload.error?.message ?? `HTTP ${response.status}`);
      Object.assign(error, { status: response.status, code: payload.error?.code, details: payload.error?.details });
      throw error;
    }
    return binary ? response.blob() : response.json();
  }
  const path = id => "/" + encodeURIComponent(id);
  return {
    versions: (year, signal) => request(year == null ? "" : "?year=" + encodeURIComponent(year), signal),
    snapshot: (id, signal) => request(path(id), signal),
    catalog: (id, signal) => request(path(id) + "/catalog", signal),
    brief: (id, signal) => request(path(id) + "/brief", signal),
    signals: (id, signal) => request(path(id) + "/signals", signal),
    analyze: (id, query, signal) => request(path(id) + "/query", signal, query),
    charts: (id, query, signal) => request(path(id) + "/charts", signal, query),
    departments: (id, query, signal) => request(path(id) + "/operations", signal, query),
    downloadReport: (id, signal) => request(path(id) + "/xlsx", signal, undefined, true),
    downloadAnalysis: (id, query, signal) => request(path(id) + "/query/xlsx", signal, query, true),
    downloadDepartments: (id, query, signal) => request(path(id) + "/operations/xlsx", signal, query, true),
  };
}
