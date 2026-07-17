const API_BASE = "http://127.0.0.1:9000/api/v1";

export async function askQuestion(query, limit = 10, account_context = null, conversation_history = null) {
  const res = await fetch(`${API_BASE}/query/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit, account_context, conversation_history }),
  });
  if (!res.ok) throw new Error(`Query failed: ${res.statusText}`);
  return res.json();
}

export async function ingestData(source, data) {
  const res = await fetch(`${API_BASE}/data/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, data }),
  });
  if (!res.ok) throw new Error(`Ingest failed: ${res.statusText}`);
  return res.json();
}

export async function uploadFile(file, source = "user_upload", forceProcess = false) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("source", source);
  if (forceProcess) formData.append("force_process", "true");

  const res = await fetch(`${API_BASE}/data/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

export async function uploadFileForAccount(accountName, file, source = "account_upload", forceProcess = false) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("source", source);
  if (forceProcess) formData.append("force_process", "true");

  const res = await fetch(`${API_BASE}/data/upload/${encodeURIComponent(accountName)}`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

export async function getSchemaInfo() {
  const res = await fetch(`${API_BASE}/schema/info`);
  if (!res.ok) throw new Error(`Schema info failed: ${res.statusText}`);
  return res.json();
}

export async function checkHealth() {
  const res = await fetch("http://127.0.0.1:9000/health");
  if (!res.ok) throw new Error("Backend unreachable");
  return res.json();
}

export async function getAccounts() {
  const res = await fetch(`${API_BASE}/dashboard/accounts`);
  if (!res.ok) throw new Error("Failed to fetch accounts");
  return res.json();
}

export async function getAccountDetail(accountId) {
  const res = await fetch(`${API_BASE}/dashboard/accounts/${accountId}`);
  if (!res.ok) throw new Error("Failed to fetch account detail");
  return res.json();
}

export async function getPipeline() {
  const res = await fetch(`${API_BASE}/dashboard/pipeline`);
  if (!res.ok) throw new Error("Failed to fetch pipeline");
  return res.json();
}

export async function getInsights() {
  const res = await fetch(`${API_BASE}/dashboard/insights`);
  if (!res.ok) throw new Error("Failed to fetch insights");
  return res.json();
}

export async function getDashboardStats() {
  const res = await fetch(`${API_BASE}/dashboard/stats`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export async function getGoldTopCustomers() {
  const res = await fetch(`${API_BASE}/dashboard/gold/top-customers`);
  if (!res.ok) throw new Error("Failed to fetch top customers");
  return res.json();
}

export async function getGoldPipelineHealth() {
  const res = await fetch(`${API_BASE}/dashboard/gold/pipeline-health`);
  if (!res.ok) throw new Error("Failed to fetch pipeline health");
  return res.json();
}

export async function getGoldRevenueSummary() {
  const res = await fetch(`${API_BASE}/dashboard/gold/revenue-summary`);
  if (!res.ok) throw new Error("Failed to fetch revenue summary");
  return res.json();
}

export async function refreshGoldLayer() {
  const res = await fetch(`${API_BASE}/dashboard/gold/refresh`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to refresh gold layer");
  return res.json();
}

export async function getGoldDealsClosingSoon() {
  const res = await fetch(`${API_BASE}/dashboard/gold/deals-closing-soon`);
  if (!res.ok) throw new Error("Failed to fetch deals closing soon");
  return res.json();
}

export async function getGoldAtRiskAccounts() {
  const res = await fetch(`${API_BASE}/dashboard/gold/at-risk-accounts`);
  if (!res.ok) throw new Error("Failed to fetch at-risk accounts");
  return res.json();
}
