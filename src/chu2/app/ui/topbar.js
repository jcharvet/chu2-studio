// Top bar (brief S3): undo / redo, the mode switch (Quick Tune | Build PEQ),
// Presets, Import & share, Settings, the device chip with its menu (Restore
// original), EQ on/off (A/B), "N changes not on CHU 2", Save.
import { computed, ref } from "./vendor/vue.esm-browser.prod.js";
import { state, ui, setEqEnabled, undo, redo, setMode, openDialog } from "./store.js";
import { openSave } from "./savepanel.js";

export const TopBar = {
  setup() {
    const menuOpen = ref(false);
    const chipText = computed(() => {
      if (state.connected) return "CHU 2 DSP";
      return ui.explore && !ui.everConnected ? "No CHU 2 · exploring" : "CHU 2 not connected";
    });
    const status = computed(() => {
      const n = state.changes;
      if (n > 0) return { kind: "pending", text: `${n} ${n === 1 ? "change" : "changes"} not on CHU 2`, short: String(n) };
      if (state.connected) return { kind: "ok", text: "On CHU 2", short: "✓" };
      return { kind: "none", text: "", short: "" };
    });
    const busy = computed(() => ["running", "waiting_device"].includes(state.save.state));
    const canSave = computed(() => state.changes > 0 && !busy.value);
    const saveLabel = computed(() => (state.connected ? "Save" : "Save when connected"));

    function toggleEq() {
      setEqEnabled(!state.eq_on);
    }

    function openRestore() {
      menuOpen.value = false;
      ui.restoreOpen = true;
    }

    return { state, ui, menuOpen, chipText, status, canSave, saveLabel, openSave, toggleEq, openRestore,
             undo, redo, setMode, openDialog };
  },
  template: `
    <header class="topbar panel">
      <span class="brand">CHU 2 Studio</span>
      <div class="history" role="group" aria-label="Undo and redo">
        <button type="button" class="icon-btn" data-test="undo" aria-label="Undo" title="Undo (Ctrl+Z)"
                :disabled="!ui.canUndo" @click="undo()">
          <span class="icon icon-16 i-arrow-u-up-left" aria-hidden="true"></span>
        </button>
        <button type="button" class="icon-btn" data-test="redo" aria-label="Redo" title="Redo (Ctrl+Y)"
                :disabled="!ui.canRedo" @click="redo()">
          <span class="icon icon-16 i-arrow-u-up-right" aria-hidden="true"></span>
        </button>
      </div>
      <div class="modes" role="tablist" aria-label="Mode">
        <button type="button" role="tab" class="mode" data-test="mode-quick" title="Quick Tune (Ctrl+1)"
                :aria-selected="ui.mode === 'quick' ? 'true' : 'false'" @click="setMode('quick')">Quick Tune</button>
        <button type="button" role="tab" class="mode" data-test="mode-build" title="Build PEQ (Ctrl+3)"
                :aria-selected="ui.mode === 'build' ? 'true' : 'false'" @click="setMode('build')">Build PEQ</button>
      </div>
      <div class="tools">
        <button type="button" class="btn btn-small" data-test="open-library" title="Presets (Ctrl+P)"
                @click="openDialog('library')">
          <span class="icon icon-16 i-books" aria-hidden="true"></span><span class="label-text">Presets</span>
        </button>
        <button type="button" class="btn btn-small" data-test="open-share" title="Import &amp; share (Ctrl+I)"
                @click="openDialog('share')">
          <span class="icon icon-16 i-share-network" aria-hidden="true"></span><span class="label-text">Share</span>
        </button>
        <button type="button" class="icon-btn" data-test="open-settings" aria-label="Settings" title="Settings (Ctrl+,)"
                @click="openDialog('settings')">
          <span class="icon icon-16 i-gear-six" aria-hidden="true"></span>
        </button>
      </div>
      <div class="topbar-right">
        <div class="device" @keydown.escape="menuOpen = false">
          <button type="button" class="chip" data-test="device-chip" aria-haspopup="menu"
                  :aria-expanded="menuOpen ? 'true' : 'false'" @click="menuOpen = !menuOpen">
            <span :class="['dot', state.connected ? 'dot-on' : '']" aria-hidden="true"></span>{{ chipText }}
          </button>
          <div v-if="menuOpen" class="menu dialog" role="menu" data-test="device-menu">
            <button type="button" role="menuitem" class="menu-item" data-test="restore-open"
                    :disabled="!state.backup || state.save.state !== 'idle'" @click="openRestore">
              <span class="icon icon-16 i-clock-counter-clockwise" aria-hidden="true"></span>Restore original…
            </button>
          </div>
        </div>
        <div class="ab">
          <span class="ab-label" id="eq-label">EQ</span>
          <button type="button" class="switch" role="switch" data-test="eq-switch" aria-labelledby="eq-label"
                  :aria-checked="state.eq_on ? 'true' : 'false'" :disabled="!state.connected"
                  @click="toggleEq">{{ state.eq_on ? "On" : "Off" }}</button>
        </div>
        <span class="eq-name" data-test="eq-name" :title="state.name">{{ state.name }}</span>
        <span :class="['status', 'status-' + status.kind]" data-test="changes" role="status" :title="status.text">
          <span v-if="status.kind !== 'none'" :class="['dot', status.kind === 'ok' ? 'dot-on' : 'dot-warn']"
                aria-hidden="true"></span><span class="status-long">{{ status.text }}</span><span
                class="status-short" aria-hidden="true">{{ status.short }}</span>
        </span>
        <button type="button" :class="['btn', canSave ? 'btn-primary' : '']" data-test="save"
                :disabled="!canSave" @click="openSave">
          <span class="icon icon-16 i-floppy-disk" aria-hidden="true"></span>{{ saveLabel }}
        </button>
      </div>
    </header>`,
};
