// "Record signs" panel: captures hand poses and saves them to the server as training samples.

import { api } from "./api.js";

const SAMPLES_PER_RECORDING = 20;
const SAMPLE_GAP_MS = 150;
const COUNTDOWN_SECONDS = 3;
const TIMEOUT_MS = 15000;
const STORAGE_KEY = "signaid.recorder";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? {};
  } catch {
    return {};
  }
}

function saveSettings(settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // storage unavailable; settings just won't be remembered
  }
}

// getHands() returns the hands in the latest camera frame.
export function setupRecorder(modes, modeNames, getHands) {
  const panel = $("recorder");
  const signer = $("rec-signer");
  const leftHanded = $("rec-left");
  const select = $("rec-label");
  const recordBtn = $("rec-btn");
  const status = $("rec-status");

  // Each sign is listed once, under the first mode it appears in (YES/NO are also in Free).
  const listed = new Set();
  const uniqueModes = Object.entries(modes).map(([mode, labels]) => {
    const fresh = labels.filter((label) => !listed.has(label));
    fresh.forEach((label) => listed.add(label));
    return [mode, fresh];
  });
  for (const [mode, labels] of uniqueModes) {
    const group = document.createElement("optgroup");
    group.label = modeNames[mode] ?? mode;
    for (const label of labels) group.append(new Option(label, label));
    select.append(group);
  }

  const saved = loadSettings();
  signer.value = saved.signer ?? "";
  leftHanded.checked = Boolean(saved.leftHanded);
  if (saved.label) select.value = saved.label;
  const remember = () =>
    saveSettings({ signer: signer.value, leftHanded: leftHanded.checked, label: select.value });
  signer.addEventListener("change", remember);
  leftHanded.addEventListener("change", remember);
  select.addEventListener("change", remember);

  async function refreshCounts() {
    const counts = await api.counts();
    const box = $("rec-counts");
    box.replaceChildren();
    for (const [mode, labels] of uniqueModes) {
      const heading = document.createElement("h3");
      heading.textContent = modeNames[mode] ?? mode;
      const chips = document.createElement("div");
      chips.className = "chips";
      for (const label of labels) {
        const n = counts[label] ?? 0;
        const chip = document.createElement("span");
        chip.className = `chip ${n >= SAMPLES_PER_RECORDING * 3 ? "ok" : "low"}`;
        chip.textContent = `${label} ${n}`;
        chips.append(chip);
      }
      box.append(heading, chips);
    }
  }

  $("recorder-toggle").addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) refreshCounts().catch((e) => (status.textContent = e.message));
  });

  recordBtn.addEventListener("click", async () => {
    if (!signer.value.trim()) {
      status.textContent = "Enter your name first, so samples can be tested per person.";
      signer.focus();
      return;
    }
    const label = select.value;
    recordBtn.disabled = true;
    try {
      for (let s = COUNTDOWN_SECONDS; s > 0; s--) {
        status.textContent = `Get ready to sign ${label}… ${s}`;
        await sleep(1000);
      }
      const frames = [];
      const started = Date.now();
      while (frames.length < SAMPLES_PER_RECORDING && Date.now() - started < TIMEOUT_MS) {
        const hands = getHands();
        if (hands.length) frames.push(hands);
        status.textContent = hands.length
          ? `Recording ${label}: ${frames.length}/${SAMPLES_PER_RECORDING} — move a little between samples`
          : "No hand in view…";
        await sleep(SAMPLE_GAP_MS);
      }
      if (!frames.length) throw new Error("No hands were detected, nothing saved.");
      const { count } = await api.addSamples(label, signer.value.trim(), leftHanded.checked, frames);
      status.textContent = `Saved ${frames.length} samples of ${label} (${count} total).`;
      await refreshCounts();
    } catch (e) {
      status.textContent = `Error: ${e.message}`;
    } finally {
      recordBtn.disabled = false;
    }
  });

  $("rec-delete").addEventListener("click", async () => {
    const label = select.value;
    const name = signer.value.trim();
    if (!name) {
      status.textContent = "Enter your name to delete your samples.";
      return;
    }
    if (!confirm(`Delete all of ${name}'s samples of ${label}?`)) return;
    const { removed } = await api.deleteSamples(label, name);
    status.textContent = `Deleted ${removed} samples of ${label}.`;
    await refreshCounts();
  });

  return { isLeftHanded: () => leftHanded.checked };
}
