// Save to CHU 2 (brief S8): confirm -> progress -> done (toast) or failed
// (Retry). The same panel shows a Restore original run (brief S9) and the
// "waiting for your CHU 2" state of a save made without the device.
import { computed, ref, watch } from "./vendor/vue.esm-browser.prod.js";
import { state, ui, save, cancelSave, dismissSave, restoreOriginal, setSetting, toast } from "./store.js";
import { TYPE_LABEL, amount, formatFreq, formatGain } from "./format.js";

const STEPS = [
  { key: "writing", label: "Writing 5 bands" },
  { key: "committing", label: "Storing in the CHU 2's memory" },
  { key: "restarting", label: "Restarting CHU 2… audio drops about a second" },
  { key: "verifying", label: "Checking what was stored" },
];
const WORDS = { done: "done", active: "in progress", todo: "to do" };
const REPLUG = ["no_restart", "commit_unknown"];

const sameBand = (a, b) => !!a && !!b && a.type === b.type && a.frequency === b.frequency &&
  a.gain === b.gain && a.q === b.q;

/** Save button, Ctrl+S: ask first when a CHU 2 is there (unless turned off in
 * Settings), else save now or queue the save. */
export function openSave() {
  if (state.changes === 0 || state.save.state !== "idle") return;
  if (state.connected && state.settings.confirm_save) ui.saveOpen = true;
  else save();
}

