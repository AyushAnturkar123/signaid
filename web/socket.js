// WebSocket to the Python sign classifier. Reconnects automatically if the server restarts.

export function connectSigns(onMessage, onStatus = () => {}) {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/signs`;
  let ws;

  function open() {
    ws = new WebSocket(url);
    ws.onopen = () => onStatus(true);
    ws.onmessage = (event) => onMessage(JSON.parse(event.data));
    ws.onclose = () => {
      onStatus(false);
      setTimeout(open, 1000);
    };
  }
  open();

  // Returns a send function. Frames are dropped while disconnected.
  return (msg) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  };
}
