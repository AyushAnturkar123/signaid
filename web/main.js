// Wires everything together and runs the conversation loop:
// medic speaks -> simplified question + answer mode -> patient signs -> DONE -> spoken answer.
// The patient never touches the computer: they answer, correct and send by signing.

import { api } from "./api.js";
import { startCamera } from "./camera.js";
import { setupRecorder } from "./recorder.js";
import { connectSigns } from "./socket.js";
import { speak, speechSupported, startListening, stopListening } from "./speech.js";
import { flashNewQuestion, showSpoken } from "./ui/alerts.js";
import { renderControlGuide } from "./ui/control-guide.js";
import { setupFullscreen } from "./ui/fullscreen.js";
import { setupPhone } from "./ui/phone.js";

const $ = (id) => document.getElementById(id);
const SEND_INTERVAL_MS = 66; // ~15 frames a second to the classifier
const MODE_NAMES = { yesno: "Yes / No", number: "Number", spelling: "Spelling", free: "Free", location: "Pain location" };
const INTRO = "I'm Deaf. Please speak to me, and I'll answer with signs.";

// scanning: recognition is on. It starts off, so testing or setting up never adds signs by accident.
const state = { mode: "free", question: "", answer: [], log: [], hands: [], modes: {}, scanning: false };
let sendToServer = () => {};
let lastSent = 0;
let recorder = { isLeftHanded: () => false };

function answerText() {
  return state.mode === "spelling" ? state.answer.join("") : state.answer.join(" ");
}

function setMode(mode) {
  state.mode = mode;
  state.answer = [];
  for (const btn of $("mode-buttons").children) btn.classList.toggle("active", btn.dataset.mode === mode);
  renderQuickReplies();
  renderAnswer();
}

// One tap-to-answer button per sign in the current mode, as a backup when a sign isn't recognized.
function renderQuickReplies() {
  const box = $("quick-replies");
  box.replaceChildren();
  for (const label of state.modes[state.mode] ?? []) {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.addEventListener("click", () => addSign(label));
    box.append(btn);
  }
}

function renderAnswer() {
  $("answer").textContent = answerText() || "—";
  $("send-btn").disabled = state.answer.length === 0;
}

function clearAnswer() {
  state.answer = [];
  renderAnswer();
}

function removeLastSign() {
  state.answer.pop();
  renderAnswer();
}

// Control signs work in every mode and are never added to the answer.
// DONE sends the answer straight away; CLEAR and DELETE are for corrections before that.
const CONTROLS = {
  DONE: sendAnswer,
  CLEAR: clearAnswer,
  DELETE: removeLastSign,
};

function addLog(role, text) {
  state.log.push({ role, text });
  const item = document.createElement("li");
  item.className = role;
  const who = document.createElement("span");
  who.className = "role";
  who.textContent = { medic: "Medic:", signaid: "SignAid:" }[role] ?? "Patient:";
  item.append(who, text);
  $("log").append(item);
  // Scroll the list only, never the page: the question and camera must stay in view.
  $("log").scrollTop = $("log").scrollHeight;
}

function addSign(label) {
  if (CONTROLS[label]) return CONTROLS[label]();
  // Yes/No and Number questions take a single answer; the latest sign replaces the previous one.
  if (state.mode === "yesno" || state.mode === "number") state.answer = [label];
  else state.answer.push(label);
  renderAnswer();
}

function onHands(hands) {
  state.hands = hands;
  if (!state.scanning) return; // hands are still tracked (the recorder needs them), just not recognized
  const now = performance.now();
  if (now - lastSent < SEND_INTERVAL_MS) return;
  lastSent = now;
  sendToServer({ type: "landmarks", mode: state.mode, hands, left_handed: recorder.isLeftHanded() });
}

const PAUSED_TEXT = "Paused · press Start scanning";

function setScanning(on) {
  state.scanning = on;
  const btn = $("scan-btn");
  btn.setAttribute("aria-pressed", String(on));
  btn.textContent = on ? "⏸ Pause scanning" : "▶ Start scanning";
  if (!on) $("live").textContent = PAUSED_TEXT;
}

