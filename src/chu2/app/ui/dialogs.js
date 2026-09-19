// Restore original (brief S9) and the close-with-unsaved-changes guard (S8 E).
import { computed, nextTick, ref, watch } from "./vendor/vue.esm-browser.prod.js";
import { onEvent } from "./bridge.js";
import { state, ui, restoreOriginal, closeApp } from "./store.js";
import { formatDate } from "./format.js";

// Python asks before the window closes with unsaved changes (chu2/app/api.py).
onEvent("close_requested", (info) => { ui.closeRequest = info; });

function focusWhenOpen(source, target) {
  watch(source, (open) => {
    if (open) nextTick(() => target.value && target.value.focus());
  });
}

export const RestoreDialog = {
  setup() {
    const primary = ref(null);
    const when = computed(() => (state.backup ? formatDate(state.backup.saved_at) : ""));
    focusWhenOpen(() => ui.restoreOpen, primary);

    function confirm() {
      ui.restoreOpen = false;
      ui.saveOpen = true;
      restoreOriginal();
    }

    return { ui, when, primary, confirm };
  },
  template: `
    <div v-if="ui.restoreOpen" class="scrim modal-wrap" @click.self="ui.restoreOpen = false">
      <div class="dialog modal" role="dialog" aria-modal="true" aria-labelledby="restore-title" data-test="restore-dialog">
        <h2 id="restore-title" class="title">Put back the EQ your CHU 2 had on {{ when }}?</h2>
        <p class="copy">Your CHU 2 restarts to store it, so audio drops for about a second. Lower the volume or pause first.</p>
        <div class="actions">
          <button type="button" class="btn" @click="ui.restoreOpen = false">Cancel</button>
          <button type="button" class="btn btn-primary" ref="primary" data-test="restore-confirm"
                  @click="confirm">Restore &amp; restart</button>
        </div>
      </div>
    </div>`,
};

export const CloseDialog = {
  setup() {
    const first = ref(null);
    focusWhenOpen(() => ui.closeRequest, first);

    function keep() {
      ui.closeRequest = null;
    }

    function discard() {
      ui.closeRequest = null;
      closeApp("discard");
    }

    function saveAndClose() {
      ui.closeRequest = null;
      ui.saveOpen = true;
      closeApp("save");
    }

    return { ui, first, keep, discard, saveAndClose };
  },
  template: `
    <div v-if="ui.closeRequest" class="scrim modal-wrap">
      <div class="dialog modal" role="alertdialog" aria-modal="true" aria-labelledby="close-title"
           aria-describedby="close-text" data-test="close-dialog">
        <template v-if="ui.closeRequest.saving">
          <h2 id="close-title" class="title">Saving to your CHU 2…</h2>
          <p id="close-text" class="copy">Wait until it's done, then close the app.</p>
          <div class="actions">
            <button type="button" class="btn btn-primary" ref="first" @click="keep">OK</button>
          </div>
        </template>
        <template v-else>
          <h2 id="close-title" class="title">Close without saving?</h2>
          <p id="close-text" class="copy">{{ ui.closeRequest.connected
            ? "Your CHU 2 still has the old EQ."
            : "Your changes aren't on a CHU 2 yet. They're lost when you close." }}</p>
          <div class="actions">
            <button type="button" class="btn" ref="first" data-test="close-keep" @click="keep">Keep editing</button>
            <button type="button" class="btn btn-danger" data-test="close-discard" @click="discard">Close without saving</button>
            <button v-if="ui.closeRequest.connected" type="button" class="btn btn-primary" data-test="close-save"
                    @click="saveAndClose">Save &amp; close</button>
          </div>
        </template>
      </div>
    </div>`,
};
