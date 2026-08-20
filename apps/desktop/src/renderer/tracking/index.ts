import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
// Static top-of-file import, per the task brief's own note -- NOT the inline
// `await import(...)` form. The default export is a Promise that resolves
// once the WASM runtime finishes initializing (see pointTracker.ts's header
// comment and task-15-report.md for why this can't be touched synchronously
// at module scope), so it's awaited once below, inside main().
import cvReadyPromise from "@techstark/opencv-js";
import { computeFaceMetrics, EYE_OUTER_A, EYE_OUTER_B, type Point } from "./faceMetrics";
import { PointTracker } from "./pointTracker";

export {}; // module scope

declare global {
  interface Window {
    tracking: {
      sendFrame: (frame: unknown) => void;
      cameraError: () => void;
      onSetPreview: (callback: (enabled: boolean) => void) => () => void;
    };
  }
}

const WORK_WIDTH = 640;
const WORK_HEIGHT = 480;

// Mirrors engine.py's _SEED_LANDMARKS/_head_size_px exactly.
const SEED_LANDMARKS = [98, 327, 168, 6, 197, 195, 5, 4, 234, 454, 127, 356, 122, 351];

function headSizePx(landmarks: Point[], width: number, height: number): number {
  const left = landmarks[EYE_OUTER_A];
  const right = landmarks[EYE_OUTER_B];
  return Math.hypot((left[0] - right[0]) * width, (left[1] - right[1]) * height);
}

let previewEnabled = false;
window.tracking.onSetPreview((enabled) => { previewEnabled = enabled; });

async function main(): Promise<void> {
  const video = document.getElementById("video") as HTMLVideoElement;
  const workCanvas = document.getElementById("work") as HTMLCanvasElement;
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

  const loop = () => {
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
      const src = cv.imread(workCanvas);
      const gray = new cv.Mat();
      cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
      src.delete();
      const anchor: Point = [metrics.noseX * WORK_WIDTH, metrics.noseY * WORK_HEIGHT];
      const headSize = headSizePx(metrics.landmarks, WORK_WIDTH, WORK_HEIGHT);
      const candidates = SEED_LANDMARKS.filter((i) => i < metrics.landmarks.length).map(
        (i): Point => [metrics.landmarks[i][0] * WORK_WIDTH, metrics.landmarks[i][1] * WORK_HEIGHT]
      );
      pointTracker.update(gray, anchor, headSize, candidates);
      movement = pointTracker.getMovement();
      gray.delete();
    } else {
      pointTracker.reset();
    }

    // Task 16 fills in the preview.
    window.tracking.sendFrame({ metrics, movement, previewJpegBase64: null });

    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

void main();
