/**
 * FPL prices and bank are transmitted as tenths of a million (e.g. 105 ==
 * £10.5m). These helpers match the formatting already used by frontend/src/App.tsx
 * so the web and mobile clients render identical numbers.
 */
export function formatMoney(tenths: number | null | undefined): string {
  return tenths == null ? "–" : `£${(tenths / 10).toFixed(1)}m`;
}

export function formatPoints(value: number | null | undefined, digits = 2): string {
  return value == null ? "–" : value.toFixed(digits);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  return value == null ? "–" : `${value.toFixed(digits)}%`;
}

export function formatSigned(value: number, digits = 1, suffix = ""): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}${suffix}`;
}

export function formatRank(value: number | null | undefined): string {
  return value == null ? "–" : new Intl.NumberFormat("nb-NO").format(value);
}

export function formatHoursRemaining(hours: number | null | undefined): string {
  return hours == null ? "–" : `${hours.toFixed(1)} t`;
}

const DATE_FORMATTER = new Intl.DateTimeFormat("nb-NO", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDeadline(isoDate: string): string {
  return DATE_FORMATTER.format(new Date(isoDate));
}