function onServerMessage(msg) {
  if (!state.scanning) return; // ignore replies to frames sent just before pausing
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

function showQuestion(text, from) {
  state.question = text;
  $("question").textContent = text;
  $("question-from").textContent = from === "signaid" ? "SignAid asks" : "Medic said";
  flashNewQuestion();
}

async function onMedicSpeech(text) {
  addLog("medic", text);
  $("heard").textContent = "";
  try {
    const { text: plain, mode } = await api.simplify(text);
    showQuestion(plain, "medic");
    setMode(mode);
  } catch (e) {
    showQuestion(text, "medic");
  }
}

// After an answer, SignAid may ask one short follow-up (e.g. PAIN -> "How bad is your pain,
// 1 to 10?") and switch to the tab the patient answers in. The server stops after 3 in a row.
async function askFollowUp() {
  let next;
  try {
    next = await api.followUp(state.log);
  } catch {
    return;
  }
  if (!next.question) return;
  // A medic question that arrived while we waited takes priority.
  if (state.log.at(-1)?.role !== "patient") return;
  addLog("signaid", next.question);
  showQuestion(next.question, "signaid");
  setMode(next.mode);
}

// Everything the app says out loud is also shown on screen.
function say(text) {
  showSpoken(text);
  return speak(text);
}

async function sendAnswer() {
  if (!state.answer.length) return;
  const { answer: signs, mode, question } = state;
  setMode("free"); // clear the answer right away, so a second DONE can't send it twice
  let text;
  try {
    ({ text } = await api.answer(signs, mode, question));
  } catch {
    text = signs.join(" ");
  }
  addLog("patient", text);
  // Side by side: a follow-up must not wait on speech, which sometimes never reports finishing.
  await Promise.all([say(text), askFollowUp()]);
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
  setupPhone();
  const modes = await api.modes();
  state.modes = modes;
  buildModeButtons(modes);
  setMode("free");
  recorder = setupRecorder(modes, MODE_NAMES, () => state.hands);
  sendToServer = connectSigns(onServerMessage, (connected) => {
    if (!connected) $("live").textContent = "Reconnecting to server…";
  });

  if (!speechSupported) {
    $("mic-btn").textContent = "Speech not supported, use Chrome";
    $("mic-btn").disabled = true;
  }
  setMic(true);

  addLog("patient", INTRO);
  say(INTRO);

  try {
    await startCamera($("video"), $("overlay"), onHands);
    if (!state.scanning) $("live").textContent = PAUSED_TEXT;
  } catch (e) {
    $("live").textContent = `Camera error: ${e.message}`;
  }
}

// The mic turns on at Start, so nobody has to touch the computer. The button can still turn it off.
let micOn = false;
function setMic(on) {
  if (on === micOn || !speechSupported) return;
  micOn = on;
  const btn = $("mic-btn");
  btn.setAttribute("aria-pressed", String(micOn));
  btn.classList.toggle("active", micOn);
  if (micOn) {
    startListening({
      onFinal: onMedicSpeech,
      onInterim: (text) => ($("heard").textContent = text),
      onStatus: (text) => (btn.textContent = text),
    });
  } else {
    stopListening();
    $("heard").textContent = "";
  }
}

// The mic is off while the "Record signs" panel is open: background speech would otherwise be
// taken as a medic question and switch the answer mode mid-recording.
let micPausedForRecorder = false;
new MutationObserver(() => {
  const open = !$("recorder").hidden;
  if (open && micOn) {
    micPausedForRecorder = true;
    setMic(false);
  } else if (!open && micPausedForRecorder) {
    micPausedForRecorder = false;
    setMic(true);
  }
}).observe($("recorder"), { attributes: true, attributeFilter: ["hidden"] });

renderControlGuide($("control-guide"));
setupFullscreen();

$("start-btn").addEventListener("click", start);
$("scan-btn").addEventListener("click", () => setScanning(!state.scanning));
$("mic-btn").addEventListener("click", () => setMic(!micOn));
// Send, Clear and ⌫ stay as a backup for the medic. The patient never needs them.
$("send-btn").addEventListener("click", sendAnswer);
$("clear-btn").addEventListener("click", clearAnswer);
$("backspace-btn").addEventListener("click", removeLastSign);
$("summary-btn").addEventListener("click", showSummary);
// Typed fallback for when speech recognition struggles (noisy room, no internet).
$("type-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("type-input").value.trim();
  if (!text) return;
  $("type-input").value = "";
  onMedicSpeech(text);
});

// DEV ONLY: keys D, C and X act as the DONE, CLEAR and DELETE signs, for testing before the team
// has recorded samples of the control signs. Delete this block once they are recorded.
const DEV_CONTROL_KEYS = { d: "DONE", c: "CLEAR", x: "DELETE" };
document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target.closest?.("input, select, textarea")) return; // typing, not a shortcut
  const label = DEV_CONTROL_KEYS[event.key.toLowerCase()];
  if (label) addSign(label);
});
// END DEV ONLY
