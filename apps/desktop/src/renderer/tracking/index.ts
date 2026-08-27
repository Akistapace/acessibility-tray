import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
// Static top-of-file import, per the task brief's own note -- NOT the inline
// `await import(...)` form. The default export is a Promise that resolves
// once the WASM runtime finishes initializing (see pointTracker.ts's header
// comment and task-15-report.md for why this can't be touched synchronously
// at module scope), so it's awaited once below, inside main().
import cvReadyPromise from "@techstark/opencv-js";
import type { Mat as CvMat } from "@techstark/opencv-js";
import { computeFaceMetrics, EYE_OUTER_A, EYE_OUTER_B, GESTURE_LANDMARK_GROUPS, type Point } from "./faceMetrics";
import { triggerProgress } from "@facemesh-mouse/shared";
import { PointTracker } from "./pointTracker";

export {}; // module scope

declare global {
  interface Window {
    tracking: {
      sendFrame: (frame: unknown) => void;
      cameraError: () => void;
      onSetPreview: (callback: (enabled: boolean) => void) => () => void;
      onHighlightGesture: (callback: (gesture: string | null) => void) => () => void;
    };
  }
}

const WORK_WIDTH = 640;
const WORK_HEIGHT = 480;
const PREVIEW_WIDTH = 480;
const PREVIEW_HEIGHT = 360;
const JPEG_QUALITY = 0.8;

// Hoisted to module scope (rather than declared inside main(), where the
// brief's own code sample implies it lives alongside WORK_WIDTH/WORK_HEIGHT)
// so renderPreviewJpeg below can read it -- index.html's <script> tag comes
// after the <canvas id="work"> element, so it already exists in the DOM by
// the time this runs.
const workCanvas = document.getElementById("work") as HTMLCanvasElement;

const previewCanvas = document.createElement("canvas");
previewCanvas.width = PREVIEW_WIDTH;
previewCanvas.height = PREVIEW_HEIGHT;
const previewCtx = previewCanvas.getContext("2d")!;

