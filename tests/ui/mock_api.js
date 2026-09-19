// Stand-in for window.pywebview.api (chu2/app/api.py) in UI tests.
// window.__mockState (set before this script) overrides the first snapshot;
// window.__mockLibrary is the library (conftest builds it with chu2.library).
(() => {
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const band = (type, frequency, gain, q) => ({ type, frequency, gain, q, bypass: false });
  const design = [
    band("peaking", 40, -1.5, 0.5), band("peaking", 200, -6, 0.6), band("peaking", 1400, -2.5, 1.6),
    band("peaking", 3500, -4.8, 1.0), band("peaking", 9000, -2, 1.5),
  ];
  const deviceBands = design.map(({ bypass, ...rest }) => rest);
  let state = Object.assign({
    rev: 1, connected: true, device_error: null, eq_on: true,
    design, device_bands: deviceBands, stored: clone(deviceBands), changes: 0, edited: false,
    auto_preamp: true,
    preamp: { preamp_db: 0, peak_db: -0.4, peak_hz: 20, device_peak_db: -0.4, method: "none",
              flipped: [], trim_index: null, warning: null },
    save: { state: "idle", kind: "save", step: null, reason: null, after_commit: false,
            mismatched: [], message: null },
    backup: { saved_at: "2026-09-19T14:02:00" },
    name: "My EQ", quick: null, settings: { theme: "atelier", confirm_save: true }, version: "0.1.0",
  }, window.__mockState || {});
  const calls = [];
  const next = (patch) => {
    state = Object.assign(clone(state), patch || {}, { rev: state.rev + 1 });
    return clone(state);
  };
  const saveState = (fields) => Object.assign(clone(state.save), fields);
  const busy = new Set(); // bands with a set_band still running
  const library = clone(window.__mockLibrary || { presets: [], recipes: { scenes: [], tweaks: [], intensities: [] } });
  const slug = (name) => name.toLowerCase().match(/[a-z0-9]+/g).join("-");
  const findPreset = (id) => library.presets.find((p) => p.id === id);
  const record = (name, args) => calls.push([name, ...clone(args)]);

  const api = {
    async get_state() { record("get_state", []); return clone(state); },
    async set_band(index, b) {
      record("set_band", [index, b]);
      if (busy.has(index)) window.__mock.overlap = true; // Python could apply them out of order
      busy.add(index);
      if (window.__mock.delayMs) await new Promise((r) => setTimeout(r, window.__mock.delayMs));
      busy.delete(index);
      const d = clone(state.design);
      d[index] = clone(b);
      return next({ design: d, changes: 1, edited: true });
    },
    async reset_bands() {
      record("reset_bands", []);
      const idle = [["low_shelf", 105, 0.71], ["peaking", 250, 1.0], ["peaking", 1000, 1.0],
                    ["peaking", 4000, 1.4], ["high_shelf", 10000, 0.71]];
      return next({ design: idle.map(([type, f, q]) => band(type, f, 0, q)), changes: 5, edited: true });
    },
    async set_design(bands, name, quick) {
      record("set_design", name === undefined ? [bands] : [bands, name, quick]);
      return next(Object.assign({ design: clone(bands), edited: true,
                                  quick: quick ? Object.assign({ notes: [], text: [] }, clone(quick)) : null },
                                name ? { name } : {}));
    },
    async set_eq_enabled(on) { record("set_eq_enabled", [on]); return next({ eq_on: on }); },
    async get_library() { record("get_library", []); return clone(library); },
    async apply_preset(id) {
      record("apply_preset", [id]);
      const p = findPreset(id);
      return next({ design: clone(p.bands), name: p.name, edited: true, changes: 5, quick: null });
    },
    async quick_tune(scene, tweaks, intensity) {
      record("quick_tune", [scene, tweaks, intensity]);
      const recipe = library.recipes.scenes.find((s) => s.id === scene);
      const preset = scene ? findPreset("scene:" + scene) : findPreset("official:flat");
      return next({ design: clone(preset.bands), name: recipe ? recipe.name : "Quick Tune", edited: true,
                    changes: 5, quick: { scene, tweaks: clone(tweaks), intensity,
                                         notes: tweaks.map((t) => `Tweak ${t}.`),
                                         text: [recipe ? recipe.about : "Tweaks only."] } });
    },
    async save_preset(name, tags) {
      record("save_preset", [name, tags]);
      library.presets.push({ id: "mine:" + slug(name), name, group: "mine", tags: clone(tags),
                             bands: clone(state.design), about: "", favourite: false, gaming: false,
                             on_chu2: false });
      state = Object.assign(clone(state), { name });
      return clone(library);
    },
    async rename_preset(id, name) { record("rename_preset", [id, name]); findPreset(id).name = name; return clone(library); },
    async delete_preset(id) {
      record("delete_preset", [id]);
      library.presets = library.presets.filter((p) => p.id !== id);
      return clone(library);
    },
    async set_favourite(id, on) { record("set_favourite", [id, on]); findPreset(id).favourite = on; return clone(library); },
    async set_setting(key, value) {
      record("set_setting", [key, value]);
      return next({ settings: Object.assign(clone(state.settings), { [key]: value }) });
    },
    async set_auto_preamp(on) { record("set_auto_preamp", [on]); return next({ auto_preamp: on }); },
    async free_smallest_band() { record("free_smallest_band", []); return next({}); },
    async save() {
      record("save", []);
      return next({ save: saveState({ state: state.connected ? "running" : "waiting_device",
                                      kind: "save", step: null }) });
    },
    async cancel_save() { record("cancel_save", []); return next({ save: saveState({ state: "idle" }) }); },
    async dismiss_save() { record("dismiss_save", []); return next({ save: saveState({ state: "idle" }) }); },
    async restore_original() {
      record("restore_original", []);
      return next({ save: saveState({ state: "running", kind: "restore", step: null }) });
    },
    async close_app(action) { record("close_app", [action]); return clone(state); },
    // Import & share: previews built by chu2.transfer in conftest. A text with
    // "CHU2-" in it reads as the share code, one with "Filter" as the APO file.
    async import_file() {
      record("import_file", []);
      return window.__mock.cancelDialog ? { cancelled: true } : clone(library.previews.apo);
    },
    async import_text(text, name) {
      record("import_text", [text, name]);
      if (text.includes("CHU2-")) return clone(library.previews.code);
      if (text.includes("Filter")) return clone(library.previews.apo);
      return { error: "No EQ filters were found. Paste a share code, or an Equalizer APO / AutoEq / Peace text." };
    },
    async export_file(fmt) {
      record("export_file", [fmt]);
      return window.__mock.cancelDialog ? { cancelled: true }
        : { saved: "Documents/My EQ" + (fmt === "apo" ? ".txt" : ".chu2.json") };
    },
    async share_code() { record("share_code", []); return clone(library.share); },
    async open_data_folder() { record("open_data_folder", []); return { folder: "AppData/Roaming/CHU2Studio" }; },
  };

  window.__mock = {
    calls,
    delayMs: 0,      // set in a test to make Python answer slowly
    cancelDialog: false, // set in a test: the user cancels the Open / Save dialog
    overlap: false,  // true if one band ever had two set_band calls running at once
    state: () => clone(state),
    // Python pushed a new snapshot: patch fields, bump rev, deliver it.
    push(patch) {
      const snap = next(patch);
      window.chu2.onEvent("state", snap);
      return snap;
    },
    emit(name, data) { window.chu2.onEvent(name, data); },
  };
  window.pywebview = { api };
  window.addEventListener("DOMContentLoaded", () => {
    setTimeout(() => window.dispatchEvent(new Event("pywebviewready")), 0);
  });
})();
