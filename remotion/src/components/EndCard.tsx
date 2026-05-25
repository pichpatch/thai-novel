import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

interface Props {
  nextEpisodeTitle: string | null;
  message: string | null;
  channelName: string;
}

export const EndCard: React.FC<Props> = ({ nextEpisodeTitle, message, channelName }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const opacity = interpolate(
    frame,
    [0, Math.round(0.7 * fps), durationInFrames - Math.round(0.7 * fps), durationInFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" }
  );
  const ty = interpolate(frame, [0, Math.round(1.0 * fps)], [12, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at center, #2a1810 0%, #050302 100%)",
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <div style={{ transform: `translateY(${ty}px)`, textAlign: "center", maxWidth: 1500, padding: "0 80px" }}>
        {message && (
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 52,
              color: "#fff8df",
              marginBottom: 56,
              fontWeight: 500,
              lineHeight: 1.4,
            }}
          >
            {message}
          </div>
        )}
        {nextEpisodeTitle && (
          <>
            <div
              style={{
                fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
                fontSize: 36,
                color: "#c9a97a",
                letterSpacing: 6,
                textTransform: "uppercase",
                opacity: 0.85,
                marginBottom: 24,
              }}
            >
              next episode
            </div>
            <div
              style={{
                fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
                fontSize: 72,
                color: "#fff8df",
                fontWeight: 600,
                lineHeight: 1.3,
              }}
            >
              {nextEpisodeTitle}
            </div>
          </>
        )}
        <div
          style={{
            marginTop: 80,
            fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
            fontSize: 32,
            color: "#8c7a5e",
            letterSpacing: 4,
          }}
        >
          {channelName}
        </div>
      </div>
    </AbsoluteFill>
  );
};
