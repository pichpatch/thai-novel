import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";

import type { SubtitleCue, SubtitlesConfig } from "../lib/timeline";

interface Props {
  cues: SubtitleCue[];
  config: SubtitlesConfig;
  // Strings to emphasize (character names, place names).
  emphasis: string[];
  // Absolute time offset that block_start = 0 of the cues maps to in the parent composition.
  // We don't actually need it here because cues' start_sec are block-relative and we get
  // current frame relative to the parent <Sequence>; this is for documentation.
  _ignored?: number;
}

/**
 * Karaoke-style subtitle:
 *  - Current cue's words: 100% opacity
 *  - Upcoming words in same cue: 60% opacity
 *  - Past words: 100% opacity (latched)
 *  - Character names: bold
 */
export const Subtitle: React.FC<Props> = ({ cues, config, emphasis }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  // Find the active cue (block-relative t)
  const active = cues.find((c) => t >= c.start_sec && t < c.end_sec);
  if (!active) return null;

  const positionStyle: React.CSSProperties = (() => {
    if (config.position === "top_center") {
      return { top: 80, left: 0, right: 0, justifyContent: "center" };
    }
    if (config.position === "bottom_left") {
      return { bottom: 80, left: 80, right: 0, justifyContent: "flex-start" };
    }
    return { bottom: 80, left: 0, right: 0, justifyContent: "center" };
  })();

  // Soft drop shadow with a subtle backdrop for legibility over any image
  const baseTextStyle: React.CSSProperties = {
    color: "#fff",
    fontFamily: `"${config.font}", "Noto Sans Thai", sans-serif`,
    fontSize: config.size_px,
    lineHeight: 1.35,
    textShadow:
      "0 2px 8px rgba(0,0,0,0.65), 0 0 2px rgba(0,0,0,0.9), 0 0 18px rgba(0,0,0,0.45)",
    letterSpacing: 0.5,
    textAlign: config.position.endsWith("left") ? "left" : "center",
    maxWidth: 1600,
    margin: "0 auto",
    padding: "0 60px",
  };

  // Render either karaoke (word-by-word reveal) or simple plain text.
  let content: React.ReactNode;
  if (config.karaoke_reveal && active.words && active.words.length > 0) {
    content = (
      <>
        {active.words.map((w, i) => {
          const isPast = t >= w.end_sec;
          const isCurrent = t >= w.start_sec && t < w.end_sec;
          const opacity = isPast || isCurrent ? 1 : 0.55;
          const isName =
            config.emphasize_character_names &&
            emphasis.some((name) => w.word.includes(name));
          return (
            <span
              key={i}
              style={{
                opacity,
                fontWeight: isName ? 700 : 500,
                transition: "opacity 120ms linear",
                marginRight: 2,
              }}
            >
              {w.word}
            </span>
          );
        })}
      </>
    );
  } else {
    // Simple mode: emphasize substrings by splitting on each emphasis term.
    let text = active.text;
    let nodes: React.ReactNode[] = [text];
    if (config.emphasize_character_names) {
      for (const name of emphasis) {
        nodes = nodes.flatMap((n) => {
          if (typeof n !== "string") return [n];
          const parts = n.split(name);
          const merged: React.ReactNode[] = [];
          parts.forEach((part, i) => {
            if (i > 0) merged.push(<strong key={`${name}-${i}`}>{name}</strong>);
            merged.push(part);
          });
          return merged;
        });
      }
    }
    content = <>{nodes}</>;
  }

  return (
    <AbsoluteFill style={{ ...positionStyle, alignItems: "flex-end", pointerEvents: "none" }}>
      <div style={baseTextStyle}>{content}</div>
    </AbsoluteFill>
  );
};