// Monotone-chain convex hull, ascending x (ties by y). Used to outline a
// highlighted gesture's actual landmark points instead of a padded bounding
// shape.
function convexHull(points: Point[]): Point[] {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length <= 2) return pts;
  const cross = (o: Point, a: Point, b: Point) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: Point[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: Point[] = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

function renderPreviewJpeg(metrics: ReturnType<typeof computeFaceMetrics>): string {
  previewCtx.drawImage(workCanvas, 0, 0, WORK_WIDTH, WORK_HEIGHT, 0, 0, PREVIEW_WIDTH, PREVIEW_HEIGHT);
  if (metrics) {
    const leftEye: Point = [
      metrics.landmarks[EYE_OUTER_A][0] * PREVIEW_WIDTH,
      metrics.landmarks[EYE_OUTER_A][1] * PREVIEW_HEIGHT,
    ];
    const rightEye: Point = [
      metrics.landmarks[EYE_OUTER_B][0] * PREVIEW_WIDTH,
      metrics.landmarks[EYE_OUTER_B][1] * PREVIEW_HEIGHT,
    ];
    const center: Point = [metrics.noseX * PREVIEW_WIDTH, metrics.noseY * PREVIEW_HEIGHT];

    previewCtx.strokeStyle = "rgb(255, 255, 0)";
    previewCtx.lineWidth = 1;
    previewCtx.beginPath();
    previewCtx.moveTo(leftEye[0], leftEye[1]);
    previewCtx.lineTo(rightEye[0], rightEye[1]);
    previewCtx.stroke();

    previewCtx.fillStyle = "rgb(0, 255, 0)";
    for (const [x, y] of [leftEye, rightEye]) {
      previewCtx.beginPath();
      previewCtx.arc(x, y, 2, 0, 2 * Math.PI);
      previewCtx.fill();
    }

    previewCtx.fillStyle = "rgb(255, 0, 0)";
    previewCtx.beginPath();
    previewCtx.arc(center[0], center[1], 5, 0, 2 * Math.PI);
    previewCtx.fill();
  }
  if (metrics && highlightedGesture) {
    const groups = GESTURE_LANDMARK_GROUPS[highlightedGesture];
    if (groups?.length) {
      // Green while building up to the gesture's trigger threshold, blue
      // once it's fully met (progress reaches 1) -- same 0..1 value the
      // Gestos tab's own progress bar reads, via the same shared
      // triggerProgress used to fire the gesture in the first place.
      const threshold = gestureThresholds[highlightedGesture];
      const progress = threshold !== undefined ? triggerProgress(highlightedGesture, metrics, threshold) : 0;
      const color = progress >= 1 ? "rgb(64, 156, 255)" : "rgb(0, 255, 0)";
      previewCtx.save();
      // Each sub-group gets its own hull, so a "_both" gesture (two eyes,
      // two eyebrows) shows two separate shapes instead of one hull spanning
      // the gap between them.
      for (const indices of groups) {
        const pts: Point[] = indices.map((i) => [
          metrics.landmarks[i][0] * PREVIEW_WIDTH,
          metrics.landmarks[i][1] * PREVIEW_HEIGHT,
        ]);
        const hull = convexHull(pts);
        if (hull.length >= 3) {
          previewCtx.globalAlpha = 0.25;
          previewCtx.fillStyle = color;
          previewCtx.beginPath();
          previewCtx.moveTo(hull[0][0], hull[0][1]);
          for (const [x, y] of hull.slice(1)) previewCtx.lineTo(x, y);
          previewCtx.closePath();
          previewCtx.fill();
          previewCtx.globalAlpha = 1;
          previewCtx.strokeStyle = color;
          previewCtx.lineWidth = 1.5;
          previewCtx.stroke();
        }
        // Mesh vertices for the highlighted group, drawn on top of the hull
        // so the actual tracked points (not just the enclosing shape) are
        // visible.
        previewCtx.fillStyle = color;
        for (const [x, y] of pts) {
          previewCtx.beginPath();
          previewCtx.arc(x, y, 1.5, 0, 2 * Math.PI);
          previewCtx.fill();
        }
      }
      previewCtx.restore();
    }
  }
  const dataUrl = previewCanvas.toDataURL("image/jpeg", JPEG_QUALITY);
  return dataUrl.slice(dataUrl.indexOf(",") + 1);
}

// Mirrors engine.py's _SEED_LANDMARKS/_head_size_px exactly.
const SEED_LANDMARKS = [98, 327, 168, 6, 197, 195, 5, 4, 234, 454, 127, 356, 122, 351];

function headSizePx(landmarks: Point[], width: number, height: number): number {
  const left = landmarks[EYE_OUTER_A];
  const right = landmarks[EYE_OUTER_B];
  return Math.hypot((left[0] - right[0]) * width, (left[1] - right[1]) * height);
}

let previewEnabled = false;
window.tracking.onSetPreview((enabled) => { previewEnabled = enabled; });

let highlightedGesture: string | null = null;
window.tracking.onHighlightGesture((gesture) => { highlightedGesture = gesture; });

// Per-gesture trigger thresholds, needed to color the highlight overlay
// above -- this window never owns config, it just needs to read the same
// thresholds the Gestos tab's progress bars use. Populated from whichever
// window's get_config/save_config triggers a broadcast; requested here too
// so a preview opened before any other window touches config still gets it.
let gestureThresholds: Record<string, number> = {};
window.backend.on("config", (message) => {
  const config = (message as { config: { gestures: Record<string, { threshold: number }>} }).config;
  gestureThresholds = Object.fromEntries(
    Object.entries(config.gestures).map(([name, g]) => [name, g.threshold])
  );
});
window.backend.send({ type: "get_config" });

async function main(): Promise<void> {
  const video = document.getElementById("video") as HTMLVideoElement;
  const workCtx = workCanvas.getContext("2d", { willReadFrequently: true })!;

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: WORK_WIDTH, height: WORK_HEIGHT },
      audio: false,
    });
  } catch {
    window.tracking.cameraError();
    return;
  }
  video.srcObject = stream;
  await video.play();

  const vision = await FilesetResolver.forVisionTasks("assets/wasm");
  const faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: "assets/face_landmarker.task" },
    runningMode: "VIDEO",
    numFaces: 1,
  });

  // Resolved once here, alongside the other async setup above -- everything
  // downstream (the loop's per-frame cv.Mat/cv.imread/cv.cvtColor calls, and
  // PointTracker's own cv.Size/cv.TermCriteria construction) uses this same
  // ready `cv`, never the raw pre-await import.
  const cv = await cvReadyPromise;
  const pointTracker = new PointTracker(cv);

  // ~30fps, matching engine.py's FRAME_INTERVAL_S = 1/30. A self-scheduling
  // setTimeout is used instead of requestAnimationFrame: this window is
  // never shown (show: false, permanently, by design), and Chromium
  // throttles rAF to ~1Hz or less for windows that are never shown.
  const FRAME_INTERVAL_MS = 33;
  // Frame work (MediaPipe inference, optical flow) takes a variable amount
  // of time each iteration. Scheduling the next call relative to "now" (as
  // setTimeout(loop, FRAME_INTERVAL_MS) in `finally` would) lets that
  // variance directly become cadence jitter -- cursor updates arriving at
  // uneven intervals reads as choppy motion even when each individual delta
  // is correct. Targeting a fixed nextFrameAt instead keeps the cadence
  // steady across frames of differing cost.
  const MAX_CATCHUP_MS = FRAME_INTERVAL_MS * 3;
  let nextFrameAt = performance.now() + FRAME_INTERVAL_MS;

  const scheduleNextFrame = () => {
    nextFrameAt += FRAME_INTERVAL_MS;
    const now = performance.now();
    // A one-off stall (GC pause, OS scheduling hiccup, debugger break) must
    // not be "made up for" with a burst of zero-delay frames -- resync to
    // now instead of trying to catch up.
    if (nextFrameAt < now - MAX_CATCHUP_MS) nextFrameAt = now + FRAME_INTERVAL_MS;
    setTimeout(loop, Math.max(0, nextFrameAt - now));
  };

  const loop = () => {
    // Without this guard a single bad frame (a throw from detectForVideo,
    // cv.imread, cvtColor, calcOpticalFlowPyrLK, toDataURL, etc.) would kill
    // the loop for the rest of the session -- the reschedule below must run
    // in `finally` no matter what throws above it. Mirrors engine.py's _run
    // guard: "the tray icon and window survive, the cursor just silently
    // stops forever" otherwise.
    try {
      // Mirrors the frame once, up front -- landmarks (Task 14), optical
      // flow (Task 15), and the preview overlay (Task 16) all read from this
      // same mirrored canvas, matching tracker.py's cv2.flip(frame, 1) being
      // applied before every downstream consumer touches the frame.
      workCtx.save();
      workCtx.translate(WORK_WIDTH, 0);
      workCtx.scale(-1, 1);
      workCtx.drawImage(video, 0, 0, WORK_WIDTH, WORK_HEIGHT);
      workCtx.restore();

      const result = faceLandmarker.detectForVideo(workCanvas, performance.now());
      const rawLandmarks = result.faceLandmarks[0];
      const metrics = rawLandmarks
        ? computeFaceMetrics(rawLandmarks.map((p): Point => [p.x, p.y]))
        : null;

      let movement: [number, number] = [0, 0];
      if (metrics) {
        // Declared outside the try so the finally below can safely delete
        // whichever of the two actually got allocated, even if the second
        // `new cv.Mat()` itself throws before assignment.
        let src: CvMat | null = null;
        let gray: CvMat | null = null;
        try {
          src = cv.imread(workCanvas);
          gray = new cv.Mat();
          cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
          const anchor: Point = [metrics.noseX * WORK_WIDTH, metrics.noseY * WORK_HEIGHT];
          const headSize = headSizePx(metrics.landmarks, WORK_WIDTH, WORK_HEIGHT);
          const candidates = SEED_LANDMARKS.filter((i) => i < metrics.landmarks.length).map(
            (i): Point => [metrics.landmarks[i][0] * WORK_WIDTH, metrics.landmarks[i][1] * WORK_HEIGHT]
          );
          pointTracker.update(gray, anchor, headSize, candidates);
          movement = pointTracker.getMovement();
        } finally {
          src?.delete();
          gray?.delete();
        }
      } else {
        pointTracker.reset();
      }

      // Landmarks never cross IPC to Main -- Main doesn't read them, and
      // sending the full 468-478-point array every frame is a needless
      // privacy/perf cost. The preview overlay above already consumed
      // `metrics.landmarks` renderer-side before this strip.
      const wireMetrics = metrics ? { ...metrics, landmarks: [] } : null;

      window.tracking.sendFrame({
        metrics: wireMetrics,
        movement,
        previewJpegBase64: previewEnabled ? renderPreviewJpeg(metrics) : null,
      });
    } catch (exc) {
      console.error(`facemesh-mouse: tracking frame failed (${exc})`);
      pointTracker.reset();
    } finally {
      scheduleNextFrame();
    }
  };
  setTimeout(loop, FRAME_INTERVAL_MS);
}

void main();
