import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

interface Props {
  title: string;
  chapterIndex: number;
  totalChapters: number;
}

/**
 * Brief chapter title card (4s default). Shown between chapters; lets the
 * audience breathe and resets the rhythm.
 */
export const ChapterCard: React.FC<Props> = ({ title, chapterIndex, totalChapters }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const opacity = interpolate(
    frame,
    [0, Math.round(0.5 * fps), durationInFrames - Math.round(0.5 * fps), durationInFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" }
  );
  const ty = interpolate(frame, [0, Math.round(0.8 * fps)], [10, 0], { extrapolateRight: "clamp" });
  const lineWidth = interpolate(frame, [Math.round(0.4 * fps), Math.round(1.4 * fps)], [0, 320], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at center, #2a1810 0%, #0e0805 100%)",
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <div style={{ transform: `translateY(${ty}px)`, textAlign: "center", maxWidth: 1500, padding: "0 80px" }}>
        <div
          style={{
            fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
            fontSize: 40,
            color: "#c9a97a",
            letterSpacing: 8,
            textTransform: "uppercase",
            opacity: 0.85,
            marginBottom: 24,
          }}
        >
          chapter {chapterIndex} / {totalChapters}
        </div>
        <div
          style={{
            width: lineWidth,
            height: 3,
            background: "#c9a97a",
            margin: "0 auto 30px",
            opacity: 0.7,
            borderRadius: 2,
          }}
        />
        <div
          style={{
            fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
            fontSize: 88,
            color: "#fff8df",
            fontWeight: 600,
            lineHeight: 1.25,
            textShadow: "0 4px 24px rgba(0,0,0,0.6)",
          }}
        >
          {title}
        </div>
      </div>
    </AbsoluteFill>
  );
};
