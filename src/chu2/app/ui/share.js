// Import & share (brief S7): open a file, paste a code or an EQ text, export a
// file, copy the share code. Nothing changes until "Import to editor", which
// Undo can take back. A file dropped on the window, or a share code pasted
// with no text field focused, opens here with its preview.
import { computed, nextTick, ref, watch } from "./vendor/vue.esm-browser.prod.js";
import { state, ui, ask, importBands, openDialog, toast } from "./store.js";
import { formatGain, formatFreq, formatQ, signed } from "./format.js";
import { MiniCurve } from "./minicurve.js";

const TABS = [
  { id: "import", label: "Import file" },
  { id: "paste", label: "Paste" },
  { id: "export", label: "Export" },
  { id: "share", label: "Share code" },
];
const MAX_FILE_BYTES = 1_000_000;

function showPreview(result) {
  ui.shareError = "";
  ui.sharePreview = null;
  if (!result || result.cancelled) return;
  if (result.error) ui.shareError = result.error;
  else ui.sharePreview = result;
}

export function openShare(tab) {
  ui.shareTab = tab;
  openDialog("share");
}

export function closeShare() {
  ui.shareOpen = false;
  ui.sharePreview = null;
  ui.shareError = "";
}

/** Open the dialog on `tab` with a preview of `text` (a dropped file or a pasted code). */
export async function previewText(text, name, tab) {
  ui.shareTab = tab;
  if (tab === "paste") ui.pasteText = text;
  showPreview(await ask("import_text", text, name));
  openDialog("share");
}

function isTextField(target) {
  return target instanceof Element &&
    target.closest("textarea, input[type=text], input[type=number], input[type=search]");
}

window.addEventListener("dragover", (e) => e.preventDefault()); // or WebView2 opens the file itself
window.addEventListener("drop", (e) => {
  e.preventDefault();
  const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (!file) return;
  if (file.size > MAX_FILE_BYTES) {
    toast(`"${file.name}" is too big to be an EQ file.`, "warn");
    return;
  }
  file.text().then((text) => previewText(text, file.name, "import"));
});
window.addEventListener("paste", (e) => {
  if (isTextField(e.target) || !e.clipboardData) return;
  const text = e.clipboardData.getData("text/plain");
  if (!/CHU2-\d+\./.test(text)) return;
  e.preventDefault();
  previewText(text, "", "paste");
});

