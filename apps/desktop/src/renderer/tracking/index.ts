import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
// Static top-of-file import, per the task brief's own note -- NOT the inline
// `await import(...)` form. The default export is a Promise that resolves
// once the WASM runtime finishes initializing (see pointTracker.ts's header
// comment and task-15-report.md for why this can't be touched synchronously
// at module scope), so it's awaited once below, inside main().
import cvReadyPromise from "@techstark/opencv-js";
import type { Mat as CvMat } from "@techstark/opencv-js";
import { computeFaceMetrics, EYE_OUTER_A, EYE_OUTER_B, GESTURE_LANDMARK_GROUPS, type Point } from "./faceMetrics";
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
    const indices = GESTURE_LANDMARK_GROUPS[highlightedGesture];
    if (indices?.length) {
      const xs = indices.map((i) => metrics.landmarks[i][0] * PREVIEW_WIDTH);
      const ys = indices.map((i) => metrics.landmarks[i][1] * PREVIEW_HEIGHT);
      const xMin = Math.min(...xs), xMax = Math.max(...xs);
      const yMin = Math.min(...ys), yMax = Math.max(...ys);
      const padX = Math.max((xMax - xMin) * 0.4, 10);
      const padY = Math.max((yMax - yMin) * 0.4, 10);
      const cx = (xMin + xMax) / 2, cy = (yMin + yMax) / 2;
      const rx = (xMax - xMin) / 2 + padX, ry = (yMax - yMin) / 2 + padY;
      previewCtx.save();
      previewCtx.globalAlpha = 0.35;
      previewCtx.fillStyle = "rgb(0, 255, 0)";
      previewCtx.beginPath();
      previewCtx.ellipse(cx, cy, rx, ry, 0, 0, 2 * Math.PI);
      previewCtx.fill();
      previewCtx.restore();
      previewCtx.strokeStyle = "rgb(0, 255, 0)";
      previewCtx.lineWidth = 2;
      previewCtx.beginPath();
      previewCtx.ellipse(cx, cy, rx, ry, 0, 0, 2 * Math.PI);
      previewCtx.stroke();
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
      setTimeout(loop, FRAME_INTERVAL_MS);
    }
  };
  setTimeout(loop, FRAME_INTERVAL_MS);
}

void main();
