// No device / first run (brief S0), explore mode, the unplugged banner, and the
// first-seen backup toast.
import { computed, onBeforeUnmount, onMounted, ref } from "./vendor/vue.esm-browser.prod.js";
import { onEvent } from "./bridge.js";
import { state, ui, toast } from "./store.js";
import { formatDate } from "./format.js";

// Python writes the first-seen backup on the first connect (chu2/app/api.py).
onEvent("backup_saved", (info) => {
  toast(`Backup saved on this PC: the EQ your CHU 2 had on ${formatDate(info.saved_at)}. ` +
    "Restore it any time from the device menu.", "ok");
});

function errorText(error) {
  if (!error) return "";
  if (error.code === "unknown_filter_type") {
    return "Your CHU 2 reports a filter type this app doesn't know, so the app won't change its EQ. Unplug it to try again.";
  }
  return "Found a CHU 2 but couldn't open it. Close other EQ tools that may be using it; the app keeps trying.";
}

export const NoDevice = {
  setup() {
    const looking = ref(true); // the pulse stops after 30 s (brief §5.7)
    let timer = null;
    onMounted(() => { timer = setTimeout(() => { looking.value = false; }, 30000); });
    onBeforeUnmount(() => clearTimeout(timer));
    const error = computed(() => errorText(state.device_error));

    function explore() {
      ui.explore = true;
    }

    return { looking, error, explore };
  },
  template: `
    <main class="nodevice" data-test="no-device" aria-labelledby="nd-title">
      <section class="nd-card panel">
        <span class="icon icon-hero i-headphones" aria-hidden="true"></span>
        <p class="eyebrow">Unofficial EQ studio for the Moondrop CHU 2 DSP</p>
        <h1 id="nd-title" class="display">Plug in your CHU 2 DSP</h1>
        <p class="copy muted">The EQ lives inside your earphones. We read what's stored on them first and keep a backup before changing anything.</p>
        <p class="looking" role="status">
          <span :class="['pulse-dot', { pulsing: looking }]" aria-hidden="true"></span>Looking for CHU 2 DSP…
        </p>
        <p v-if="error" class="warn-line" role="alert" data-test="device-error">
          <span class="icon icon-16 i-warning" aria-hidden="true"></span><span>{{ error }}</span>
        </p>
        <h2 class="eyebrow">Not showing up?</h2>
        <ul class="tips">
          <li>Plug straight into the PC; avoid unpowered hubs.</li>
          <li>Close browser tabs using the CHU 2 (web EQ tools).</li>
          <li>Try another port or a data-capable USB-C/A adapter.</li>
        </ul>
        <div class="actions actions-start">
          <button type="button" class="btn" data-test="explore" @click="explore">Explore without a device</button>
        </div>
      </section>
      <p class="disclaimer" data-test="disclaimer">Unofficial community app · not affiliated with or endorsed by Moondrop · open source</p>
    </main>`,
};

export const StatusBanner = {
  setup() {
    const text = computed(() => {
      if (state.connected) return "";
      if (state.device_error) return errorText(state.device_error);
      if (ui.everConnected) return "CHU 2 unplugged. Your edits are kept; they're not on CHU 2.";
      if (ui.explore) return "No CHU 2 connected. Edit freely and save when it's plugged in.";
      return "";
    });
    return { text };
  },
  template: `
    <div v-if="text" class="banner" role="status" data-test="banner">
      <span class="icon icon-16 i-info" aria-hidden="true"></span><span>{{ text }}</span>
    </div>`,
};
