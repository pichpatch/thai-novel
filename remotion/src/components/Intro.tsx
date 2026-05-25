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
 * Logo path resolver. The library is mirrored into remotion/public/library/
 * before render (see src/thai_novel/remotion/__init__.py).
 *
 * Tries the explicit ref first; falls back to ./intro/logo.png (the user's
 * pre-rewrite asset, still tracked in the project root).
 */
function resolveLogoPath(logoRef: string | null): string | null {
  if (!logoRef) return null;
  // library://overlays/channel_logo -> library/visuals/overlays/channel_logo.{png,webp}
  // We try .png by convention; the Python side has already materialized
  // it under remotion/public/library/.
  const body = logoRef.replace("library://", "");
  if (body.startsWith("overlays/")) {
    return `library/visuals/${body}.png`;
  }
  return null;
}

/**
 * Two-card intro:
 *  1. Channel welcome:  "ยินดีต้อนรับสู่ช่อง THAI Novel"  + logo
 *  2. Episode title:    "ตอนที่ N — <title>"
 *
 * Both spoken (edge-tts). Background = optional anchor or warm gradient.
 */
export const Intro: React.FC<Props> = ({ intro }) => {
  const { fps } = useVideoConfig();

  const welcomeFrames = Math.round(intro.welcome_duration_sec * fps);
  const titleFrames = Math.round(intro.title_duration_sec * fps);
  const logoPath = resolveLogoPath(intro.logo_ref);

  return (
    <AbsoluteFill style={{ backgroundColor: "#1a0f08" }}>
      <Sequence from={0} durationInFrames={welcomeFrames}>
        <WelcomeCard
          channel={intro.channel_name}
          text={intro.welcome_text}
          background={intro.background_image_path}
          logoPath={logoPath}
        />
        <Audio src={staticFile(intro.welcome_audio_path)} volume={0.95} />
      </Sequence>

      <Sequence from={welcomeFrames} durationInFrames={titleFrames}>
        <TitleCard
          text={intro.title_text}
          background={intro.background_image_path}
          logoPath={logoPath}
          channel={intro.channel_name}
        />
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
  logoPath: string | null;
}> = ({ channel, text, background, logoPath }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const opacity = interpolate(
    frame,
    [0, Math.round(0.6 * fps), durationInFrames - Math.round(0.6 * fps), durationInFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" }
  );
  const ty = interpolate(frame, [0, Math.round(1.2 * fps)], [12, 0], { extrapolateRight: "clamp" });
  // Logo fades in just before the channel name lands
  const logoOpacity = interpolate(frame, [0, Math.round(0.4 * fps), Math.round(1.0 * fps)], [0, 0, 1], { extrapolateRight: "clamp" });
  const logoScale = interpolate(frame, [Math.round(0.4 * fps), Math.round(1.2 * fps)], [0.92, 1.0], { extrapolateRight: "clamp" });

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
          {logoPath && (
            <img
              src={staticFile(logoPath)}
              alt={`${channel} logo`}
              style={{
                width: 280,
                height: 280,
                objectFit: "contain",
                marginBottom: 40,
                opacity: logoOpacity,
                transform: `scale(${logoScale})`,
                filter: "drop-shadow(0 8px 24px rgba(0,0,0,0.5))",
              }}
            />
          )}
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 44,
              color: "#f3d9a8",
              letterSpacing: 6,
              textTransform: "uppercase",
              opacity: 0.85,
              marginBottom: 22,
            }}
          >
            welcome to
          </div>
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 136,
              color: "#fff8df",
              fontWeight: 700,
              letterSpacing: 4,
              textShadow: "0 4px 32px rgba(0,0,0,0.6)",
              lineHeight: 1.1,
            }}
          >
            {channel}
          </div>
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 38,
              color: "#e7c896",
              marginTop: 32,
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

const TitleCard: React.FC<{
  text: string;
  background: string | null;
  logoPath: string | null;
  channel: string;
}> = ({ text, background, logoPath, channel }) => {
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
          {logoPath && (
            <img
              src={staticFile(logoPath)}
              alt={`${channel} logo`}
              style={{
                width: 140,
                height: 140,
                objectFit: "contain",
                marginBottom: 32,
                filter: "drop-shadow(0 6px 18px rgba(0,0,0,0.5))",
                opacity: 0.9,
              }}
            />
          )}
          <div
            style={{
              fontFamily: '"Sarabun", "Noto Sans Thai", sans-serif',
              fontSize: 86,
              color: "#fff8df",
              fontWeight: 700,
              lineHeight: 1.25,
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
