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

    // Task 14 replaces this stub with a real FaceLandmarker.detectForVideo
    // call against workCanvas, and Task 15/16 fill in movement/preview.
    window.tracking.sendFrame({ metrics: null, movement: [0, 0], previewJpegBase64: null });

    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

void main();