export const SavePanel = {
  setup() {
    const dontAsk = ref(false);
    const phase = computed(() => {
      const s = state.save.state;
      if (s === "running") return "running";
      if (s === "waiting_device") return "waiting";
      if (s === "failed") return "failed";
      return ui.saveOpen && s === "idle" ? "confirm" : "";
    });
    const changed = computed(() => state.design
      .map((b, i) => ({ b, i }))
      .filter(({ i }) => !state.stored || !sameBand(state.stored[i], state.device_bands[i])));
    const describe = (b) => `${TYPE_LABEL[b.type]} ${formatFreq(b.frequency)} ${formatGain(b.gain)}` +
      (b.bypass ? " (bypassed)" : "");
    const preampSummary = computed(() => (state.preamp.preamp_db < 0
      ? `Stored with a preamp of ${formatGain(state.preamp.preamp_db)}, so it plays about ` +
        `${amount(state.preamp.preamp_db)} dB quieter.`
      : "No preamp needed."));
    const current = computed(() => {
      const step = state.save.step === "still_waiting" ? "restarting" : state.save.step;
      return Math.max(0, STEPS.findIndex((s) => s.key === step));
    });
    const steps = computed(() => STEPS.map((s, i) => {
      const status = i < current.value ? "done" : i === current.value ? "active" : "todo";
      return { ...s, status, word: WORDS[status] };
    }));
    const failure = computed(() => {
      const r = state.save.reason;
      const list = (indexes) => indexes.map((i) => i + 1).join(", ");
      if (r === "write_mismatch") {
        return { title: "Nothing was saved",
                 text: `Your CHU 2 didn't take band ${list(state.save.mismatched)} as sent. It still has its previous EQ.` };
      }
      if (r === "invalid_bands" || r === "write_failed") {
        return { title: "Nothing was saved",
                 text: "Couldn't write to your CHU 2. It still has its previous EQ. Check the cable and try again." };
      }
      if (r === "verify_mismatch") {
        return { title: "Stored, but not as sent",
                 text: `Your CHU 2 stored band ${list(changed.value.map((c) => c.i))} differently from what was sent.` };
      }
      if (REPLUG.includes(r)) {
        return { title: "Save didn't finish",
                 text: "Your CHU 2 didn't restart, so it may still have its previous EQ. Unplug it, plug it back in, and we'll check." };
      }
      return { title: "Save didn't finish",
               text: "Your CHU 2 may still have its previous EQ. Reconnect it and we'll check." };
    });

    watch(() => state.save.state, (now) => {
      if (now !== "done") return;
      toast(state.save.kind === "restore"
        ? "Restored the original EQ on your CHU 2 ✓ Checked."
        : "Saved to CHU 2 ✓ Checked. It now plays this EQ on any phone or PC.", "ok");
      ui.saveOpen = false;
      dismissSave();
    });

    function confirm() {
      if (dontAsk.value) setSetting("confirm_save", false);
      dontAsk.value = false;
      save();
    }

    function cancel() {
      ui.saveOpen = false;
    }

    function retry() {
      if (state.save.kind === "restore") restoreOriginal();
      else save();
    }

    function close() {
      ui.saveOpen = false;
      dismissSave();
    }

    function stopWaiting() {
      ui.saveOpen = false;
      cancelSave();
    }

    return { state, dontAsk, phase, changed, describe, preampSummary, steps, failure, confirm, cancel, retry, close, stopWaiting };
  },
  template: `
    <div v-if="phase" class="save-panel dialog" role="dialog" aria-labelledby="save-title"
         data-test="save-panel" :data-phase="phase">
      <template v-if="phase === 'confirm'">
        <h2 id="save-title" class="title">Save to your CHU 2?</h2>
        <p class="copy">Your CHU 2 restarts to store it, so audio drops for about a second. Lower the volume or pause first.</p>
        <ul class="change-list" data-test="change-list">
          <li v-for="c in changed" :key="c.i">Band {{ c.i + 1 }} · {{ describe(c.b) }}</li>
        </ul>
        <p class="meta" data-test="save-preamp">{{ preampSummary }}</p>
        <p v-if="!state.eq_on" class="meta" data-test="save-eq-note">The EQ is off for comparing; saving turns it back on.</p>
        <label class="toggle meta"><input type="checkbox" v-model="dontAsk" data-test="save-dont-ask">
          Don't ask again (Settings can turn this back on)</label>
        <div class="actions">
          <button type="button" class="btn" data-test="save-cancel" @click="cancel">Cancel</button>
          <button type="button" class="btn btn-primary" data-test="save-confirm" @click="confirm">Save &amp; restart</button>
        </div>
      </template>
      <template v-else-if="phase === 'waiting'">
        <h2 id="save-title" class="title">Waiting for your CHU 2</h2>
        <p class="copy">{{ state.save.kind === "restore" ? "The original EQ" : "Your EQ" }} is saved as soon as your CHU 2 is plugged in.</p>
        <div class="actions">
          <button type="button" class="btn" data-test="save-stop-waiting" @click="stopWaiting">Don't save</button>
        </div>
      </template>
      <template v-else-if="phase === 'running'">
        <h2 id="save-title" class="title">{{ state.save.kind === "restore" ? "Restoring the original EQ" : "Saving to CHU 2" }}</h2>
        <ol class="steps" aria-live="polite">
          <li v-for="s in steps" :key="s.key" :class="['step', 'step-' + s.status]" :data-step="s.key" :data-status="s.status">
            <span :class="['step-mark', s.status === 'done' ? 'icon icon-16 i-check' : '']" aria-hidden="true"></span>
            <span>{{ s.label }}</span><span class="sr-only">, {{ s.word }}</span>
            <span v-if="s.key === 'restarting' && s.status === 'active'" class="shimmer" aria-hidden="true"></span>
          </li>
        </ol>
        <p v-if="state.save.step === 'still_waiting'" class="copy" data-test="still-waiting">
          Still waiting for your CHU 2… (unplugging and replugging is safe).</p>
      </template>
      <template v-else-if="phase === 'failed'">
        <h2 id="save-title" class="title">{{ failure.title }}</h2>
        <p class="copy" role="alert" data-test="save-failure">{{ failure.text }}</p>
        <div class="actions">
          <button type="button" class="btn" data-test="save-close" @click="close">Close</button>
          <button type="button" class="btn btn-primary" data-test="save-retry" @click="retry">Retry</button>
        </div>
      </template>
    </div>`,
};
