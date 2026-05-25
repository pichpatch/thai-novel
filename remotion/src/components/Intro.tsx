import React from "react";
import {
  AbsoluteFill, Audio, Sequence, staticFile,
  interpolate, useCurrentFrame, useVideoConfig,
} from "remotion";

import type { IntroSection } from "../lib/timeline";

interface Props {
  intro: IntroSection;
}

/**
 * Two-card intro:
 *  1. "ยินดีต้อนรับสู่ช่อง THAI Novel"  (over background image or warm gradient)
 *  2. "ตอนที่ N — <title>"
 *
 * Both have narration. Background music plays under both.
 */
export const Intro: React.FC<Props> = ({ intro }) => {
  const { fps } = useVideoConfig();

  const welcomeFrames = Math.round(intro.welcome_duration_sec * fps);
  const titleFrames = Math.round(intro.title_duration_sec * fps);

  return (
    <AbsoluteFill style={{ backgroundColor: "#1a0f08" }}>
      {/* Welcome card */}
      <Sequence from={0} durationInFrames={welcomeFrames}>
        <WelcomeCard
          channel={intro.channel_name}
          text={intro.welcome_text}
          background={intro.background_image_path}
        />
        <Audio src={staticFile(intro.welcome_audio_path)} volume={0.95} />
      </Sequence>

      {/* Episode title card */}
      <Sequence from={welcomeFrames} durationInFrames={titleFrames}>
        <TitleCard text={intro.title_text} background={intro.background_image_path} />
        <Audio src={staticFile(intro.title_audio_path)} volume={0.95} />
      </Sequence>
    </AbsoluteFill>
  );
};

// ────────────────────────────────────────────────────────────────────────────

const WarmGradient: React.FC = () => (
  <AbsoluteFill
    style={{
      background:
        "radial-gradient(ellipse at 50% 35%, #4a2d18 0%, #1a0f08 65%, #0a0604 100%)",
    }}
  />
);

const WelcomeCard: React.FC<{
  channel: string;
  text: string;
  background: string | null;
}> = ({ channel, text, background }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Gentle fade in/out
  const opacity = interpolate(
    frame,
    [0, Math.round(0.6 * fps), durationInFrames - Math.round(0.6 * fps), durationInFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" }
  );
  // Subtle rise for the channel logotype
  const ty = interpolate(frame, [0, Math.round(1.2 * fps)], [12, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      {background ? (
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <img
            src={staticFile(background)}
            style={{ width: "100%", height: "100%", objectFit: "cover", filter: "brightness(0.45) saturate(0.9)" }}
            alt=""
          />
        </AbsoluteFill>
      ) : (
        <WarmGradient />
      )}
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity }}>
        <div style={{ transform: `translateY(${ty}px)`, textAlign: "center" }}>
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 56,
              color: "#f3d9a8",
              letterSpacing: 6,
              textTransform: "uppercase",
              opacity: 0.85,
              marginBottom: 28,
            }}
          >
            channel
          </div>
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 168,
              color: "#fff8df",
              fontWeight: 700,
              letterSpacing: 4,
              textShadow: "0 4px 32px rgba(0,0,0,0.6)",
            }}
          >
            {channel}
          </div>
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 44,
              color: "#e7c896",
              marginTop: 36,
              fontWeight: 400,
              opacity: 0.92,
            }}
          >
            {text}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const TitleCard: React.FC<{ text: string; background: string | null }> = ({
  text,
  background,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const opacity = interpolate(
    frame,
    [0, Math.round(0.6 * fps), durationInFrames - Math.round(0.6 * fps), durationInFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" }
  );
  const ty = interpolate(frame, [0, Math.round(1.0 * fps)], [16, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      {background ? (
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <img
            src={staticFile(background)}
            style={{ width: "100%", height: "100%", objectFit: "cover", filter: "brightness(0.4) saturate(0.9)" }}
            alt=""
          />
        </AbsoluteFill>
      ) : (
        <WarmGradient />
      )}
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity }}>
        <div style={{ transform: `translateY(${ty}px)`, textAlign: "center", maxWidth: 1500, padding: "0 80px" }}>
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 96,
              color: "#fff8df",
              fontWeight: 700,
              lineHeight: 1.2,
              letterSpacing: 1,
              textShadow: "0 4px 32px rgba(0,0,0,0.7)",
            }}
          >
            {text}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
