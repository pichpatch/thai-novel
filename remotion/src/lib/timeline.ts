// TypeScript types that mirror src/thai_novel/timeline/__init__.py's output.
// Keep these in sync — both sides ship the same shape.

export type Mood = "cozy" | "funny" | "romantic" | "tense" | "melancholy" | "playful";

export type MotionPreset =
  | "slow_zoom_in" | "slow_zoom_out"
  | "pan_left" | "pan_right"
  | "parallax_depth" | "subtle_handheld"
  | "ken_burns_combo" | "static";

export type ColorGrade =
  | "warm_cozy" | "cool_night" | "golden_hour"
  | "melancholy_blue" | "neutral" | "playful_pop";

export interface SubtitleWord {
  word: string;
  start_sec: number;
  end_sec: number;
}

export interface SubtitleCue {
  start_sec: number;
  end_sec: number;
  text: string;
  words: SubtitleWord[];
}

export interface SFXCue {
  at_sec: number;
  ref: string;
  volume_db: number;
}

export interface BlockSection {
  id: string;
  mood: Mood;
  start_sec: number;
  duration_sec: number;
  audio_path: string;          // relative to project root
  image_path: string;          // relative to project root, already 1920x1080
  motion: MotionPreset;
  color_grade: ColorGrade;
  music_ref: string | null;
  ambience_ref: string | null;
  subtitles: SubtitleCue[];
  subtitle_emphasis: string[];
  sfx_cues: SFXCue[];
}

export interface ChapterSection {
  id: string;
  title: string;
  show_title_card: boolean;
  title_card_duration_sec: number;
  start_sec: number;
  duration_sec: number;
  blocks: BlockSection[];
}

export interface IntroSection {
  show: boolean;
  channel_name: string;
  welcome_text: string;
  title_text: string;
  welcome_start_sec: number;
  welcome_duration_sec: number;
  title_start_sec: number;
  title_duration_sec: number;
  welcome_audio_path: string;
  title_audio_path: string;
  background_music_ref: string | null;
  logo_ref: string | null;
  background_image_path: string | null;
}

export interface EndCardSection {
  show: boolean;
  start_sec: number;
  duration_sec: number;
  next_episode_title: string | null;
  message: string | null;
}

export interface SubtitlesConfig {
  enabled: boolean;
  font: string;
  size_px: number;
  max_chars_per_line: number;
  style: "soft_drop_shadow" | "stroke" | "backdrop";
  position: "bottom_center" | "bottom_left" | "top_center";
  karaoke_reveal: boolean;
  emphasize_character_names: boolean;
}

export interface CharacterSpec {
  name: string | null;
  appearance: string;
  wardrobe: string | null;
  voice_notes: string | null;
}

export interface Timeline {
  version: number;
  episode_id: string;
  title: string;
  series: string | null;
  language: "th";
  width: number;
  height: number;
  fps: number;
  total_duration_sec: number;
  subtitles_config: SubtitlesConfig;
  visual_style: { base_prompt: string; negative_prompt: string; color_grade: ColorGrade };
  characters: Record<string, CharacterSpec>;
  audio_config: {
    music_bed: { default: string | null; by_mood: Record<string, string>; volume_db: number; crossfade_ms: number; duck_during_dialogue_db: number };
    ambience: { default: string | null; by_mood: Record<string, string>; volume_db: number };
  };
  intro: IntroSection | null;
  chapters: ChapterSection[];
  end_card: EndCardSection | null;
}
