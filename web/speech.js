// Speech-to-text and text-to-speech with the browser's Web Speech API (use Chrome).

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
export const speechSupported = Boolean(Recognition);

let recognizer = null;
let enabled = false; // the mic button is on
let paused = false; // true while the app is speaking, so it doesn't transcribe itself
let blocked = false; // true if the mic permission was denied
let handlers = {};

function safeStart() {
  try {
    recognizer.start();
  } catch {
    // already running
  }
}

// handlers: { onFinal(text), onInterim(text), onStatus(text) }
export function startListening(h) {
  handlers = h;
  enabled = true;
  blocked = false; // try again, in case permission was granted since
  if (recognizer) {
    safeStart();
    return;
  }
  recognizer = new Recognition();
  recognizer.continuous = true;
  recognizer.interimResults = true;
  recognizer.lang = "en-US";

  recognizer.onstart = () => handlers.onStatus?.("🎤 Listening");
  recognizer.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const text = result[0].transcript.trim();
      if (result.isFinal) {
        if (text) handlers.onFinal?.(text);
      } else {
        interim += result[0].transcript;
      }
    }
    handlers.onInterim?.(interim);
  };
  recognizer.onerror = (event) => {
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      blocked = true;
      handlers.onStatus?.("Mic blocked");
    } else if (event.error !== "no-speech" && event.error !== "aborted") {
      handlers.onStatus?.(`Mic error: ${event.error}`);
    }
  };
  // Chrome stops listening after a while; restart unless we paused it on purpose.
  recognizer.onend = () => {
    if (enabled && !paused && !blocked) safeStart();
    else if (!enabled) handlers.onStatus?.("🎤 Mic off");
  };
  safeStart();
}

export function stopListening() {
  enabled = false;
  recognizer?.abort();
  handlers.onStatus?.("🎤 Mic off");
}

export function speak(text) {
  return new Promise((resolve) => {
    if (!text) return resolve();
    paused = true;
    recognizer?.abort();
    handlers.onStatus?.("🔊 Speaking");
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    const done = () => {
      paused = false;
      if (recognizer && enabled && !blocked) safeStart();
      else handlers.onStatus?.(enabled ? "🎤 Listening" : "🎤 Mic off");
      resolve();
    };
    utterance.onend = done;
    utterance.onerror = done;
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  });
}
