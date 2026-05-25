import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig } from "remotion";

import type { Timeline } from "./lib/timeline";
import { VisualAnchor } from "./components/VisualAnchor";
import { Subtitle } from "./components/Subtitle";
import { Intro } from "./components/Intro";
import { ChapterCard } from "./components/ChapterCard";
import { EndCard } from "./components/EndCard";

interface Props {
  timeline: Timeline;
}

/**
 * Top-level Episode composition.
 *
 * Order on screen:
 *   1. Intro (welcome + episode title cards)        — if timeline.intro.show
 *   2. Per chapter: title card + blocks (anchor+audio+subs)
 *   3. End card
 *
 * Audio: narration plays per-block (each block has its own Audio source).
 * Music + ambience are handled by the Python mux step (ffmpeg sidechain),
 * not by Remotion — keeps the Remotion render lean and lets us iterate the
 * audio mix without re-rendering video.
 */
export const Episode: React.FC<Props> = ({ timeline }) => {
  const { fps } = useVideoConfig();
  const toFrames = (sec: number) => Math.round(sec * fps);

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {/* ── 1. Intro ────────────────────────────────────────────────────── */}
      {timeline.intro && timeline.intro.show && (
        <Sequence
          from={0}
          durationInFrames={toFrames(
            timeline.intro.welcome_duration_sec + timeline.intro.title_duration_sec
          )}
        >
          <Intro intro={timeline.intro} />
        </Sequence>
      )}

      {/* ── 2. Chapters ─────────────────────────────────────────────────── */}
      {timeline.chapters.map((ch, chapterIdx) => {
        const chFrom = toFrames(ch.start_sec);
        const chDur = toFrames(ch.duration_sec);
        return (
          <Sequence key={ch.id} from={chFrom} durationInFrames={chDur}>
            {ch.show_title_card && (
              <Sequence from={0} durationInFrames={toFrames(ch.title_card_duration_sec)}>
                <ChapterCard
                  title={ch.title}
                  chapterIndex={chapterIdx + 1}
                  totalChapters={timeline.chapters.length}
                />
              </Sequence>
            )}

            {ch.blocks.map((b) => {
              const localStart = b.start_sec - ch.start_sec;
              return (
                <Sequence
                  key={b.id}
                  from={toFrames(localStart)}
                  durationInFrames={toFrames(b.duration_sec)}
                >
                  <VisualAnchor
                    imagePath={b.image_path}
                    motion={b.motion}
                    colorGrade={b.color_grade}
                  />
                  <Subtitle
                    cues={b.subtitles}
                    config={timeline.subtitles_config}
                    emphasis={b.subtitle_emphasis}
                  />
                  <Audio src={staticFile(b.audio_path)} volume={1.0} />
                </Sequence>
              );
            })}
          </Sequence>
        );
      })}

      {/* ── 3. End card ─────────────────────────────────────────────────── */}
      {timeline.end_card && timeline.end_card.show && (
        <Sequence
          from={toFrames(timeline.end_card.start_sec)}
          durationInFrames={toFrames(timeline.end_card.duration_sec)}
        >
          <EndCard
            nextEpisodeTitle={timeline.end_card.next_episode_title}
            message={timeline.end_card.message}
            channelName={timeline.intro?.channel_name ?? "THAI Novel"}
          />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
