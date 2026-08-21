export interface FaceMetrics {
  noseX: number;
  noseY: number;
  earA: number;
  earB: number;
  mouthOpenRatio: number;
  eyebrowRaiseA: number;
  eyebrowRaiseB: number;
  mouthShiftRatio: number;
  landmarks: [number, number][];
}

export interface TrackingFrame {
  metrics: FaceMetrics | null;
  movement: [number, number];
  previewJpegBase64: string | null;
}
