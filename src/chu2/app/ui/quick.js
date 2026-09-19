// Quick Tune (brief S4): pick a scene, combine tweaks, choose an intensity;
// Python composes the five bands (chu2/quicktune.py) and explains them. The
// graph shows "before" (the bands when Quick Tune was opened) and "after".
import { computed } from "./vendor/vue.esm-browser.prod.js";
import { state, lib, quickTune, setMode } from "./store.js";
import { TYPE_LABEL, formatFreq, formatGain } from "./format.js";

const INTENSITY_LABEL = { subtle: "Subtle", standard: "Standard", strong: "Strong" };

/** The current choice: Python's `quick` state, or nothing chosen. */
function choice() {
  const q = state.quick;
  return q ? { scene: q.scene, tweaks: [...q.tweaks], intensity: q.intensity }
    : { scene: null, tweaks: [], intensity: "standard" };
}

export const QuickPanel = {
  setup() {
    const sel = computed(choice);
    const recipes = computed(() => lib.recipes || { scenes: [], tweaks: [], intensities: [] });

    function pick(patch) {
      const next = { ...sel.value, ...patch };
      quickTune(next.scene, next.tweaks, next.intensity);
    }

    function toggle(tweak, on) {
      const others = sel.value.tweaks.filter((id) => id !== tweak.id && !tweak.conflicts.includes(id));
      pick({ tweaks: on ? [...others, tweak.id] : others });
    }

    return { sel, recipes, pick, toggle, INTENSITY_LABEL };
  },
  template: `
    <section class="quick-panel panel" aria-labelledby="quick-title" data-test="quick-panel">
      <h2 id="quick-title" class="eyebrow">What do you want?</h2>
      <fieldset class="quick-group">
        <legend class="eyebrow">Scenes · pick one</legend>
        <label class="quick-option">
          <input type="radio" name="scene" data-test="scene-none" :checked="!sel.scene" @change="pick({ scene: null })">
          <span>None</span>
        </label>
        <label v-for="s in recipes.scenes" :key="s.id" class="quick-option">
          <input type="radio" name="scene" :data-test="'scene-' + s.id" :checked="sel.scene === s.id"
                 @change="pick({ scene: s.id })">
          <span>{{ s.name }}</span>
        </label>
      </fieldset>
      <fieldset class="quick-group">
        <legend class="eyebrow">Tweaks · combine</legend>
        <label v-for="t in recipes.tweaks" :key="t.id" class="quick-option" :title="t.about">
          <input type="checkbox" :data-test="'tweak-' + t.id" :checked="sel.tweaks.includes(t.id)"
                 @change="toggle(t, $event.target.checked)">
          <span>{{ t.name }}</span>
        </label>
      </fieldset>
      <fieldset class="quick-group">
        <legend class="eyebrow">Intensity</legend>
        <div class="segmented" role="radiogroup" aria-label="Intensity">
          <button v-for="k in recipes.intensities" :key="k" type="button" role="radio" class="segment"
                  :data-test="'intensity-' + k" :aria-checked="sel.intensity === k ? 'true' : 'false'"
                  @click="pick({ intensity: k })">{{ INTENSITY_LABEL[k] }}</button>
        </div>
      </fieldset>
    </section>`,
};

export const WhatChanged = {
  setup() {
    const changed = computed(() => state.design
      .map((b, i) => ({ b, i }))
      .filter(({ b }) => b.gain !== 0 && !b.bypass));
    const describe = (b) => `${TYPE_LABEL[b.type]} ${formatFreq(b.frequency)} ${formatGain(b.gain)}`;
    return { state, changed, describe, setMode };
  },
  template: `
    <section class="changed" aria-labelledby="changed-title" data-test="what-changed">
      <h2 id="changed-title" class="eyebrow">What changed</h2>
      <template v-if="state.quick">
        <p class="title">{{ state.name }}</p>
        <p v-for="(t, n) in state.quick.text" :key="'t' + n" class="copy">{{ t }}</p>
        <p v-for="(note, n) in state.quick.notes" :key="'n' + n" class="changed-note">{{ note }}</p>
        <ul class="changed-bands" data-test="changed-bands">
          <li v-for="c in changed" :key="c.i">{{ c.i + 1 }} · {{ describe(c.b) }}</li>
          <li v-if="!changed.length">All bands at 0 dB.</li>
        </ul>
      </template>
      <p v-else class="copy muted">Pick a scene or a tweak on the left. Each one says in plain words what it
        changes. Your bands stay as they are until you pick.</p>
      <button type="button" class="btn" data-test="fine-tune" @click="setMode('build')">Fine-tune in Build PEQ ▸</button>
    </section>`,
};
