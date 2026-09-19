// Headroom and preamp bar under the graph (spec §4.4, brief §3.6): max boost,
// the preamp the app builds from the bands, and the honest loudness note.
import { computed } from "./vendor/vue.esm-browser.prod.js";
import { state, setAutoPreamp, freeSmallestBand } from "./store.js";
import { amount, formatFreq, formatGain } from "./format.js";

export const HeadroomBar = {
  setup() {
    const p = computed(() => state.preamp);
    const boost = computed(() => Math.max(0, p.value.peak_db));
    const level = computed(() => (boost.value > 6 ? "warn" : boost.value > 3 ? "amber" : "jade"));
    const boostText = computed(() => (p.value.peak_db > 0.05
      ? `Max boost ${formatGain(p.value.peak_db)} at ${formatFreq(p.value.peak_hz)}`
      : "No boost: the curve stays at or below 0 dB"));
    const preampLine = computed(() => {
      if (!state.auto_preamp) {
        return p.value.peak_db > 0.05 ? "Auto preamp is off: boosts above 0 dB may distort." : "Auto preamp is off.";
      }
      if (p.value.preamp_db < 0) {
        return `Preamp ${formatGain(p.value.preamp_db)} — turn your volume up about ` +
          `${amount(p.value.preamp_db)} dB to compare fairly.`;
      }
      if (p.value.warning === "no_free_band") return ""; // the warning below says it
      if (p.value.warning === "stored_without_preamp") {
        return "Stored without a preamp: boosts above 0 dB may distort. Your next edit adds one.";
      }
      return "No preamp needed.";
    });
    const warning = computed(() => {
      if (p.value.warning === "no_free_band") {
        return "All 5 bands are in use, so there is no room for a preamp: loud passages may distort.";
      }
      if (p.value.warning === "trim_limit") {
        return "This boost is bigger than the preamp can cover (12 dB): loud passages may distort.";
      }
      return "";
    });
    const smallest = computed(() => {
      let best = -1;
      state.design.forEach((b, i) => {
        if (b.gain !== 0 && (best < 0 || Math.abs(b.gain) < Math.abs(state.design[best].gain))) best = i;
      });
      return best + 1;
    });
    return { state, p, boost, level, boostText, preampLine, warning, smallest, setAutoPreamp, freeSmallestBand };
  },
  template: `
    <section class="headroom" data-test="headroom" aria-label="Headroom and preamp">
      <div class="headroom-row">
        <span class="readout" data-test="boost">{{ boostText }}</span>
        <span class="meter" role="meter" aria-label="Max boost" aria-valuemin="0" aria-valuemax="12"
              :aria-valuenow="boost.toFixed(1)">
          <span :class="['meter-fill', 'meter-' + level]" :style="{ width: (Math.min(boost, 12) / 12) * 100 + '%' }"></span>
        </span>
        <span v-if="preampLine" class="preamp-line" data-test="preamp-line">{{ preampLine }}</span>
        <label class="toggle">
          <input type="checkbox" data-test="auto-preamp" :checked="state.auto_preamp"
                 @change="setAutoPreamp($event.target.checked)"> Auto preamp
        </label>
      </div>
      <div v-if="warning" class="warn-line" data-test="preamp-warning" role="alert">
        <span class="icon icon-16 i-warning" aria-hidden="true"></span><span>{{ warning }}</span>
        <button v-if="p.warning === 'no_free_band'" type="button" class="btn btn-small" data-test="free-band"
                @click="freeSmallestBand()">Free band {{ smallest }} for the preamp</button>
      </div>
    </section>`,
};
