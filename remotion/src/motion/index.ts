// Motion presets.
// Each preset returns CSS transform values given (progress, width, height).
// progress: 0.0 -> 1.0 across the duration the image is on screen.

import type { MotionPreset } from "../lib/timeline";

export interface MotionState {
  transform: string;
  filter?: string;
}

// Easing helpers
const easeInOutCubic = (t: number): number =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

// Simple deterministic perlin-ish noise for handheld
const noise = (seed: number) => {
  const x = Math.sin(seed) * 43758.5453123;
  return x - Math.floor(x);
};

export function computeMotion(
  preset: MotionPreset,
  progress: number,
  // unused for now, but kept for future shaders / parallax
  _width = 1920,
  _height = 1080
): MotionState {
  const p = Math.max(0, Math.min(1, progress));

  switch (preset) {
    case "slow_zoom_in": {
      const scale = 1.00 + 0.12 * easeInOutCubic(p);
      return { transform: `scale(${scale.toFixed(4)})` };
    }
    case "slow_zoom_out": {
      const scale = 1.12 - 0.12 * easeInOutCubic(p);
      return { transform: `scale(${scale.toFixed(4)})` };
    }
    case "pan_left": {
      const tx = -8 * p;  // % of width
      const scale = 1.08; // slight zoom so the pan doesn't reveal black bars
      return { transform: `translateX(${tx.toFixed(2)}%) scale(${scale})` };
    }
    case "pan_right": {
      const tx = 8 * p;
      const scale = 1.08;
      return { transform: `translateX(${tx.toFixed(2)}%) scale(${scale})` };
    }
    case "parallax_depth": {
      // Foreground translates 1.2x background; here we approximate with a
      // gentle zoom + horizontal drift so single-layer assets still feel
      // dimensional.
      const scale = 1.04 + 0.04 * easeInOutCubic(p);
      const tx = (p - 0.5) * 4; // -2% .. +2%
      return { transform: `translateX(${tx.toFixed(2)}%) scale(${scale.toFixed(4)})` };
    }
    case "subtle_handheld": {
      // tiny noise jitter on translation
      const tx = (noise(p * 31.7) - 0.5) * 0.6;  // ~±0.3%
      const ty = (noise(p * 53.3 + 100) - 0.5) * 0.6;
      const scale = 1.05;
      return { transform: `translate(${tx.toFixed(3)}%, ${ty.toFixed(3)}%) scale(${scale})` };
    }
    case "ken_burns_combo": {
      const scale = 1.00 + 0.10 * easeInOutCubic(p);
      const tx = -4 * easeInOutCubic(p);
      return { transform: `translateX(${tx.toFixed(2)}%) scale(${scale.toFixed(4)})` };
    }
    case "static":
    default:
      return { transform: "scale(1.0)" };
  }
}

export function colorGradeFilter(grade: string): string {
  switch (grade) {
    case "warm_cozy":
      return "saturate(1.05) brightness(1.02) contrast(0.96) sepia(0.06)";
    case "cool_night":
      return "saturate(0.9) brightness(0.85) contrast(1.05) hue-rotate(-10deg)";
    case "golden_hour":
      return "saturate(1.15) brightness(1.05) sepia(0.18)";
    case "melancholy_blue":
      return "saturate(0.7) brightness(0.9) hue-rotate(15deg)";
    case "playful_pop":
      return "saturate(1.2) brightness(1.05) contrast(1.05)";
    case "neutral":
    default:
      return "none";
  }
}
