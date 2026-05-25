import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { computeMotion, colorGradeFilter } from "../motion";
import type { MotionPreset, ColorGrade } from "../lib/timeline";

interface Props {
  imagePath: string;        // relative to project root
  motion: MotionPreset;
  colorGrade: ColorGrade;
}

/**
 * A single visual anchor: a 1920x1080 image that lives on screen for the
 * duration of its parent Sequence, with camera motion + color grading.
 */
export const VisualAnchor: React.FC<Props> = ({ imagePath, motion, colorGrade }) => {
  const frame = useCurrentFrame();
  const { durationInFrames, width, height } = useVideoConfig();
  const progress = durationInFrames > 0 ? frame / durationInFrames : 0;

  const m = computeMotion(motion, progress, width, height);
  const filter = colorGradeFilter(colorGrade);

  return (
    <AbsoluteFill style={{ backgroundColor: "black", overflow: "hidden" }}>
      <Img
        src={staticFile(imagePath)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: m.transform,
          transformOrigin: "center center",
          filter,
          willChange: "transform, filter",
        }}
      />
    </AbsoluteFill>
  );
};
