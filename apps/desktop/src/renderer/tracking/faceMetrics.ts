import type { FaceMetrics as SharedFaceMetrics } from "@facemesh-mouse/shared";

export const NOSE_TIP = 1;
export const FOREHEAD_TOP = 10;
export const CHIN_BOTTOM = 152;
export const FACE_AXIS_TOP = 168;
export const EYE_OUTER_A = 33;
export const EYE_OUTER_B = 263;
export const EYE_A = [33, 160, 158, 133, 153, 144];
export const EYE_B = [362, 385, 387, 263, 373, 380];
export const MOUTH_TOP_INNER = 13;
export const MOUTH_BOTTOM_INNER = 14;
export const MOUTH_CORNER_LEFT = 61;
export const MOUTH_CORNER_RIGHT = 291;
export const EYEBROW_A = 105;
export const EYEBROW_B = 334;
export const EYELID_TOP_A = 159;
export const EYELID_TOP_B = 386;

// The real brow hairline, as two 5-point arcs (outer row + inner row) --
// read from FaceLandmarker.FACE_LANDMARKS_RIGHT_EYEBROW/_LEFT_EYEBROW's own
// connection topology, not guessed. EYEBROW_A/EYEBROW_B above are single
// points used only for the raise-ratio calculation below; these arcs are
// for drawing the actual eyebrow shape in the camera preview.
export const EYEBROW_ARC_A = [
  [46, 53, 52, 65, 55],
  [70, 63, 105, 66, 107],
];
export const EYEBROW_ARC_B = [
  [276, 283, 282, 295, 285],
  [300, 293, 334, 296, 336],
];

export type Point = [number, number];
export type FaceMetrics = SharedFaceMetrics;

// The mouth gestures (open/left/right) all read off the same mouth-center-vs-
// face-axis measurement, not distinct mouth regions -- matching tracker.py's
// own comment -- so mouth_left/mouth_right share mouth_open's landmark set.
const MOUTH_LANDMARKS = [MOUTH_TOP_INNER, MOUTH_BOTTOM_INNER, MOUTH_CORNER_LEFT, MOUTH_CORNER_RIGHT];

// Which landmark indices to highlight in the camera preview when the config
// window's Gestos tab hovers a given gesture row. Keys must match
// config.service.ts's GESTURE_NAMES exactly. Each gesture maps to a list of
// sub-groups -- one per convex hull to draw -- so a "_both" gesture renders
// two separate hulls (left eye, right eye) instead of one hull spanning the
// gap between them.
export const GESTURE_LANDMARK_GROUPS: Record<string, number[][]> = {
  blink_a: [EYE_A],
  blink_b: [EYE_B],
  blink_both: [EYE_A, EYE_B],
  // Own arc points only (not EYELID_TOP/EYE_A) -- matches the eye groups
  // above, which highlight only the eye's own ring rather than pulling in
  // the eyebrow too. Same convex-hull-plus-dots render path as blink/mouth.
  eyebrow_a: [EYEBROW_ARC_A.flat()],
  eyebrow_b: [EYEBROW_ARC_B.flat()],
  eyebrow_both: [EYEBROW_ARC_A.flat(), EYEBROW_ARC_B.flat()],
  mouth_open: [MOUTH_LANDMARKS],
  mouth_left: [MOUTH_LANDMARKS],
  mouth_right: [MOUTH_LANDMARKS],
};

function dist(p1: Point, p2: Point): number {
  return Math.hypot(p1[0] - p2[0], p1[1] - p2[1]);
}

function eyeAspectRatio(pts: Point[]): number {
  const [p1, p2, p3, p4, p5, p6] = pts;
  const vertical = dist(p2, p6) + dist(p3, p5);
  const horizontal = 2.0 * dist(p1, p4);
  return horizontal === 0 ? 0.0 : vertical / horizontal;
}

export function eyeMidpoint(pts: Point[]): Point {
  const left = pts[EYE_OUTER_A];
  const right = pts[EYE_OUTER_B];
  return [(left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0];
}

export function signedLateralOffset(point: Point, axisStart: Point, axisEnd: Point): number {
  const [ax, ay] = axisStart;
  const [bx, by] = axisEnd;
  const [px, py] = point;
  const dx = bx - ax, dy = by - ay;
  const length = Math.hypot(dx, dy) || 1e-6;
  return ((px - ax) * dy - (py - ay) * dx) / length;
}

export function computeFaceMetrics(pts: Point[]): FaceMetrics | null {
  if (!pts.length) return null;

  const faceHeight = dist(pts[FOREHEAD_TOP], pts[CHIN_BOTTOM]) || 1e-6;
  const faceWidth = dist(pts[EYE_OUTER_A], pts[EYE_OUTER_B]) || 1e-6;

  const earA = eyeAspectRatio(EYE_A.map((i) => pts[i]));
  const earB = eyeAspectRatio(EYE_B.map((i) => pts[i]));

  const mouthVertical = dist(pts[MOUTH_TOP_INNER], pts[MOUTH_BOTTOM_INNER]);
  const mouthHorizontal = dist(pts[MOUTH_CORNER_LEFT], pts[MOUTH_CORNER_RIGHT]) || 1e-6;
  const mouthOpenRatio = mouthVertical / mouthHorizontal;

  const eyebrowRaiseA = dist(pts[EYEBROW_A], pts[EYELID_TOP_A]) / faceHeight;
  const eyebrowRaiseB = dist(pts[EYEBROW_B], pts[EYELID_TOP_B]) / faceHeight;

  const mouthCenter: Point = [
    (pts[MOUTH_CORNER_LEFT][0] + pts[MOUTH_CORNER_RIGHT][0]) / 2.0,
    (pts[MOUTH_CORNER_LEFT][1] + pts[MOUTH_CORNER_RIGHT][1]) / 2.0,
  ];
  const mouthShiftRatio = signedLateralOffset(mouthCenter, pts[FACE_AXIS_TOP], pts[CHIN_BOTTOM]) / faceWidth;

  const [noseX, noseY] = eyeMidpoint(pts);

  return {
    noseX, noseY, earA, earB, mouthOpenRatio,
    eyebrowRaiseA, eyebrowRaiseB, mouthShiftRatio,
    landmarks: pts,
  };
}
