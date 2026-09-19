// EQ math for the page: RBJ biquads at 48 kHz, ported from chu2/eq.py
// (peaking, low_shelf, high_shelf), the CHU 2's limits, and log-axis helpers.
// tests/ui/test_ui_eqmath.py checks it against eq.py.

export const FS = 48000;
export const F_MIN = 20;
export const F_MAX = 20000;
export const GAIN_LIMIT = 12;
export const Q_MIN = 0.1;
export const Q_MAX = 10;
export const TYPES = ["peaking", "low_shelf", "high_shelf"];

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** Clamp to the CHU 2's limits and round to what it stores (1 Hz, 0.1 dB, Q 0.001). */
export function quantizeBand(b) {
  return {
    type: b.type,
    frequency: Math.round(clamp(b.frequency, F_MIN, F_MAX)),
    gain: Math.round(clamp(b.gain, -GAIN_LIMIT, GAIN_LIMIT) * 10) / 10 + 0,
    q: Math.round(clamp(b.q, Q_MIN, Q_MAX) * 1000) / 1000,
    bypass: !!b.bypass,
  };
}

function normalize(b0, b1, b2, a0, a1, a2) {
  return { b0: b0 / a0, b1: b1 / a0, b2: b2 / a0, a1: a1 / a0, a2: a2 / a0 };
}

/** Normalised biquad coefficients, as eq.py's *_coefficients functions. */
export function coefficients(band) {
  const A = Math.pow(10, band.gain / 40);
  const w0 = (2 * Math.PI * band.frequency) / FS;
  const c = Math.cos(w0);
  const s = Math.sin(w0);
  if (band.type === "peaking") {
    const alpha = s / (2 * band.q);
    return normalize(1 + alpha * A, -2 * c, 1 - alpha * A, 1 + alpha / A, -2 * c, 1 - alpha / A);
  }
  const alpha = (s / (2 * band.q)) * Math.SQRT2;
  const t = 2 * Math.sqrt(A) * alpha;
  if (band.type === "low_shelf") {
    return normalize(
      A * ((A + 1) - (A - 1) * c + t), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - t),
      (A + 1) + (A - 1) * c + t, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - t);
  }
  if (band.type === "high_shelf") {
    return normalize(
      A * ((A + 1) + (A - 1) * c + t), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - t),
      (A + 1) - (A - 1) * c + t, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - t);
  }
  throw new Error(`unknown band type ${band.type}`);
}

/** Level of one band at `f` Hz, in dB. */
export function bandDb(band, f) {
  const k = coefficients(band);
  const w = (2 * Math.PI * f) / FS;
  const c1 = Math.cos(w), s1 = Math.sin(w), c2 = Math.cos(2 * w), s2 = Math.sin(2 * w);
  const nRe = k.b0 + k.b1 * c1 + k.b2 * c2;
  const nIm = -(k.b1 * s1 + k.b2 * s2);
  const dRe = 1 + k.a1 * c1 + k.a2 * c2;
  const dIm = -(k.a1 * s1 + k.a2 * s2);
  return 10 * Math.log10((nRe * nRe + nIm * nIm) / (dRe * dRe + dIm * dIm));
}

/** Level of all bands together at `f` Hz, in dB. Bypassed bands play flat. */
export function curveDb(bands, f) {
  let total = 0;
  for (const band of bands) {
    if (!band.bypass && band.gain !== 0) total += bandDb(band, f);
  }
  return total;
}

/** `n` frequencies spread evenly on a log axis from `lo` to `hi`. */
export function logFreqs(n, lo = F_MIN, hi = F_MAX) {
  const a = Math.log10(lo), b = Math.log10(hi);
  return Array.from({ length: n }, (_, i) => Math.pow(10, a + ((b - a) * i) / (n - 1)));
}

/** Position of `f` on a log axis from x0 (20 Hz) to x1 (20 kHz). */
export function xOfFreq(f, x0, x1) {
  const a = Math.log10(F_MIN), b = Math.log10(F_MAX);
  return x0 + ((Math.log10(f) - a) / (b - a)) * (x1 - x0);
}

export function freqOfX(x, x0, x1) {
  const a = Math.log10(F_MIN), b = Math.log10(F_MAX);
  return Math.pow(10, a + ((x - x0) / (x1 - x0)) * (b - a));
}

/** Position of `gain` dB between y0 (+range) and y1 (-range). */
export function yOfGain(gain, y0, y1, range) {
  return y0 + ((range - gain) / (2 * range)) * (y1 - y0);
}

export function gainOfY(y, y0, y1, range) {
  return range - ((y - y0) / (y1 - y0)) * 2 * range;
}

/** Width of a peak in octaves between its -3 dB points (for the Q whiskers). */
export function bandwidthOctaves(q) {
  return (2 / Math.LN2) * Math.asinh(1 / (2 * q));
}
