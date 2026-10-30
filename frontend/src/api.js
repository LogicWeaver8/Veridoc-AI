const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function buildQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function request(path, { method = "GET", body, signal } = {}) {
  const options = { method, signal, headers: {} };

  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(
      "Cannot reach the VeriDox API. Check that the backend is running on port 8000.",
      0,
    );
  }

  if (response.status === 204) return null;

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : null;

  if (!response.ok) {
    const message =
      payload?.error?.message || `The request failed with status ${response.status}.`;
    throw new ApiError(message, response.status, payload?.error?.details);
  }

  return payload;
}

function uploadForm(files, fields = {}) {
  const form = new FormData();
  const list = Array.isArray(files) ? files : [files];
  const fieldName = list.length > 1 ? "files" : "file";
  list.forEach((file) => form.append(fieldName, file, file.name));
  Object.entries(fields).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      form.append(key, value);
    }
  });
  return form;
}

export const api = {
  health: () => request("/health"),
  stats: () => request("/api/stats"),
  appSettings: () => request("/api/system/settings"),
  indexStatus: () => request("/api/index/status"),
  rebuildIndex: () => request("/api/index/rebuild", { method: "POST" }),

  listDocuments: (params = {}) => request(`/api/documents${buildQuery(params)}`),
  getDocument: (documentId) => request(`/api/documents/${documentId}`),
  deleteDocument: (documentId) =>
    request(`/api/documents/${documentId}`, { method: "DELETE" }),
  uploadDocument: (file, fields = {}) =>
    request("/api/documents/upload", { method: "POST", body: uploadForm(file, fields) }),
  uploadDocuments: (files) =>
    request("/api/documents/upload-multiple", {
      method: "POST",
      body: uploadForm(files),
    }),
  addVersion: (documentId, file, fields = {}) =>
    request(`/api/documents/${documentId}/versions`, {
      method: "POST",
      body: uploadForm(file, fields),
    }),

  listConversations: () => request("/api/chat/conversations"),
  createConversation: (title) =>
    request("/api/chat/conversations", {
      method: "POST",
      body: title ? { title } : {},
    }),
  getConversation: (conversationId) => request(`/api/chat/conversations/${conversationId}`),
  deleteConversation: (conversationId) =>
    request(`/api/chat/conversations/${conversationId}`, { method: "DELETE" }),
  ask: (payload) => request("/api/chat/ask", { method: "POST", body: payload }),

  listBatchJobs: () => request("/api/batch/jobs"),
  uploadBatch: (file) =>
    request("/api/batch/upload", { method: "POST", body: uploadForm(file) }),
  getBatchJob: (jobId) => request(`/api/batch/${jobId}/status`),
  batchDownloadUrl: (jobId) => `${API_BASE}/api/batch/${jobId}/download`,
};