export const ShareDialog = {
  components: { MiniCurve },
  setup() {
    const shared = ref({ code: "", text: "" });
    const box = ref(null);
    const preview = computed(() => ui.sharePreview);
    const showsPreview = computed(() => ["import", "paste"].includes(ui.shareTab));
    const summary = computed(() => {
      const p = preview.value;
      if (!p) return "";
      const preamp = p.preamp !== null && p.preamp !== undefined ? ` · Preamp ${signed(p.preamp)} dB` : "";
      return `${p.name} · ${p.format} · ${p.total} ${p.total === 1 ? "filter" : "filters"}${preamp}`;
    });

    watch(() => [ui.shareOpen, ui.shareTab], async ([open, tab]) => {
      if (open && tab === "share") shared.value = await ask("share_code");
    }, { immediate: true });
    watch(() => ui.shareOpen, (open) => open && nextTick(() => box.value && box.value.focus()));
    const close = closeShare;

    async function chooseFile() {
      showPreview(await ask("import_file"));
    }

    async function readPaste() {
      showPreview(await ask("import_text", ui.pasteText, ""));
    }

    async function importNow() {
      const p = preview.value;
      await importBands(p.bands, p.name);
      close();
      toast(`Imported "${p.name}". It's playing; it's not on CHU 2 until you save.`, "info");
    }

    async function exportAs(fmt) {
      const result = await ask("export_file", fmt);
      if (result.saved) toast(`Saved ${result.saved}`, "ok");
      else if (result.error) toast(result.error, "warn");
    }

    async function copy(text, inputId) {
      try {
        await navigator.clipboard.writeText(text);
      } catch (err) {
        const field = document.getElementById(inputId); // older WebView2: copy the selection
        if (!field) throw err;
        field.select();
        document.execCommand("copy");
      }
      toast("Copied.", "ok");
    }

    const cell = {
      frequency: (row) => formatFreq(row.frequency),
      gain: (row) => (row.type ? formatGain(row.gain) : "—"),
      q: (row) => (row.q !== null && row.q !== undefined ? formatQ(row.q) : "—"),
    };

    return { state, ui, TABS, shared, box, preview, showsPreview, summary, close, chooseFile, readPaste,
             importNow, exportAs, copy, cell, formatGain };
  },
  template: `
    <div v-if="ui.shareOpen" class="scrim modal-wrap" @click.self="close">
      <section ref="box" tabindex="-1" class="dialog share" role="dialog" aria-modal="true"
               aria-labelledby="share-title" data-test="share-dialog">
        <header class="sheet-head">
          <h2 id="share-title" class="title">Import &amp; share</h2>
          <button type="button" class="icon-btn" aria-label="Close" @click="close">
            <span class="icon icon-16 i-x" aria-hidden="true"></span>
          </button>
        </header>
        <div class="modes share-tabs" role="tablist" aria-label="Import and share">
          <button v-for="t in TABS" :key="t.id" type="button" role="tab" class="mode" :data-test="'tab-' + t.id"
                  :aria-selected="ui.shareTab === t.id ? 'true' : 'false'" @click="ui.shareTab = t.id">{{ t.label }}</button>
        </div>
        <div class="share-body">
          <template v-if="ui.shareTab === 'import'">
            <p v-if="!preview" class="copy">Open a .txt from AutoEq, Equalizer APO or Peace, or a CHU 2 Studio preset
              (.chu2.json). You can also drop a file anywhere on the window.</p>
            <button type="button" class="btn" data-test="choose-file" @click="chooseFile">
              <span class="icon icon-16 i-folder-open" aria-hidden="true"></span>Choose a file…</button>
          </template>
          <template v-if="ui.shareTab === 'paste'">
            <label class="stack-label">Paste a share code, or the text of an EQ file
              <textarea v-model="ui.pasteText" rows="4" class="mono" data-test="paste-text"></textarea>
            </label>
            <button type="button" class="btn" data-test="paste-read" @click="readPaste">Read</button>
          </template>
          <p v-if="showsPreview && ui.shareError" class="warn-line" role="alert" data-test="import-error">
            <span class="icon icon-16 i-warning" aria-hidden="true"></span><span>{{ ui.shareError }}</span></p>
          <div v-if="showsPreview && preview" class="preview" data-test="import-preview">
            <p class="readout" data-test="preview-summary">{{ summary }}</p>
            <div class="table-wrap">
              <table class="filters" data-test="preview-table">
                <thead><tr><th>#</th><th>Type</th><th>Freq</th><th>Gain</th><th>Q</th><th>Status</th></tr></thead>
                <tbody>
                  <tr v-for="row in preview.filters" :key="row.n" :class="{ 'row-off': !row.type || row.status.startsWith('not kept') }">
                    <td>{{ row.n }}</td><td>{{ row.code }}</td><td>{{ cell.frequency(row) }}</td>
                    <td>{{ cell.gain(row) }}</td><td>{{ cell.q(row) }}</td><td>{{ row.status }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <ul v-if="preview.notes.length" class="notes" data-test="preview-notes">
              <li v-for="(note, n) in preview.notes" :key="n">{{ note }}</li>
            </ul>
            <mini-curve :bands="preview.bands" :before="state.design" :height="72"></mini-curve>
            <p class="legend muted"><span class="swatch swatch-before"></span>now <span class="swatch swatch-after"></span>after import
              · max boost {{ formatGain(preview.peak_db) }}</p>
            <div class="actions">
              <button type="button" class="btn" @click="ui.sharePreview = null">Cancel</button>
              <button type="button" class="btn btn-primary" data-test="import-apply" @click="importNow">Import to editor</button>
            </div>
          </div>
          <template v-if="ui.shareTab === 'export'">
            <p class="copy">Save the current EQ ("{{ state.name }}") as a file.</p>
            <button type="button" class="btn" data-test="export-apo" @click="exportAs('apo')">
              <span class="icon icon-16 i-download-simple" aria-hidden="true"></span>Equalizer APO / AutoEq text (.txt)…</button>
            <p class="meta">For Equalizer APO, Peace or AutoEq tools. Its Preamp line is the preamp this app
              builds into the bands.</p>
            <button type="button" class="btn" data-test="export-json" @click="exportAs('json')">
              <span class="icon icon-16 i-download-simple" aria-hidden="true"></span>CHU 2 Studio preset (.chu2.json)…</button>
            <p class="meta">For CHU 2 Studio on another PC.</p>
          </template>
          <template v-if="ui.shareTab === 'share'">
            <div class="code-row">
              <input id="share-code-field" type="text" readonly class="mono" :value="shared.code"
                     aria-label="Share code" data-test="share-code">
              <button type="button" class="btn" data-test="copy-code" @click="copy(shared.code, 'share-code-field')">
                <span class="icon icon-16 i-copy" aria-hidden="true"></span>Copy</button>
            </div>
            <p class="copy">Anyone with CHU 2 Studio can paste this. No server, no account.</p>
            <p class="meta" data-test="share-text">As text: {{ shared.text }}</p>
            <button type="button" class="btn btn-small" data-test="copy-text" @click="copy(shared.text, 'share-code-field')">Copy as text</button>
          </template>
        </div>
      </section>
    </div>`,
};
