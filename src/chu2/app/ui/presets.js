// The preset library (brief S6): groups, search, cards with a small curve, a
// preview with Apply / Apply & save, favourites, and the user's own presets
// (save the current EQ, rename, delete). Keys: arrows move, Enter applies,
// Ctrl+Enter applies and saves, F toggles the favourite, Esc closes.
import { computed, nextTick, ref, watch } from "./vendor/vue.esm-browser.prod.js";
import { state, ui, lib, loadLibrary, applyPreset, savePreset, renamePreset, deletePreset,
         setFavourite, toast } from "./store.js";
import { openSave } from "./savepanel.js";
import { TYPE_LABEL, formatFreq, formatGain, formatQ } from "./format.js";
import { MiniCurve } from "./minicurve.js";

const CATEGORIES = [
  { id: "all", label: "All", test: () => true },
  { id: "favourites", label: "Favourites", test: (p) => p.favourite },
  { id: "official", label: "Official", test: (p) => p.group === "official" },
  { id: "gaming", label: "Gaming", test: (p) => p.tags.includes("Gaming") },
  { id: "music", label: "Music", test: (p) => p.tags.includes("Music") },
  { id: "movies", label: "Movies", test: (p) => p.tags.includes("Movies") },
  { id: "calls", label: "Calls", test: (p) => p.tags.includes("Calls") },
  { id: "mine", label: "Mine", test: (p) => p.group === "mine" },
];
const TAGS = ["Gaming", "Music", "Movies", "Calls"];
const GROUP_LABEL = { official: "Official", builtin: "Quick Tune scene", mine: "Yours" };

