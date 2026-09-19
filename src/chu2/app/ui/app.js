// The Vue root. Components are plain objects with template strings, compiled
// by the vendored full build of Vue (no Node, no build step).
import { computed, createApp } from "./vendor/vue.esm-browser.prod.js";
import { state, ui, start, dismissToast, setEqEnabled, undo, redo, setMode, openDialog } from "./store.js";
import { EqGraph } from "./graph.js";
import { TopBar } from "./topbar.js";
import { BandCards } from "./bands.js";
import { HeadroomBar } from "./headroom.js";
import { SavePanel, openSave } from "./savepanel.js";
import { RestoreDialog, CloseDialog } from "./dialogs.js";
import { NoDevice, StatusBanner } from "./nodevice.js";
import { QuickPanel, WhatChanged } from "./quick.js";
import { PresetSheet } from "./presets.js";
import { ShareDialog, openShare, closeShare } from "./share.js";
import { SettingsDialog } from "./settings.js";

// Global keys (brief §3.7): Ctrl+S save, Ctrl+Z / Ctrl+Y (or Ctrl+Shift+Z) undo / redo,
// Ctrl+1 Quick Tune, Ctrl+3 Build PEQ, Ctrl+P presets, Ctrl+I import, Ctrl+Shift+S share code,
// Ctrl+, settings, A = EQ on/off, Esc closes a dialog.
// In a text field, Ctrl+Z stays the field's own undo.
function onKey(e) {
  const typing = e.target instanceof Element &&
    e.target.closest("textarea, select, input[type=text], input[type=number], input[type=search]");
  const key = e.key.toLowerCase();
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && key === "s") {
    e.preventDefault();
    if (e.shiftKey) openShare("share");
    else openSave();
  } else if (ctrl && key === "i") {
    e.preventDefault();
    openShare("import");
  } else if (ctrl && !typing && (key === "z" || key === "y")) {
    e.preventDefault();
    if (key === "y" || e.shiftKey) redo();
    else undo();
  } else if (ctrl && (key === "1" || key === "3")) {
    e.preventDefault();
    setMode(key === "1" ? "quick" : "build");
  } else if (ctrl && key === "p") {
    e.preventDefault();
    openDialog("library");
  } else if (ctrl && key === ",") {
    e.preventDefault();
    openDialog("settings");
  } else if (e.key === "Escape") {
    if (ui.closeRequest) ui.closeRequest = null;
    else if (ui.libraryOpen) ui.libraryOpen = false;
    else if (ui.shareOpen) closeShare();
    else if (ui.settingsOpen) ui.settingsOpen = false;
    else if (ui.restoreOpen) ui.restoreOpen = false;
    else if (ui.saveOpen && state.save.state === "idle") ui.saveOpen = false;
  } else if (!typing && !ctrl && !e.altKey && key === "a" && state.connected) {
    setEqEnabled(!state.eq_on);
  }
}

const App = {
  components: { EqGraph, TopBar, BandCards, HeadroomBar, SavePanel, RestoreDialog, CloseDialog, NoDevice,
                StatusBanner, QuickPanel, WhatChanged, PresetSheet, ShareDialog, SettingsDialog },
  setup() {
    // S0 until a CHU 2 was seen or the user chose to explore without one.
    const noDevice = computed(() => !state.connected && !ui.explore && !ui.everConnected);
    return { state, ui, noDevice, dismissToast };
  },
  template: `
    <div class="app" :data-ready="ui.ready ? 'true' : 'false'">
      <template v-if="ui.ready">
        <no-device v-if="noDevice"></no-device>
        <template v-else>
          <top-bar></top-bar>
          <main :class="['studio', ui.mode === 'quick' ? 'studio-quick' : '']" :inert="state.save.state === 'running'">
            <quick-panel v-if="ui.mode === 'quick'"></quick-panel>
            <section class="graph-panel" aria-label="EQ graph">
              <status-banner></status-banner>
              <eq-graph :readonly="ui.mode === 'quick'" :before="ui.mode === 'quick' ? ui.quickBefore : null"></eq-graph>
              <headroom-bar></headroom-bar>
            </section>
            <aside class="band-panel" :aria-label="ui.mode === 'quick' ? 'What changed' : 'Bands'">
              <what-changed v-if="ui.mode === 'quick'"></what-changed>
              <band-cards v-else></band-cards>
            </aside>
          </main>
          <save-panel></save-panel>
          <restore-dialog></restore-dialog>
          <close-dialog></close-dialog>
          <preset-sheet></preset-sheet>
          <share-dialog></share-dialog>
          <settings-dialog></settings-dialog>
        </template>
      </template>
      <div class="toasts">
        <div v-for="t in ui.toasts" :key="t.id" :class="['toast', 'dialog', 'toast-' + t.kind]" role="status">
          <span>{{ t.text }}</span>
          <button v-if="t.action" type="button" class="btn btn-small" data-test="toast-action"
                  @click="t.action.run(); dismissToast(t.id)">{{ t.action.label }}</button>
          <button type="button" class="icon-btn" aria-label="Dismiss" @click="dismissToast(t.id)">
            <span class="icon icon-16 i-x" aria-hidden="true"></span>
          </button>
        </div>
      </div>
    </div>`,
};

window.addEventListener("keydown", onKey);
createApp(App).mount("#app");
start();
