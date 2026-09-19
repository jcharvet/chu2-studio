// Settings and About (brief S10): the theme, asking before a save, Restore
// original (brief S9), the data folder and its log, the version, the
// disclaimer and the licences. Each theme card carries its own data-theme, so
// tokens.css paints its swatch in that theme's colours.
import { nextTick, ref, watch } from "./vendor/vue.esm-browser.prod.js";
import { state, ui, ask, setSetting } from "./store.js";

const THEMES = [
  { id: "atelier", name: "Atelier", note: "Dark · the default" },
  { id: "mocha", name: "Mocha", note: "Dark · Catppuccin" },
  { id: "sage", name: "Sage", note: "Dark green" },
  { id: "latte", name: "Latte", note: "Light · Catppuccin" },
  { id: "porcelain", name: "Porcelain", note: "Light · warm" },
];
const CREDITS = [
  ["Vue", "MIT", "vendor/LICENSE-vue.txt"],
  ["Phosphor Icons", "MIT", "icons/LICENSE-phosphor.txt"],
  ["Catppuccin colours (Mocha, Latte)", "MIT", "LICENSE-catppuccin.txt"],
  ["Inter", "SIL Open Font License 1.1", "fonts/OFL-Inter.txt"],
  ["Newsreader", "SIL Open Font License 1.1", "fonts/OFL-Newsreader.txt"],
  ["JetBrains Mono", "SIL Open Font License 1.1", "fonts/OFL-JetBrainsMono.txt"],
];

export const SettingsDialog = {
  setup() {
    const box = ref(null);
    watch(() => ui.settingsOpen, (open) => open && nextTick(() => box.value && box.value.focus()));

    function close() {
      ui.settingsOpen = false;
    }

    function openRestore() {
      ui.settingsOpen = false;
      ui.restoreOpen = true;
    }

    function onThemeKey(e, index) {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const next = THEMES[(index + step + THEMES.length) % THEMES.length];
      setSetting("theme", next.id);
      nextTick(() => document.querySelector(`[data-theme-option=${next.id}]`).focus());
    }

    return { state, ui, THEMES, CREDITS, box, close, openRestore, onThemeKey, setSetting,
             openFolder: () => ask("open_data_folder") };
  },
  template: `
    <div v-if="ui.settingsOpen" class="scrim modal-wrap" @click.self="close">
      <section ref="box" tabindex="-1" class="dialog settings" role="dialog" aria-modal="true"
               aria-labelledby="settings-title" data-test="settings-dialog">
        <header class="sheet-head">
          <h2 id="settings-title" class="title">Settings</h2>
          <button type="button" class="icon-btn" aria-label="Close" @click="close">
            <span class="icon icon-16 i-x" aria-hidden="true"></span>
          </button>
        </header>
        <div class="settings-body">
          <h3 class="eyebrow" id="theme-label">Theme</h3>
          <div class="theme-grid" role="radiogroup" aria-labelledby="theme-label">
            <button v-for="(t, i) in THEMES" :key="t.id" type="button" role="radio" class="theme-card"
                    :data-theme="t.id" :data-theme-option="t.id"
                    :aria-checked="state.settings.theme === t.id ? 'true' : 'false'"
                    :tabindex="state.settings.theme === t.id ? 0 : -1"
                    @click="setSetting('theme', t.id)" @keydown="onThemeKey($event, i)">
              <span class="theme-swatch" aria-hidden="true">
                <span style="background: var(--surface)"></span><span style="background: var(--jade)"></span>
                <span style="background: var(--amber)"></span><span style="background: var(--amethyst)"></span>
              </span>
              <span class="theme-name">{{ t.name }}</span>
              <span class="theme-note">{{ t.note }}</span>
            </button>
          </div>
          <h3 class="eyebrow">Saving</h3>
          <label class="toggle">
            <input type="checkbox" data-test="confirm-save" :checked="state.settings.confirm_save"
                   @change="setSetting('confirm_save', $event.target.checked)">
            Ask before saving to CHU 2 (it restarts, so audio drops for about a second)
          </label>
          <h3 class="eyebrow">Your data</h3>
          <p class="meta">The backup of your CHU 2's original EQ, your presets, settings and the log stay on this PC.</p>
          <div class="actions actions-start">
            <button type="button" class="btn btn-small" data-test="open-data-folder" @click="openFolder">
              <span class="icon icon-16 i-folder-open" aria-hidden="true"></span>Open data folder</button>
            <button type="button" class="btn btn-small" data-test="settings-restore"
                    :disabled="!state.backup || state.save.state !== 'idle'" @click="openRestore">
              <span class="icon icon-16 i-clock-counter-clockwise" aria-hidden="true"></span>Restore original…</button>
          </div>
          <h3 class="eyebrow">About</h3>
          <p class="copy" data-test="about-version">CHU 2 Studio {{ state.version }}</p>
          <p class="meta" data-test="disclaimer">Unofficial community app · not affiliated with or endorsed by
            Moondrop · open source (MIT). Works offline: no account, no telemetry.</p>
          <ul class="credits" data-test="credits">
            <li v-for="c in CREDITS" :key="c[0]">{{ c[0] }} · {{ c[1] }} <span class="muted">({{ c[2] }})</span></li>
          </ul>
        </div>
      </section>
    </div>`,
};
