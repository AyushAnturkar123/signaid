// Webcam + MediaPipe hand tracking. Runs entirely in the browser; no video leaves the device.

import { DrawingUtils, FilesetResolver, HandLandmarker } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1";

const WASM_PATH = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODEL_PATH =
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

// MediaPipe result -> [{ handedness: "Left" | "Right", points: [[x, y, z] x 21] }]
function toHands(result) {
  const handedness = result.handedness ?? result.handednesses ?? [];
  return result.landmarks.map((points, i) => ({
    handedness: handedness[i]?.[0]?.categoryName ?? null,
    points: points.map((p) => [p.x, p.y, p.z]),
  }));
}

// Calls onHands(hands) for every new video frame.
export async function startCamera(video, canvas, onHands) {
  video.srcObject = await navigator.mediaDevices.getUserMedia({
    video: { width: 640, height: 480, facingMode: "user" },
    audio: false,
  });
  await video.play();

  const fileset = await FilesetResolver.forVisionTasks(WASM_PATH);
  const landmarker = await HandLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: MODEL_PATH, delegate: "GPU" },
    runningMode: "VIDEO",
    numHands: 2,
  });

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  const draw = new DrawingUtils(ctx);
  let lastVideoTime = -1;

  function loop() {
    if (video.currentTime !== lastVideoTime) {
      lastVideoTime = video.currentTime;
      const result = landmarker.detectForVideo(video, performance.now());
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const landmarks of result.landmarks) {
        draw.drawConnectors(landmarks, HandLandmarker.HAND_CONNECTIONS, { color: "#4c9eff", lineWidth: 4 });
        draw.drawLandmarks(landmarks, { color: "#ffffff", fillColor: "#0b6bcb", radius: 4 });
      }
      onHands(toHands(result));
    }
    requestAnimationFrame(loop);
  }
  loop();
}
