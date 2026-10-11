// Full-screen camera, with a caption bar at the bottom that is only shown in full screen.
// Everything outside the camera is hidden in full screen, so the bar repeats what the patient
// needs: what the medic said and what they've signed so far.

const $ = (id) => document.getElementById(id);

function text(el) {
  return el.textContent.trim();
}

function updateBar() {
  const heard = text($("heard"));
  const question = text($("question"));
  $("fs-medic").textContent = heard || question;

  const answer = text($("answer"));
  $("fs-patient").textContent = `You signed: ${answer && answer !== "—" ? answer : "…"}`;
}

export function setupFullscreen() {
  const camera = $("camera");
  const btn = $("fullscreen-btn");

  function show(on) {
    btn.textContent = on ? "✕ Exit full screen" : "⛶ Full screen";
    btn.setAttribute("aria-pressed", String(on));
    if (on) updateBar();
  }

  if (camera.requestFullscreen) {
    btn.addEventListener("click", () => {
      if (document.fullscreenElement) document.exitFullscreen();
      else camera.requestFullscreen().catch(() => {});
    });
    document.addEventListener("fullscreenchange", () => show(document.fullscreenElement === camera));
  } else {
    // iPhones can't put an element in real full screen, so the camera covers the page instead.
    btn.addEventListener("click", () => {
      const on = camera.classList.toggle("fullscreen");
      document.body.classList.toggle("camera-fullscreen", on);
      show(on);
    });
  }

  // Keep the bar in sync with the rest of the page without touching main.js's logic.
  const watch = { childList: true, characterData: true, subtree: true };
  const observer = new MutationObserver(updateBar);
  for (const id of ["heard", "question", "answer"]) observer.observe($(id), watch);
  updateBar();
}
