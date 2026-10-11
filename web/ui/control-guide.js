// The control sign guide next to the camera. See "Control signs" in the README.

// The one list to edit when a control sign changes.
export const CONTROL_GUIDE = [
  {
    label: "DONE",
    icon: "🖐️🖐️",
    does: "send your answer",
    how: "Both hands open, fingers spread, palms facing the camera, side by side",
  },
  {
    label: "CLEAR",
    icon: "👎👎",
    does: "start your answer again",
    how: "Both fists side by side, thumbs pointing down",
  },
  {
    label: "DELETE",
    icon: "👈👈",
    does: "remove the last sign",
    how: "Both index fingers pointing left, side by side",
  },
];

const TIP = "HELP and STOP: show both hands first, then place one on the other.";

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text) el.textContent = text;
  return el;
}

export function renderControlGuide(box) {
  const list = element("ul");
  for (const { label, icon, does, how } of CONTROL_GUIDE) {
    const item = element("li");
    const icons = element("span", "control-icon", icon);
    icons.setAttribute("aria-hidden", "true");
    const text = element("span");
    text.append(element("strong", "control-name", label), ` · ${does}`, element("span", "control-how", how));
    item.append(icons, text);
    list.append(item);
  }
  box.replaceChildren(element("h2", "", "Control signs · hold for 1 second"), list, element("p", "control-tip", TIP));
}
