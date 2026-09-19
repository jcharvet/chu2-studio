// The EQ graph (brief §3, EQ-only view): a DPR-aware canvas redrawn on
// requestAnimationFrame. Five fixed nodes; drag = frequency/gain, wheel over a
// node = Q, keyboard per brief §3.7. Invisible DOM nodes mirror the canvas
// nodes for screen readers (and give tests something to find).
// Props: `readonly` (Quick Tune: nodes are shown, not dragged) and `before`
// (five bands drawn as a stone "before" curve under the result).
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from "./vendor/vue.esm-browser.prod.js";
import { state, ui, setBand } from "./store.js";
import * as m from "./eqmath.js";
import { chipText, describeBand } from "./format.js";

const PAD = { left: 44, right: 16, top: 16, bottom: 48 };
const RANGE = 15; // ±15 dB, grid and labels every 3 dB
const LABELS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
const MAJOR = [100, 1000, 10000];
const REGIONS = [["Sub-bass", 20, 60], ["Bass", 60, 250], ["Low-mids", 250, 500],
  ["Mids", 500, 2000], ["Presence", 2000, 6000], ["Treble", 6000, 10000], ["Air", 10000, 20000]];
const NODE_R = 9; // 18 px node
const HIT_R = 16; // 32 px hit target (WCAG 2.5.8)
const Q_STEP = Math.pow(2, 1 / 6);
const Q_FINE = Math.pow(2, 1 / 24);
const FREQS = m.logFreqs(240);
const FONT = "11px Inter, 'Segoe UI', sans-serif";

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const axisLabel = (f) => (f >= 1000 ? `${f / 1000}k` : String(f));
const dbLabel = (g) => (g > 0 ? `+${g}` : g < 0 ? `−${-g}` : "0");

