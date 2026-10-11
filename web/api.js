// Small wrappers around the Python server's HTTP routes. See "Message formats" in the README.

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().then((d) => d.detail).catch(() => res.statusText);
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export const api = {
  modes: () => request("GET", "/api/modes"),
  counts: () => request("GET", "/api/samples"),
  addSamples: (label, signer, leftHanded, frames) =>
    request("POST", "/api/samples", { label, signer, left_handed: leftHanded, frames }),
  deleteSamples: (label, signer) =>
    request("DELETE", `/api/samples/${encodeURIComponent(label)}?signer=${encodeURIComponent(signer)}`),
  simplify: (text) => request("POST", "/api/simplify", { text }),
  answer: (signs, mode, question) => request("POST", "/api/answer", { signs, mode, question }),
  summary: (log) => request("POST", "/api/summary", { log }),
  followUp: (log) => request("POST", "/api/follow-up", { log }),
  opening: () => request("GET", "/api/opening"),
};
