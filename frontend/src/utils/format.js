const STATUS_LABELS = {
  uploaded: "Queued",
  extracting: "Extracting",
  chunking: "Chunking",
  embedding: "Embedding",
  indexing: "Indexing",
  completed: "Processed",
  failed: "Failed",
  active: "Active",
  superseded: "Superseded",
  pending: "Pending",
  processing: "Processing",
  queued: "Queued",
  answered: "Answered",
  partially_answered: "Partially answered",
  not_covered: "Not covered",
};

const STATUS_TONES = {
  uploaded: "neutral",
  extracting: "info",
  chunking: "info",
  embedding: "info",
  indexing: "info",
  completed: "success",
  failed: "danger",
  active: "success",
  superseded: "neutral",
  pending: "neutral",
  processing: "info",
  queued: "neutral",
  answered: "success",
  partially_answered: "warning",
  not_covered: "neutral",
};

export function statusLabel(status) {
  if (!status) return "Unknown";
  return STATUS_LABELS[status] || status.replaceAll("_", " ");
}

export function statusTone(status) {
  return STATUS_TONES[status] || "neutral";
}

export function isProcessingStatus(status) {
  return ["uploaded", "extracting", "chunking", "embedding", "indexing"].includes(status);
}

export function formatDate(value, withTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const options = { year: "numeric", month: "short", day: "numeric" };
  if (withTime) {
    options.hour = "2-digit";
    options.minute = "2-digit";
  }
  return date.toLocaleString(undefined, options);
}

export function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function formatRelative(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const divisions = [
    { amount: 60, unit: "second" },
    { amount: 60, unit: "minute" },
    { amount: 24, unit: "hour" },
    { amount: 7, unit: "day" },
    { amount: 4.34524, unit: "week" },
    { amount: 12, unit: "month" },
    { amount: Number.POSITIVE_INFINITY, unit: "year" },
  ];
  let duration = seconds;
  for (const division of divisions) {
    if (Math.abs(duration) < division.amount) {
      return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
        Math.round(duration),
        division.unit,
      );
    }
    duration /= division.amount;
  }
  return "";
}

export function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`;
}

export function truncate(text, length = 120) {
  if (!text) return "";
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

export function confidenceTone(confidence) {
  if (confidence == null) return "neutral";
  if (confidence >= 80) return "success";
  if (confidence >= 50) return "warning";
  return "danger";
}

export function pluralize(count, singular, plural) {
  return `${count} ${count === 1 ? singular : plural || `${singular}s`}`;
}
