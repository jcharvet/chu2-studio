// Five band cards (brief S3, §6): type, frequency, gain, Q, bypass, reset.
// The same edits as the graph, through native inputs with the same steps.
import { computed, reactive } from "./vendor/vue.esm-browser.prod.js";
import { state, ui, setBand, resetBands, undo, toast } from "./store.js";
import { quantizeBand } from "./eqmath.js";
import { formatGain } from "./format.js";

const shown = (b, key) => (key === "gain" ? b.gain.toFixed(1) : key === "q" ? b.q.toFixed(2) : String(b.frequency));

export const BandCards = {
  setup() {
    const active = computed(() => state.design.filter((b) => b.gain !== 0 && !b.bypass).length);
    const isFlat = computed(() => state.design.every((b) => b.gain === 0 && !b.bypass));

    async function resetAll() {
      await resetBands();
      toast("All bands reset to 0 dB: your CHU 2's own tuning. Not on CHU 2 until you save.", "info",
            { label: "Undo", run: undo });
    }

    function update(i, patch) {
      const clean = quantizeBand({ ...state.design[i], ...patch });
      setBand(i, clean);
      ui.selected = i;
      return clean;
    }

    // What the user is typing, per field ("2:gain"). Vue re-applies an input's
    // value on every re-render, so without this a state update that arrives
    // while typing (the answer to an earlier edit, a device event) would put
    // the old value back.
    const drafts = reactive({});

    function fieldValue(i, key, b) {
      const id = `${i}:${key}`;
      return id in drafts ? drafts[id] : shown(b, key);
    }

    function onDraft(i, key, event) {
      drafts[`${i}:${key}`] = event.target.value;
    }

    function endDraft(i, key) {
      delete drafts[`${i}:${key}`];  // after change (if any): show the stored value again
    }

    function onNumber(i, key, event) {
      delete drafts[`${i}:${key}`];
      const value = parseFloat(event.target.value);
      if (!Number.isFinite(value)) {
        event.target.value = shown(state.design[i], key);
        return;
      }
      event.target.value = shown(update(i, { [key]: value }), key); // show the clamped value
    }

    function note(i) {
      if (state.preamp.trim_index === i && state.device_bands[i]) {
        return `Holds the preamp (${formatGain(state.device_bands[i].gain)}).`;
      }
      if (state.preamp.flipped.includes(i)) return "Stored as the opposite shelf: same sound, quieter.";
      return "";
    }

    return { state, ui, active, isFlat, resetAll, update, fieldValue, onDraft, endDraft, onNumber, note };
  },
  template: `
    <section class="bands" aria-labelledby="bands-title">
      <div class="bands-head">
        <h2 id="bands-title" class="eyebrow">Bands</h2>
        <span class="bands-tools">
          <span class="band-strip" :aria-label="active + ' of 5 bands in use'">
            <span v-for="n in 5" :key="n" :class="['dot', n <= active ? 'dot-on' : '']" aria-hidden="true"></span>
            <span aria-hidden="true">{{ active }} / 5</span>
          </span>
          <button type="button" class="btn btn-small" data-test="reset-all" :disabled="isFlat"
                  title="Set all 5 bands to 0 dB: the CHU 2's own tuning" @click="resetAll">
            <span class="icon icon-16 i-arrow-counter-clockwise" aria-hidden="true"></span>Reset all
          </button>
        </span>
      </div>
      <fieldset v-for="(b, i) in state.design" :key="i" class="card band-card" :data-band="i + 1"
                :aria-selected="ui.selected === i ? 'true' : 'false'"
                @focusin="ui.selected = i" @pointerdown="ui.selected = i">
        <legend class="sr-only">Band {{ i + 1 }}</legend>
        <div class="band-row">
          <span class="band-num" aria-hidden="true">{{ i + 1 }}</span>
          <select :value="b.type" data-test="type" :aria-label="'Band ' + (i + 1) + ' filter type'"
                  @change="update(i, { type: $event.target.value })">
            <option value="peaking">Peak</option>
            <option value="low_shelf">Low shelf</option>
            <option value="high_shelf">High shelf</option>
          </select>
          <button type="button" class="icon-btn" data-test="bypass" :aria-pressed="b.bypass ? 'true' : 'false'"
                  :aria-label="(b.bypass ? 'Turn on band ' : 'Bypass band ') + (i + 1)"
                  :title="b.bypass ? 'Turn the band back on' : 'Bypass'" @click="update(i, { bypass: !b.bypass })">
            <span :class="['icon', 'icon-16', b.bypass ? 'i-eye-slash' : 'i-eye']" aria-hidden="true"></span>
          </button>
          <button type="button" class="icon-btn" data-test="reset" :aria-label="'Reset band ' + (i + 1) + ' to 0 dB'"
                  title="Reset to 0 dB" @click="update(i, { gain: 0 })">
            <span class="icon icon-16 i-arrow-counter-clockwise" aria-hidden="true"></span>
          </button>
        </div>
        <div class="band-fields">
          <label class="field"><input type="number" data-test="frequency" min="20" max="20000" step="1"
                 :aria-label="'Band ' + (i + 1) + ' frequency in hertz'" :value="fieldValue(i, 'frequency', b)"
                 @input="onDraft(i, 'frequency', $event)" @change="onNumber(i, 'frequency', $event)"
                 @blur="endDraft(i, 'frequency')"><span>Hz</span></label>
          <label class="field"><input type="number" data-test="gain" min="-12" max="12" step="0.1"
                 :aria-label="'Band ' + (i + 1) + ' gain in decibels'" :value="fieldValue(i, 'gain', b)"
                 @input="onDraft(i, 'gain', $event)" @change="onNumber(i, 'gain', $event)"
                 @blur="endDraft(i, 'gain')"><span>dB</span></label>
          <label class="field"><span>Q</span><input type="number" data-test="q" min="0.1" max="10" step="0.01"
                 :aria-label="'Band ' + (i + 1) + ' Q'" :value="fieldValue(i, 'q', b)"
                 @input="onDraft(i, 'q', $event)" @change="onNumber(i, 'q', $event)"
                 @blur="endDraft(i, 'q')"></label>
        </div>
        <p v-if="note(i)" class="band-note" data-test="note">{{ note(i) }}</p>
      </fieldset>
    </section>`,
};