export const EqGraph = {
  props: {
    readonly: { type: Boolean, default: false },
    before: { type: Array, default: null },
  },
  setup(props) {
    const wrap = ref(null);
    const canvas = ref(null);
    const size = reactive({ w: 0, h: 0 });
    const hover = ref(-1);
    const limit = ref(false);
    const announcement = ref("");
    let ctx = null;
    let colors = null; // read from the theme's tokens on every draw
    let frame = 0;
    let observer = null;
    let drag = null;
    let sayTimer = null;
    let lastSaid = -Infinity;

    const box = () => ({ x0: PAD.left, x1: size.w - PAD.right, y0: PAD.top, y1: size.h - PAD.bottom });
    const xOf = (f) => { const b = box(); return m.xOfFreq(f, b.x0, b.x1); };
    const yOf = (g) => { const b = box(); return m.yOfGain(g, b.y0, b.y1, RANGE); };
    const fOf = (x) => { const b = box(); return m.freqOfX(x, b.x0, b.x1); };
    const gOf = (y) => { const b = box(); return m.gainOfY(y, b.y0, b.y1, RANGE); };
    const nodeX = (i) => xOf(state.design[i].frequency);
    const nodeY = (i) => yOf(state.design[i].gain);

    function hit(x, y) {
      const near = (i) => Math.hypot(nodeX(i) - x, nodeY(i) - y) <= HIT_R;
      if (ui.selected >= 0 && near(ui.selected)) return ui.selected;
      let best = -1;
      let bestD = HIT_R;
      state.design.forEach((_, i) => {
        const d = Math.hypot(nodeX(i) - x, nodeY(i) - y);
        if (d <= bestD) { best = i; bestD = d; }
      });
      return best;
    }

    // ---- drawing ---------------------------------------------------------- //
    function requestDraw() {
      if (!frame) frame = requestAnimationFrame(draw);
    }

    function line(x1, y1, x2, y2) {
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }

    function draw() {
      frame = 0;
      const el = canvas.value;
      if (!el || size.w < 2 * (PAD.left + PAD.right) || size.h < PAD.top + PAD.bottom + 40) return;
      const dpr = window.devicePixelRatio || 1;
      const pw = Math.round(size.w * dpr), ph = Math.round(size.h * dpr);
      if (el.width !== pw || el.height !== ph) { el.width = pw; el.height = ph; }
      ctx = ctx || el.getContext("2d");
      colors = {
        plate: cssVar("--plate"), jade: cssVar("--jade"), amber: cssVar("--amber"), warn: cssVar("--warn"),
        text: cssVar("--text"), text3: cssVar("--text-3"), stone: cssVar("--stone"),
        node: cssVar("--node-fill"), onAmber: cssVar("--on-amber"),
        textRgb: cssVar("--text-rgb"), jadeRgb: cssVar("--jade-rgb"), amberRgb: cssVar("--amber-rgb"),
        warnRgb: cssVar("--warn-rgb"),
      };
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size.w, size.h);
      const b = box();
      drawGrid(b);
      ctx.save();
      ctx.beginPath(); ctx.rect(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0); ctx.clip();
      drawShapes();
      drawCurve();
      ctx.restore();
      drawWhiskers();
      drawNodes();
    }

    function drawGrid(b) {
      ctx.fillStyle = colors.plate;
      ctx.fillRect(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0);
      ctx.lineWidth = 1;
      const vline = (f, color) => {
        const x = Math.round(xOf(f)) + 0.5;
        ctx.strokeStyle = color; line(x, b.y0, x, b.y1);
      };
      const hline = (g, color) => {
        const y = Math.round(yOf(g)) + 0.5;
        ctx.strokeStyle = color; line(b.x0, y, b.x1, y);
      };
      for (let decade = 10; decade <= 10000; decade *= 10) {
        for (let k = 1; k <= 9; k++) {
          const f = k * decade;
          if (f >= m.F_MIN && f <= m.F_MAX) vline(f, `rgba(${colors.textRgb}, .05)`);
        }
      }
      for (const f of MAJOR.concat(REGIONS.slice(1).map((r) => r[1]))) vline(f, `rgba(${colors.textRgb}, .10)`);
      for (let g = -RANGE; g <= RANGE; g += 3) {
        hline(g, `rgba(${colors.textRgb}, ${g === 0 ? ".22" : ".05"})`);
      }
      ctx.setLineDash([4, 4]);
      hline(m.GAIN_LIMIT, `rgba(${colors.warnRgb}, .35)`); // the CHU 2's ±12 dB rails
      hline(-m.GAIN_LIMIT, `rgba(${colors.warnRgb}, .35)`);
      ctx.setLineDash([]);

      ctx.font = `500 ${FONT}`;
      ctx.fillStyle = colors.text3;
      ctx.textAlign = "right"; ctx.textBaseline = "middle";
      for (let g = -RANGE; g <= RANGE; g += 3) ctx.fillText(dbLabel(g), b.x0 - 8, yOf(g));
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      for (const f of LABELS) ctx.fillText(axisLabel(f), xOf(f), b.y1 + 6);
      const ry = b.y1 + 26; // region ribbon, 20 px tall
      for (const [name, lo, hi] of REGIONS) {
        const xa = xOf(lo), xb = xOf(hi);
        ctx.fillStyle = `rgba(${colors.textRgb}, .03)`;
        ctx.fillRect(xa + 1, ry, xb - xa - 2, 20);
        ctx.fillStyle = colors.text3;
        if (ctx.measureText(name).width < xb - xa - 6) ctx.fillText(name, (xa + xb) / 2, ry + 4);
      }
    }

    function path(levelAt) {
      ctx.beginPath();
      FREQS.forEach((f, i) => {
        const x = xOf(f), y = yOf(levelAt(f));
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
    }

    function shape(band, stroke, fill, width) {
      if (band.bypass) return; // a bypassed band is hidden from the result
      path((f) => m.bandDb(band, f));
      ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.stroke();
      const y0 = yOf(0);
      ctx.lineTo(xOf(m.F_MAX), y0); ctx.lineTo(xOf(m.F_MIN), y0); ctx.closePath();
      ctx.fillStyle = fill; ctx.fill();
    }

    function drawShapes() {
      const h = hover.value;
      if (h >= 0 && h !== ui.selected) {
        shape(state.design[h], `rgba(${colors.textRgb}, .45)`, `rgba(${colors.textRgb}, .06)`, 1);
      }
      if (ui.selected >= 0) shape(state.design[ui.selected], colors.amber, `rgba(${colors.amberRgb}, .12)`, 1.5);
    }

    function drawCurve() {
      if (props.before) {
        path((f) => m.curveDb(props.before, f));
        ctx.strokeStyle = colors.stone; ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      path((f) => m.curveDb(state.design, f));
      ctx.strokeStyle = colors.jade; ctx.lineWidth = 2.5;
      ctx.shadowColor = `rgba(${colors.jadeRgb}, .30)`; ctx.shadowBlur = 6;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    function drawWhiskers() {
      const i = ui.selected;
      if (i < 0) return;
      const band = state.design[i];
      if (band.type !== "peaking" || band.bypass) return;
      const half = m.bandwidthOctaves(band.q) / 2;
      const xa = xOf(Math.max(m.F_MIN, band.frequency / Math.pow(2, half)));
      const xb = xOf(Math.min(m.F_MAX, band.frequency * Math.pow(2, half)));
      const y = nodeY(i);
      ctx.strokeStyle = colors.amber; ctx.lineWidth = 1.5;
      line(xa, y, xb, y); line(xa, y - 4, xa, y + 4); line(xb, y - 4, xb, y + 4);
    }

    function drawNode(i) {
      const band = state.design[i];
      const x = nodeX(i), y = nodeY(i);
      const selected = i === ui.selected, hovered = i === hover.value;
      const idle = band.gain === 0 && !band.bypass;
      const r = NODE_R * (hovered && !selected ? 1.1 : 1);
      const ring = selected ? colors.amber
        : band.bypass ? `rgba(${colors.textRgb}, .40)`
        : idle ? `rgba(${colors.textRgb}, .35)` : colors.jade;
      ctx.globalAlpha = ui.selected >= 0 && !selected ? 0.6 : 1;
      if (selected) {
        ctx.fillStyle = `rgba(${colors.amberRgb}, .18)`;
        ctx.beginPath(); ctx.arc(x, y, 14, 0, 2 * Math.PI); ctx.fill();
      }
      if ((band.gain > 6 || (band.q > 4 && band.gain > 0) || (limit.value && i === ui.dragIndex)) && !band.bypass) {
        ctx.strokeStyle = colors.warn; ctx.lineWidth = 1.5; ctx.setLineDash([2, 3]);
        ctx.beginPath(); ctx.arc(x, y, r + 4, 0, 2 * Math.PI); ctx.stroke();
        ctx.setLineDash([]);
      }
      ctx.strokeStyle = ring; ctx.lineWidth = 2;
      if (band.type === "low_shelf") line(x - r - 6, y, x - r, y);
      if (band.type === "high_shelf") line(x + r, y, x + r + 6, y);
      ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = selected ? colors.amber : colors.node; ctx.fill();
      if (band.bypass) ctx.setLineDash([3, 3]);
      ctx.lineWidth = hovered ? 2.5 : 2; ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = selected ? colors.onAmber : idle || band.bypass ? `rgba(${colors.textRgb}, .55)` : colors.text;
      ctx.font = `600 ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(String(i + 1), x, y + 0.5);
      if (band.bypass) { ctx.strokeStyle = ring; ctx.lineWidth = 1.5; line(x - 5, y + 5, x + 5, y - 5); }
      ctx.globalAlpha = 1;
    }

    function drawNodes() {
      state.design.forEach((_, i) => { if (i !== ui.selected) drawNode(i); });
      if (ui.selected >= 0) drawNode(ui.selected); // on top
    }

    // ---- editing ---------------------------------------------------------- //
    function say(i) {
      clearTimeout(sayTimer);
      const speak = () => { lastSaid = performance.now(); announcement.value = describeBand(i, state.design[i]); };
      const wait = 250 - (performance.now() - lastSaid);
      if (wait <= 0) speak(); else sayTimer = setTimeout(speak, wait);
    }

    function update(i, patch) {
      setBand(i, m.quantizeBand({ ...state.design[i], ...patch }));
      say(i);
    }

    function local(e) {
      const r = canvas.value.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    }

    function onPointerDown(e) {
      if (e.button !== 0) return;
      const p = local(e);
      const i = hit(p.x, p.y);
      wrap.value.focus({ preventScroll: true });
      if (i < 0) { ui.selected = -1; return; }
      if (props.readonly) { ui.selected = i; return; }
      e.preventDefault();
      ui.selected = i;
      ui.dragIndex = i;
      drag = { index: i, sx: p.x, sy: p.y, lastX: p.x, lastY: p.y, nx: nodeX(i), ny: nodeY(i),
               moved: false, axis: null };
      canvas.value.setPointerCapture(e.pointerId);
      say(i);
    }

    function onPointerMove(e) {
      const p = local(e);
      if (!drag) {
        const i = hit(p.x, p.y);
        if (i !== hover.value) hover.value = i;
        canvas.value.style.cursor = i >= 0 && !props.readonly ? "grab" : "default";
        return;
      }
      if (!drag.moved && Math.hypot(p.x - drag.sx, p.y - drag.sy) < 3) return;
      drag.moved = true;
      const scale = e.shiftKey ? 0.25 : 1; // Shift = fine
      drag.nx += (p.x - drag.lastX) * scale;
      drag.ny += (p.y - drag.lastY) * scale;
      drag.lastX = p.x; drag.lastY = p.y;
      if (e.ctrlKey || e.altKey) { // lock to the axis the drag started on
        if (!drag.axis) drag.axis = Math.abs(p.x - drag.sx) >= Math.abs(p.y - drag.sy) ? "x" : "y";
      } else {
        drag.axis = null;
      }
      const band = state.design[drag.index];
      const f = drag.axis === "y" ? band.frequency : fOf(drag.nx);
      const g = drag.axis === "x" ? band.gain : gOf(drag.ny);
      limit.value = f < m.F_MIN || f > m.F_MAX || Math.abs(g) > m.GAIN_LIMIT;
      canvas.value.style.cursor = "grabbing";
      update(drag.index, { frequency: f, gain: g });
    }

    function onPointerUp(e) {
      if (!drag) return;
      if (!drag.moved && e.altKey) update(drag.index, { bypass: !state.design[drag.index].bypass });
      if (canvas.value.hasPointerCapture(e.pointerId)) canvas.value.releasePointerCapture(e.pointerId);
      drag = null;
      ui.dragIndex = -1;
      limit.value = false;
      canvas.value.style.cursor = "grab";
      requestDraw();
    }

    function onPointerLeave() {
      if (!drag) hover.value = -1;
    }

    function onWheel(e) {
      if (props.readonly) return;
      const p = local(e);
      const i = hit(p.x, p.y);
      if (i < 0) return; // wheel elsewhere does nothing
      e.preventDefault();
      const delta = e.deltaY || e.deltaX; // Shift+wheel scrolls sideways on Windows
      const step = e.shiftKey ? Q_FINE : Q_STEP;
      const band = state.design[i];
      ui.selected = i;
      update(i, { q: delta < 0 ? band.q * step : band.q / step });
    }

    function onFocus() {
      if (ui.selected < 0) ui.selected = 0;
    }

    function onKeyDown(e) {
      if (/^[1-5]$/.test(e.key) && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        ui.selected = Number(e.key) - 1;
        say(ui.selected);
        return;
      }
      if (e.key === "Escape") {
        if (ui.selected >= 0) { e.preventDefault(); ui.selected = -1; }
        return;
      }
      const i = ui.selected;
      if (i < 0 || props.readonly) return;
      const b = state.design[i];
      const oct = e.shiftKey ? 1 / 3 : 1 / 24;
      let patch = null;
      switch (e.key) {
        case "ArrowRight":
        case "ArrowLeft": {
          const dir = e.key === "ArrowRight" ? 1 : -1;
          let f = e.ctrlKey ? b.frequency + dir : b.frequency * Math.pow(2, dir * oct);
          f = dir > 0 ? Math.max(f, b.frequency + 1) : Math.min(f, b.frequency - 1); // always move
          patch = { frequency: f };
          break;
        }
        case "ArrowUp":
        case "ArrowDown":
          patch = { gain: b.gain + (e.key === "ArrowUp" ? 1 : -1) * (e.shiftKey ? 1 : 0.1) };
          break;
        case "PageUp": case "]": case "}":
          patch = { q: b.q * (e.shiftKey ? Q_FINE : Q_STEP) };
          break;
        case "PageDown": case "[": case "{":
          patch = { q: b.q / (e.shiftKey ? Q_FINE : Q_STEP) };
          break;
        case "t": case "T":
          patch = { type: m.TYPES[(m.TYPES.indexOf(b.type) + 1) % m.TYPES.length] };
          break;
        case "b": case "B":
          patch = { bypass: !b.bypass };
          break;
        case "0": case "Backspace":
          patch = { gain: 0 };
          break;
        default:
          return;
      }
      e.preventDefault();
      update(i, patch);
    }

    const chipIndex = computed(() => (ui.dragIndex >= 0 ? ui.dragIndex : hover.value));
    const chipLabel = computed(() => {
      const i = chipIndex.value;
      if (i < 0 || !state.design[i]) return "";
      return chipText(i, state.design[i]) + (limit.value && i === ui.dragIndex ? " · limit" : "");
    });
    const chipStyle = computed(() => {
      const i = chipIndex.value;
      return i < 0 ? {} : { left: `${nodeX(i)}px`, top: `${nodeY(i)}px` };
    });
    const activeId = computed(() => (ui.selected >= 0 ? `graph-node-${ui.selected + 1}` : null));

    watch(() => [state.design, state.settings, props.before, props.readonly, ui.selected, ui.dragIndex,
      hover.value, limit.value, size.w, size.h], requestDraw, { deep: true });

    onMounted(() => {
      observer = new ResizeObserver(([entry]) => {
        size.w = entry.contentRect.width;
        size.h = entry.contentRect.height;
      });
      observer.observe(wrap.value);
      document.fonts.ready.then(requestDraw);
    });
    onBeforeUnmount(() => {
      if (observer) observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
      clearTimeout(sayTimer);
    });

    return {
      state, ui, wrap, canvas, size, announcement, chipIndex, chipLabel, chipStyle, activeId,
      nodeX, nodeY, describeBand,
      onPointerDown, onPointerMove, onPointerUp, onPointerLeave, onWheel, onFocus, onKeyDown,
    };
  },
  template: `
    <div class="graph" ref="wrap" tabindex="0" role="group" aria-roledescription="EQ graph"
:aria-label="readonly ? 'EQ graph, before and after. Switch to Build PEQ to move the bands.'
           : 'EQ graph. Keys 1 to 5 pick a band, arrows move it, brackets change its width.'"
         :aria-activedescendant="activeId" @focus="onFocus" @keydown="onKeyDown">
      <canvas ref="canvas" class="graph-canvas" aria-hidden="true"
              @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp"
              @pointercancel="onPointerUp" @pointerleave="onPointerLeave" @wheel="onWheel"></canvas>
      <div v-for="(b, i) in state.design" :key="i" class="graph-node" :id="'graph-node-' + (i + 1)"
           :data-node="i + 1" role="group" :aria-label="describeBand(i, b)"
           :style="{ left: nodeX(i) + 'px', top: nodeY(i) + 'px' }"></div>
      <div v-if="chipIndex >= 0" class="graph-chip" :style="chipStyle">{{ chipLabel }}</div>
      <div class="sr-only" aria-live="polite" data-test="graph-live">{{ announcement }}</div>
    </div>`,
};
