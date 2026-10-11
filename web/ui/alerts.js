// Visual alerts. The patient can't hear the app, so everything it says or hears also shows on screen.

const NEW_QUESTION_MS = 2000;
const SPOKEN_MS = 5000;

const $ = (id) => document.getElementById(id);
let questionTimer;
let spokenTimer;

// Flash the question area and show a "New question" badge. With prefers-reduced-motion the CSS
// swaps the flash for a static highlight.
export function flashNewQuestion() {
  const card = $("question-card");
  card.classList.remove("new");
  void card.offsetWidth; // restart the flash if a question is already highlighted
  card.classList.add("new");
  $("new-question-badge").hidden = false;
  clearTimeout(questionTimer);
  questionTimer = setTimeout(() => {
    card.classList.remove("new");
    $("new-question-badge").hidden = true;
  }, NEW_QUESTION_MS);
}

// Show what the app is saying out loud to the medic.
export function showSpoken(text) {
  if (!text) return;
  const banner = $("spoken-banner");
  banner.textContent = `🔊 Said to medic: ${text}`;
  banner.hidden = false;
  clearTimeout(spokenTimer);
  spokenTimer = setTimeout(() => (banner.hidden = true), SPOKEN_MS);
}