export const PresetSheet = {
  components: { MiniCurve },
  setup() {
    const cat = ref("all");
    const query = ref("");
    const selectedId = ref(null);
    const saving = ref(false);
    const saveName = ref("");
    const saveTags = ref([]);
    const renaming = ref(false);
    const newName = ref("");
    const confirmDelete = ref(false);
    const grid = ref(null);

    const visible = computed(() => {
      const c = CATEGORIES.find((x) => x.id === cat.value);
      const q = query.value.trim().toLowerCase();
      return lib.presets.filter((p) => c.test(p) &&
        (!q || p.name.toLowerCase().includes(q) || p.tags.some((t) => t.toLowerCase().includes(q))));
    });
    const selected = computed(() => lib.presets.find((p) => p.id === selectedId.value) || null);
    const count = (c) => lib.presets.filter(c.test).length;

    watch(() => ui.libraryOpen, async (open) => {
      if (!open) return;
      saving.value = false;
      renaming.value = false;
      await loadLibrary();
      if (!selected.value && visible.value.length) selectedId.value = visible.value[0].id;
      nextTick(() => grid.value && grid.value.focus());
    }, { immediate: true });
    watch(selectedId, () => { renaming.value = false; confirmDelete.value = false; });

    function close() {
      ui.libraryOpen = false;
    }

    async function apply(p) {
      await applyPreset(p.id);
      close();
      toast(`"${p.name}" is playing. It's not on CHU 2 until you save.`, "info");
    }

    async function applyAndSave(p) {
      await applyPreset(p.id);
      close();
      openSave();
    }

    function move(step) {
      const list = visible.value;
      if (!list.length) return;
      const at = list.findIndex((p) => p.id === selectedId.value);
      selectedId.value = list[Math.max(0, Math.min(list.length - 1, (at < 0 ? 0 : at + step)))].id;
    }

    function onGridKey(e) {
      if (["ArrowRight", "ArrowDown"].includes(e.key)) move(1);
      else if (["ArrowLeft", "ArrowUp"].includes(e.key)) move(-1);
      else if (e.key === "Enter" && selected.value) (e.ctrlKey ? applyAndSave : apply)(selected.value);
      else if ((e.key === "f" || e.key === "F") && selected.value) {
        setFavourite(selected.value.id, !selected.value.favourite);
      } else return;
      e.preventDefault();
    }

    async function saveCurrent() {
      await savePreset(saveName.value, [...saveTags.value]);
      const mine = lib.presets.filter((p) => p.group === "mine" && p.name === saveName.value.trim());
      if (mine.length) selectedId.value = mine[mine.length - 1].id;
      cat.value = "mine";
      saving.value = false;
      toast(`Saved "${saveName.value.trim()}" in your presets.`, "ok");
      saveName.value = "";
      saveTags.value = [];
    }

    function startRename() {
      newName.value = selected.value.name;
      renaming.value = true;
    }

    async function finishRename() {
      await renamePreset(selected.value.id, newName.value);
      renaming.value = false;
    }

    async function remove() {
      if (!confirmDelete.value) {
        confirmDelete.value = true;
        return;
      }
      const id = selected.value.id;
      selectedId.value = null;
      await deletePreset(id);
      confirmDelete.value = false;
    }

    const bandLine = (b, i) => `${i + 1} · ${TYPE_LABEL[b.type]} ${formatFreq(b.frequency)} ` +
      `${formatGain(b.gain)} · Q ${formatQ(b.q)}${b.bypass ? " (bypassed)" : ""}`;

    return { state, ui, lib, CATEGORIES, TAGS, GROUP_LABEL, cat, query, selectedId, selected, visible, count,
             saving, saveName, saveTags, renaming, newName, confirmDelete, grid, close, apply, applyAndSave,
             onGridKey, saveCurrent, startRename, finishRename, remove, setFavourite, bandLine };
  },
  template: `
    <div v-if="ui.libraryOpen" class="scrim modal-wrap" @click.self="close">
      <section class="dialog sheet" role="dialog" aria-modal="true" aria-labelledby="presets-title"
               data-test="preset-sheet">
        <header class="sheet-head">
          <h2 id="presets-title" class="title">Presets</h2>
          <input type="search" v-model="query" placeholder="Search presets…" aria-label="Search presets"
                 data-test="preset-search">
          <button type="button" class="icon-btn" aria-label="Close" @click="close">
            <span class="icon icon-16 i-x" aria-hidden="true"></span>
          </button>
        </header>
        <div class="sheet-body">
          <nav class="sheet-cats" aria-label="Preset groups">
            <button v-for="c in CATEGORIES" :key="c.id" type="button" class="cat" :data-test="'cat-' + c.id"
                    :aria-pressed="cat === c.id ? 'true' : 'false'" @click="cat = c.id">
              <span>{{ c.label }}</span><span class="count">{{ count(c) }}</span>
            </button>
            <button type="button" class="btn btn-small" data-test="save-current" @click="saving = true">
              <span class="icon icon-16 i-floppy-disk" aria-hidden="true"></span>Save current EQ…
            </button>
          </nav>
          <div class="sheet-grid" ref="grid" role="listbox" aria-label="Presets" tabindex="0"
               :aria-activedescendant="selectedId ? 'preset-' + selectedId : null"
               data-test="preset-grid" @keydown="onGridKey">
            <div v-for="p in visible" :key="p.id" :id="'preset-' + p.id" role="option" class="preset-card card"
                 :data-preset="p.id" :aria-selected="p.id === selectedId ? 'true' : 'false'"
                 @click="selectedId = p.id" @dblclick="apply(p)">
              <mini-curve :bands="p.bands"></mini-curve>
              <div class="preset-line">
                <span class="preset-name">{{ p.name }}</span>
                <button type="button" class="icon-btn" data-test="favourite"
                        :aria-pressed="p.favourite ? 'true' : 'false'"
                        :aria-label="(p.favourite ? 'Remove ' : 'Add ') + p.name + (p.favourite ? ' from' : ' to') + ' favourites'"
                        @click.stop="setFavourite(p.id, !p.favourite)">
                  <span :class="['icon', 'icon-16', p.favourite ? 'i-star-fill' : 'i-star']" aria-hidden="true"></span>
                </button>
              </div>
              <span class="preset-tags">{{ p.tags.join(" · ") }}</span>
              <span v-if="p.on_chu2" class="badge" data-test="on-chu2">On CHU 2</span>
            </div>
            <p v-if="!visible.length" class="muted">No presets here yet.</p>
          </div>
          <aside v-if="selected" class="sheet-preview" data-test="preset-preview">
            <h3 class="title">{{ selected.name }}</h3>
            <p class="muted">{{ GROUP_LABEL[selected.group] }}<template v-if="selected.tags.length"> · {{ selected.tags.join(" · ") }}</template></p>
            <mini-curve :bands="selected.bands" :before="state.design" :height="120"></mini-curve>
            <p class="legend muted"><span class="swatch swatch-before"></span>now <span class="swatch swatch-after"></span>this preset</p>
            <p v-if="selected.about" class="copy">{{ selected.about }}</p>
            <ul class="preview-bands">
              <li v-for="(b, i) in selected.bands" :key="i">{{ bandLine(b, i) }}</li>
            </ul>
            <div class="actions">
              <button type="button" class="btn" data-test="preset-apply" @click="apply(selected)">Apply</button>
              <button type="button" class="btn btn-primary" data-test="preset-apply-save" @click="applyAndSave(selected)">Apply &amp; save</button>
            </div>
            <div v-if="selected.group === 'mine'" class="actions actions-start">
              <button type="button" class="btn btn-small" data-test="preset-rename" @click="startRename">
                <span class="icon icon-16 i-pencil-simple" aria-hidden="true"></span>Rename</button>
              <button type="button" class="btn btn-small btn-danger" data-test="preset-delete" @click="remove">
                <span class="icon icon-16 i-trash" aria-hidden="true"></span>{{ confirmDelete ? "Click again to delete" : "Delete" }}</button>
            </div>
            <form v-if="renaming" class="inline-form" data-test="rename-form" @submit.prevent="finishRename">
              <input type="text" v-model="newName" aria-label="New name" data-test="rename-name" required>
              <button type="submit" class="btn btn-small">Rename</button>
            </form>
          </aside>
        </div>
        <form v-if="saving" class="save-preset" data-test="save-preset-form" @submit.prevent="saveCurrent">
          <label class="field-label">Name
            <input type="text" v-model="saveName" data-test="save-preset-name" maxlength="60" required>
          </label>
          <span class="field-label">Tags</span>
          <label v-for="t in TAGS" :key="t" class="quick-option">
            <input type="checkbox" :value="t" v-model="saveTags" :data-test="'save-tag-' + t.toLowerCase()"> {{ t }}
          </label>
          <button type="submit" class="btn btn-primary" data-test="save-preset-confirm">Save preset</button>
          <button type="button" class="btn" @click="saving = false">Cancel</button>
        </form>
      </section>
    </div>`,
};
