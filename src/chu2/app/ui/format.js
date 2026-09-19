// Numbers and words the page shows (brief §5.2, §7): tabular numbers, a real
// minus sign, a thin space before units, plain English.

const MINUS = "−";
const THIN = " ";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const TYPE_LABEL = { peaking: "Peak", low_shelf: "Low shelf", high_shelf: "High shelf" };

/** "+3.0", "−2.5", "0.0" */
export function signed(value, digits = 1) {
  const text = Math.abs(value).toFixed(digits);
  if (Number(text) === 0) return text;
  return (value > 0 ? "+" : MINUS) + text;
}

/** "105 Hz", "1.40 kHz", "10 kHz", "12.5 kHz" */
export function formatFreq(f) {
  if (f >= 10000) return `${(f / 1000).toFixed(1).replace(/\.0$/, "")}${THIN}kHz`;
  if (f >= 1000) return `${(f / 1000).toFixed(2)}${THIN}kHz`;
  return `${Math.round(f)}${THIN}Hz`;
}

export function formatGain(gain) {
  return `${signed(gain)}${THIN}dB`;
}

export function formatQ(q) {
  return q.toFixed(2);
}

/** "6", "6.5": a level change in words ("turn your volume up about 6 dB"). */
export function amount(db) {
  return Math.abs(db).toFixed(1).replace(/\.0$/, "");
}

/** Hover chip: "2 · Peak · 250 Hz · −2.0 dB · Q 1.00" */
export function chipText(index, b) {
  return `${index + 1} · ${TYPE_LABEL[b.type]} · ${formatFreq(b.frequency)} · ${formatGain(b.gain)} · Q ${formatQ(b.q)}`;
}

/** Screen reader: "Band 2, Peak, 250 hertz, minus 2.0 decibels, Q 1.00" */
export function describeBand(index, b) {
  const sign = b.gain < 0 ? "minus " : b.gain > 0 ? "plus " : "";
  const bypass = b.bypass ? ", bypassed" : "";
  return `Band ${index + 1}, ${TYPE_LABEL[b.type]}, ${Math.round(b.frequency)} hertz, ` +
    `${sign}${Math.abs(b.gain).toFixed(1)} decibels, Q ${formatQ(b.q)}${bypass}`;
}

/** "19 Sep 2026, 14:02" from "2026-09-19T14:02:00" (local time) */
export function formatDate(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
