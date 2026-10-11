// Full-screen camera, with a caption bar at the bottom that is only shown in full screen.
// Everything outside the camera is hidden in full screen, so the bar repeats what the patient
// needs: what the medic said, what they've signed so far, and the confirm prompt.

const $ = (id) => document.getElementById(id);

function text(el) {
  return el.textContent.trim();
}

function updateBar() {
  const heard = text($("heard"));
  const question = text($("question"));
  $("fs-medic").textContent = heard || question;

  const confirm = $("confirm-prompt");
  const confirming = !confirm.hidden && text(confirm);
  const answer = text($("answer"));
  $("fs-patient").textContent = confirming
    ? text(confirm)
    : `You signed: ${answer && answer !== "—" ? answer : "…"}`;
  $("fs-patient").classList.toggle("confirming", Boolean(confirming));
}

export function setupFullscreen() {
  const camera = $("camera");
  const btn = $("fullscreen-btn");

  btn.addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else camera.requestFullscreen().catch(() => {});
  });
  document.addEventListener("fullscreenchange", () => {
    const on = document.fullscreenElement === camera;
    btn.textContent = on ? "✕ Exit full screen" : "⛶ Full screen";
    btn.setAttribute("aria-pressed", String(on));
    if (on) updateBar();
  });

  // Keep the bar in sync with the rest of the page without touching main.js's logic.
  const watch = { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ["hidden"] };
  const observer = new MutationObserver(updateBar);
  for (const id of ["heard", "question", "answer", "confirm-prompt"]) observer.observe($(id), watch);
  updateBar();
}
