// App state on the page: `state` mirrors the Python snapshot (chu2/app/api.py),
// `ui` holds what only the page cares about. Band edits are sent at most every
// THROTTLE_MS; the last value always goes out. A band never has two set_band
// calls running at once: pywebview runs each call on its own thread, so two
// could reach Python in the wrong order and leave it with the older value.
import { reactive } from "./vendor/vue.esm-browser.prod.js";
import { call, onEvent } from "./bridge.js";

export const THROTTLE_MS = 50;

export const state = reactive({
  rev: -1,
  connected: false,
  device_error: null,
  eq_on: true,
  design: [],
  device_bands: [],
  stored: null,
  changes: 0,
  edited: false,
  auto_preamp: true,
  preamp: { preamp_db: 0, peak_db: 0, peak_hz: 20, device_peak_db: 0, method: "none",
            flipped: [], trim_index: null, warning: null },
  save: { state: "idle", kind: "save", step: null, reason: null, after_commit: false,
          mismatched: [], message: null },
  backup: null,
  name: "My EQ",
  quick: null,
  settings: { theme: "atelier", confirm_save: true },
  version: "",
});

export const ui = reactive({
  ready: false,
  selected: -1,       // band index the user works on, -1 = none
  dragIndex: -1,      // band index being dragged on the graph
  everConnected: false,
  explore: false,
  saveOpen: false,
  restoreOpen: false,
  closeRequest: null,
  toasts: [],
  canUndo: false,
  canRedo: false,
  mode: "build",        // "build" (Build PEQ) or "quick" (Quick Tune)
  quickBefore: null,    // the bands when Quick Tune was opened (the "before" curve)
  libraryOpen: false,
  shareOpen: false,
  shareTab: "import",   // "import" | "paste" | "export" | "share"
  sharePreview: null,   // an import preview waiting for "Import to editor"
  shareError: "",       // why the last import could not be read
  pasteText: "",
  settingsOpen: false,
});

// The preset library and the Quick Tune recipes (Api.get_library).
export const lib = reactive({ presets: [], recipes: null, loaded: false });

const pending = new Map();   // band index -> band waiting for the throttle
const inflight = new Set();  // band indexes with a set_band still running
const running = new Set();   // set_band promises not answered yet
let timer = null;
let lastFlush = -Infinity;
let toastId = 0;

// Undo / redo (brief §3.4): snapshots of the five bands. A burst of edits to
// one band (a drag, held arrow keys) is one step; an edit to another band or a
// pause of COALESCE_MS starts a new one.
const UNDO_LIMIT = 100;
const COALESCE_MS = 800;
const past = [];
const future = [];
let lastEdit = { index: null, at: -Infinity };

export function applySnapshot(snap) {
  if (!snap || typeof snap.rev !== "number" || snap.rev <= state.rev) return;
  // A band the user is still changing keeps its local value.
  const keep = state.design.map((band, i) =>
    pending.has(i) || inflight.has(i) || i === ui.dragIndex ? band : null);
  Object.assign(state, snap);
  keep.forEach((band, i) => {
    if (band) state.design[i] = band;
  });
  document.documentElement.dataset.theme = state.settings.theme; // tokens.css picks the colours
  if (snap.connected) ui.everConnected = true;
  ui.ready = true;
}

/** Show a message; `action` ({label, run}) adds one button, e.g. Undo. */
export function toast(text, kind = "info", action = null) {
  const id = ++toastId;
  ui.toasts.push({ id, text, kind, action });
  setTimeout(() => dismissToast(id), action ? 10000 : 6000);
}

export function dismissToast(id) {
  const at = ui.toasts.findIndex((t) => t.id === id);
  if (at >= 0) ui.toasts.splice(at, 1);
}

function report(err) {
  toast(String((err && err.message) || err), "warn");
}

const snapshot = () => state.design.map((b) => ({ ...b }));
// An undo step: the bands, the EQ's name (a preset or an import renames it) and
// the Quick Tune choice behind them, if any.
const entry = () => ({
  bands: snapshot(),
  name: state.name,
  quick: state.quick ? { scene: state.quick.scene, tweaks: [...state.quick.tweaks],
                         intensity: state.quick.intensity } : null,
});

function syncHistory() {
  ui.canUndo = past.length > 0;
  ui.canRedo = future.length > 0;
}

/** Remember the bands before an edit; `index` null always starts a new step. */
function remember(index) {
  const now = performance.now();
  const sameBurst = index !== null && index === lastEdit.index && now - lastEdit.at < COALESCE_MS;
  lastEdit = { index, at: now };
  if (sameBurst) return;
  past.push(entry());
  if (past.length > UNDO_LIMIT) past.shift();
  future.length = 0;
  syncHistory();
}

