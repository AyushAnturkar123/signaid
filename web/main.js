// Wires everything together and runs the conversation loop:
// medic speaks -> simplified question + answer mode -> patient signs -> confirm -> spoken answer.

import { api } from "./api.js";
import { startCamera } from "./camera.js";
import { setupRecorder } from "./recorder.js";
import { connectSigns } from "./socket.js";
import { speak, speechSupported, startListening } from "./speech.js";

const $ = (id) => document.getElementById(id);
const SEND_INTERVAL_MS = 66; // ~15 frames a second to the classifier
const MODE_NAMES = { yesno: "Yes / No", number: "Number", spelling: "Spelling", free: "Free" };
const INTRO = "I'm Deaf. Please speak to me, and I'll answer with signs.";

const state = { mode: "free", question: "", answer: [], log: [], hands: [] };
let sendToServer = () => {};
let lastSent = 0;
let recorder = { isLeftHanded: () => false };

function setMode(mode) {
  state.mode = mode;
  state.answer = [];
  for (const btn of $("mode-buttons").children) btn.classList.toggle("active", btn.dataset.mode === mode);
  renderAnswer();
}

function renderAnswer() {
  const text = state.mode === "spelling" ? state.answer.join("") : state.answer.join(" ");
  $("answer").textContent = text || "—";
  $("send-btn").disabled = state.answer.length === 0;
}

function addLog(role, text) {
  state.log.push({ role, text });
  const item = document.createElement("li");
  item.className = role;
  const who = document.createElement("span");
  who.className = "role";
  who.textContent = role === "medic" ? "Medic:" : "Patient:";
  item.append(who, text);
  $("log").append(item);
  item.scrollIntoView({ block: "nearest" });
}

function addSign(label) {
  // Yes/No and Number questions take a single answer; the latest sign replaces the previous one.
  if (state.mode === "yesno" || state.mode === "number") state.answer = [label];
  else state.answer.push(label);
  renderAnswer();
}

function onHands(hands) {
  state.hands = hands;
  const now = performance.now();
  if (now - lastSent < SEND_INTERVAL_MS) return;
  lastSent = now;
  sendToServer({ type: "landmarks", mode: state.mode, hands, left_handed: recorder.isLeftHanded() });
}

function onServerMessage(msg) {
  if (msg.type === "prediction") {
    let text;
    if (!state.hands.length) text = "No hand in view";
    else if (msg.label) text = `Seeing ${msg.label} · ${Math.round(msg.confidence * 100)}%`;
    else text = "Not a known sign";
    if (msg.distance != null) text += ` · dist ${msg.distance}`;
    $("live").textContent = text;
  } else if (msg.type === "sign") {
    addSign(msg.label);
  }
}

async function onMedicSpeech(text) {
  addLog("medic", text);
  $("heard").textContent = "";
  try {
    const { text: plain, mode } = await api.simplify(text);
    state.question = plain;
    $("question").textContent = plain;
    setMode(mode);
  } catch (e) {
    state.question = text;
    $("question").textContent = text;
  }
}

async function sendAnswer() {
  if (!state.answer.length) return;
  const signs = state.answer;
  let text;
  try {
    ({ text } = await api.answer(signs, state.mode, state.question));
  } catch {
    text = signs.join(" ");
  }
  addLog("patient", text);
  setMode("free");
  await speak(text);
}

async function showSummary() {
  const dialog = $("summary-dialog");
  $("summary-text").textContent = "Writing summary…";
  dialog.showModal();
  try {
    const { text } = await api.summary(state.log);
    $("summary-text").textContent = text;
  } catch (e) {
    $("summary-text").textContent = `Couldn't write the summary: ${e.message}`;
  }
}

function buildModeButtons(modes) {
  const nav = $("mode-buttons");
  for (const mode of Object.keys(modes)) {
    const btn = document.createElement("button");
    btn.dataset.mode = mode;
    btn.textContent = MODE_NAMES[mode] ?? mode;
    btn.addEventListener("click", () => setMode(mode));
    nav.append(btn);
  }
}

async function start() {
  $("start-screen").hidden = true;
  const modes = await api.modes();
  buildModeButtons(modes);
  setMode("free");
  recorder = setupRecorder(modes, MODE_NAMES, () => state.hands);
  sendToServer = connectSigns(onServerMessage, (connected) => {
    if (!connected) $("live").textContent = "Reconnecting to server…";
  });

  if (speechSupported) {
    startListening({
      onFinal: onMedicSpeech,
      onInterim: (text) => ($("heard").textContent = text),
      onStatus: (text) => ($("mic-status").textContent = text),
    });
  } else {
    $("mic-status").textContent = "Speech not supported, use Chrome";
  }

  addLog("patient", INTRO);
  speak(INTRO);

  try {
    await startCamera($("video"), $("overlay"), onHands);
  } catch (e) {
    $("live").textContent = `Camera error: ${e.message}`;
  }
}

$("start-btn").addEventListener("click", start);
$("send-btn").addEventListener("click", sendAnswer);
$("clear-btn").addEventListener("click", () => {
  state.answer = [];
  renderAnswer();
});
$("backspace-btn").addEventListener("click", () => {
  state.answer.pop();
  renderAnswer();
});
$("summary-btn").addEventListener("click", showSummary);
// Typed fallback for when speech recognition struggles (noisy room, no internet).
$("type-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("type-input").value.trim();
  if (!text) return;
  $("type-input").value = "";
  onMedicSpeech(text);
});
