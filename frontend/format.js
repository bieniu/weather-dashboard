// Polish date/time formatting and HTML escaping shared by the UI modules.
// Formatters capture the time zone when created, i.e. at module load.
export const TIME_FORMAT = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit" });
const DAY_ABBR = ["nie", "pon", "wto", "śro", "czw", "pią", "sob"];
const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** HH:mm for an ISO string or epoch milliseconds (chart points). */
export function formatTimestamp(value) {
  return TIME_FORMAT.format(new Date(value));
}

export function formatUpdated(isoString) {
  return `Zaktualizowano: ${new Date(isoString).toLocaleTimeString("pl-PL")}`;
}

export function getPolishDayAbbr(date) {
  return DAY_ABBR[date.getDay()];
}

/** Escapes a config-sourced string before it goes into an innerHTML template. */
export function esc(value) {
  return String(value).replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
}