async function showDesign(step) {
  await flushEdits();
  state.design = step.bands.map((b) => ({ ...b }));
  state.name = step.name;
  await act("set_design", step.bands, step.name, step.quick);
}

export async function undo() {
  if (!past.length || state.save.state === "running") return;
  future.push(entry());
  const step = past.pop();
  lastEdit = { index: null, at: -Infinity };
  syncHistory();
  await showDesign(step);
}

export async function redo() {
  if (!future.length || state.save.state === "running") return;
  past.push(entry());
  const step = future.pop();
  lastEdit = { index: null, at: -Infinity };
  syncHistory();
  await showDesign(step);
}

/** Show `band` (already clamped and rounded, see eqmath.quantizeBand) and send it. */
export function setBand(index, band) {
  remember(index);
  state.design[index] = band;
  pending.set(index, band);
  schedule();
}

function schedule() {
  if (!timer) {
    const wait = Math.max(0, THROTTLE_MS - (performance.now() - lastFlush));
    timer = setTimeout(flush, wait);
  }
}

function flush() {
  timer = null;
  lastFlush = performance.now();
  for (const [index, band] of pending) {
    if (inflight.has(index)) continue; // sent when the running call for this band answers
    pending.delete(index);
    inflight.add(index);
    const job = call("set_band", index, band)
      .then((snap) => {
        inflight.delete(index);
        applySnapshot(snap);
      })
      .catch((err) => {
        inflight.delete(index);
        report(err);
      })
      .finally(() => {
        running.delete(job);
        if (pending.has(index)) schedule();
      });
    running.add(job);
  }
}

/** Send every waiting band edit and wait until Python has them all. */
export async function flushEdits() {
  while (pending.size || running.size) {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    flush();
    await Promise.all([...running]);
  }
}

async function act(method, ...args) {
  try {
    applySnapshot(await call(method, ...args));
  } catch (err) {
    report(err);
  }
}

export const refresh = () => act("get_state");
export const setEqEnabled = (on) => act("set_eq_enabled", on);
export const setAutoPreamp = (on) => act("set_auto_preamp", on);
export const freeSmallestBand = () => act("free_smallest_band");
export const cancelSave = () => act("cancel_save");
export const dismissSave = () => act("dismiss_save");
export const restoreOriginal = () => act("restore_original");

export async function resetBands() {
  remember(null);
  await flushEdits();
  await act("reset_bands");
}

async function libraryCall(method, ...args) {
  try {
    Object.assign(lib, await call(method, ...args), { loaded: true });
  } catch (err) {
    report(err);
  }
}

export const loadLibrary = () => libraryCall("get_library");
export const savePreset = (name, tags) => libraryCall("save_preset", name, tags);
export const renamePreset = (id, name) => libraryCall("rename_preset", id, name);
export const deletePreset = (id) => libraryCall("delete_preset", id);
export const setFavourite = (id, on) => libraryCall("set_favourite", id, on);
export const setSetting = (key, value) => act("set_setting", key, value);

export async function applyPreset(id) {
  remember(null);
  await flushEdits();
  await act("apply_preset", id);
}

export async function quickTune(scene, tweaks, intensity) {
  remember(null);
  await flushEdits();
  await act("quick_tune", scene, tweaks, intensity);
}

/** Import to editor: the preview's five bands, under the preview's name. */
export async function importBands(bands, name) {
  remember(null);
  await flushEdits();
  await act("set_design", bands, name);
}

/** Api calls that answer with a preview or a result instead of the state. */
export async function ask(method, ...args) {
  try {
    return await call(method, ...args);
  } catch (err) {
    report(err);
    return { error: String((err && err.message) || err) };
  }
}

/** Open the Presets sheet, Import & share or Settings; the other two close. */
export function openDialog(which) {
  ui.libraryOpen = which === "library";
  ui.settingsOpen = which === "settings";
  ui.shareOpen = which === "share";
  if (which !== "share") {
    ui.sharePreview = null;
    ui.shareError = "";
  }
}

export function setMode(mode) {
  if (mode === ui.mode) return;
  if (mode === "quick") {
    ui.quickBefore = snapshot();
    if (!lib.loaded) loadLibrary();
  }
  ui.mode = mode;
}

export async function save() {
  await flushEdits();
  await act("save");
}

export async function closeApp(action) {
  await flushEdits();
  await act("close_app", action);
}

export function start() {
  onEvent("state", applySnapshot);
  return refresh();
}
