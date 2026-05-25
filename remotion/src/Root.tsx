import React from "react";
import { Composition } from "remotion";

import { Episode } from "./Episode";
import type { Timeline } from "./lib/timeline";

// Minimal stub timeline shown in the Remotion studio when no real timeline
// has been compiled yet. Replace with `--props=cache/<id>/timeline.json` to
// preview a real episode.
const STUB: Timeline = {
  version: 1,
  episode_id: "stub",
  title: "stub",
  series: null,
  language: "th",
  width: 1920,
  height: 1080,
  fps: 30,
  total_duration_sec: 10,
  subtitles_config: {
    enabled: true, font: "Sarabun", size_px: 48, max_chars_per_line: 38,
    style: "soft_drop_shadow", position: "bottom_center",
    karaoke_reveal: true, emphasize_character_names: true,
  },
  visual_style: { base_prompt: "", negative_prompt: "", color_grade: "warm_cozy" },
  characters: {},
  audio_config: {
    music_bed: { default: null, by_mood: {}, volume_db: -22, crossfade_ms: 1500, duck_during_dialogue_db: -6 },
    ambience: { default: null, by_mood: {}, volume_db: -28 },
  },
  intro: null,
  chapters: [],
  end_card: null,
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Episode"
        component={Episode}
        defaultProps={{ timeline: STUB }}
        durationInFrames={Math.round(STUB.total_duration_sec * STUB.fps)}
        fps={STUB.fps}
        width={STUB.width}
        height={STUB.height}
        // When invoked via the renderer with a real --props, the timeline
        // arrives via defaultProps merge and these dimensions are overridden
        // by calculateMetadata below.
        calculateMetadata={({ props }) => {
          const t = props.timeline as Timeline;
          return {
            durationInFrames: Math.max(1, Math.round(t.total_duration_sec * t.fps)),
            fps: t.fps,
            width: t.width,
            height: t.height,
          };
        }}
      />
    </>
  );
};
