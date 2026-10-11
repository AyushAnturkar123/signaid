// Shows which step the patient is in: the status line by the camera and the confirm prompt.

const STATUS = {
  answering: "Sign your answer, then lower your hand",
  confirming: "Sign YES to send, NO to redo",
};

const $ = (id) => document.getElementById(id);

export function renderStep(step, answer) {
  const confirming = step === "confirming";
  $("step-status").textContent = STATUS[step];
  $("step-status").classList.toggle("confirming", confirming);

  const prompt = $("confirm-prompt");
  prompt.hidden = !confirming;
  prompt.replaceChildren();
  if (!confirming) return;
  const said = document.createElement("strong");
  said.textContent = `"${answer}"`;
  prompt.append("You said: ", said, `. ${STATUS.confirming}.`);
}
