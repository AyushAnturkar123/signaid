// Phone-only touches: keep the screen awake, since the patient never touches it.

let wakeLock = null;

async function keepAwake() {
  try {
    wakeLock = await navigator.wakeLock?.request("screen");
  } catch {
    // not allowed right now (e.g. low battery); the phone's own screen timeout applies
  }
}

// Call once the patient has pressed Start: a wake lock needs a visible page and a user action.
export function setupPhone() {
  keepAwake();
  // The lock is dropped whenever the app goes to the background, so take it again on return.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") keepAwake();
  });
}
