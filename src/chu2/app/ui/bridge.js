// The only file that knows about pywebview.
// Calls go to window.pywebview.api (each returns a Promise); Python pushes
// events by running window.chu2.onEvent(name, data) (chu2/app/main.py).

const handlers = new Map();

export function onEvent(name, fn) {
  if (!handlers.has(name)) handlers.set(name, []);
  handlers.get(name).push(fn);
}

window.chu2 = {
  onEvent(name, data) {
    for (const fn of handlers.get(name) || []) {
      try {
        fn(data);
      } catch (err) {
        console.error("chu2 event", name, err);
      }
    }
  },
};

let ready = null;

export function apiReady() {
  if (!ready) {
    ready = new Promise((resolve) => {
      const done = () => resolve(window.pywebview.api);
      const api = window.pywebview && window.pywebview.api;
      if (api && typeof api.get_state === "function") done();
      else window.addEventListener("pywebviewready", done, { once: true });
    });
  }
  return ready;
}

export async function call(method, ...args) {
  const api = await apiReady();
  return api[method](...args);
}
