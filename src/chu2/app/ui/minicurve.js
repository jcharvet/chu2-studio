// A small curve for preset cards and previews: the plate, the 0 dB line, an
// optional "before" curve (stone) and the preset's curve (jade). Colours come
// from the theme tokens, like the main graph.
import { ref, watch, onMounted, onBeforeUnmount } from "./vendor/vue.esm-browser.prod.js";
import { state } from "./store.js";
import * as m from "./eqmath.js";

const RANGE = 12;
const FREQS = m.logFreqs(80);
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export const MiniCurve = {
  props: {
    bands: { type: Array, required: true },
    before: { type: Array, default: null },
    height: { type: Number, default: 56 },
  },
  setup(props) {
    const canvas = ref(null);
    let frame = 0;
    let observer = null;

    function line(bands, color, width) {
      const el = canvas.value;
      const w = el.clientWidth, h = props.height;
      const ctx = el.getContext("2d");
      ctx.beginPath();
      FREQS.forEach((f, i) => {
        const x = m.xOfFreq(f, 2, w - 2);
        const y = m.yOfGain(Math.max(-RANGE, Math.min(RANGE, m.curveDb(bands, f))), 2, h - 2, RANGE);
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke();
    }

    function draw() {
      frame = 0;
      const el = canvas.value;
      if (!el || !el.clientWidth) return;
      const dpr = window.devicePixelRatio || 1;
      const w = el.clientWidth, h = props.height;
      el.width = Math.round(w * dpr); el.height = Math.round(h * dpr);
      const ctx = el.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = cssVar("--plate");
      ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = `rgba(${cssVar("--text-rgb")}, .18)`; ctx.lineWidth = 1;
      const zero = Math.round(m.yOfGain(0, 2, h - 2, RANGE)) + 0.5;
      ctx.beginPath(); ctx.moveTo(0, zero); ctx.lineTo(w, zero); ctx.stroke();
      if (props.before) line(props.before, cssVar("--stone"), 1.25);
      line(props.bands, cssVar("--jade"), 2);
    }

    function requestDraw() {
      if (!frame) frame = requestAnimationFrame(draw);
    }

    watch(() => [props.bands, props.before, state.settings], requestDraw, { deep: true });
    onMounted(() => {
      observer = new ResizeObserver(requestDraw);
      observer.observe(canvas.value);
      requestDraw();
    });
    onBeforeUnmount(() => {
      if (observer) observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    });
    return { canvas };
  },
  template: `<canvas ref="canvas" class="mini-curve" :style="{ height: height + 'px' }" aria-hidden="true"></canvas>`,
};
