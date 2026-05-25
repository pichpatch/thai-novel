#!/usr/bin/env node
/**
 * scripts/render.mjs
 *
 * Programmatic Remotion render. Bypasses `npx remotion render` whose
 * --props/calculateMetadata path doesn't reliably override the composition's
 * static durationInFrames in Remotion 4.x point releases.
 *
 * Reads the timeline.json directly, computes duration from it, and drives
 * @remotion/bundler + @remotion/renderer end-to-end.
 *
 * Usage:
 *   node scripts/render.mjs <timeline.json> <out.mp4> [concurrency]
 */
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const __filename = url.fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

const [, , timelinePathArg, outPathArg, concurrencyArg] = process.argv;
if (!timelinePathArg || !outPathArg) {
  console.error("usage: node scripts/render.mjs <timeline.json> <out.mp4> [concurrency]");
  process.exit(2);
}

const timelinePath = path.resolve(timelinePathArg);
const outPath = path.resolve(outPathArg);
const concurrency = Number(concurrencyArg ?? 3);

if (!fs.existsSync(timelinePath)) {
  console.error(`timeline not found: ${timelinePath}`);
  process.exit(2);
}

const timeline = JSON.parse(fs.readFileSync(timelinePath, "utf-8"));
console.log(
  `[render] episode=${timeline.episode_id}  ` +
  `${timeline.total_duration_sec.toFixed(1)}s @ ${timeline.fps}fps  ` +
  `${timeline.width}x${timeline.height}  concurrency=${concurrency}`
);

// ── 1. Bundle ───────────────────────────────────────────────────────────────
// publicDir is critical: defaults can vary, and the Python caller has
// materialized real files into remotion/public/ (hardlinks).
const publicDir = path.join(projectRoot, "remotion", "public");
console.log(`[render] bundling (publicDir=${publicDir})...`);
const bundleLocation = await bundle({
  entryPoint: path.join(projectRoot, "remotion", "src", "index.ts"),
  publicDir,
  onProgress: (progress) => {
    if (progress === 100) process.stdout.write(`\r[render] bundle ${progress}%\n`);
    else process.stdout.write(`\r[render] bundle ${progress}%   `);
  },
  webpackOverride: (config) => config,
});

// ── 2. Resolve composition with our props (this fires calculateMetadata
//      AND lets us override duration via inputProps deterministically) ────────
console.log(`[render] selecting composition with timeline props...`);
const composition = await selectComposition({
  serveUrl: bundleLocation,
  id: "Episode",
  inputProps: { timeline },
});

// Force the real duration even if calculateMetadata didn't run inside the bundle.
const desiredFrames = Math.max(1, Math.round(timeline.total_duration_sec * timeline.fps));
const resolvedComposition = {
  ...composition,
  durationInFrames: desiredFrames,
  fps: timeline.fps,
  width: timeline.width,
  height: timeline.height,
};
console.log(
  `[render] composition: ${resolvedComposition.durationInFrames} frames ` +
  `@ ${resolvedComposition.fps}fps = ${(resolvedComposition.durationInFrames / resolvedComposition.fps).toFixed(1)}s`
);

// ── 3. Render ───────────────────────────────────────────────────────────────
fs.mkdirSync(path.dirname(outPath), { recursive: true });

let lastPct = -1;
await renderMedia({
  composition: resolvedComposition,
  serveUrl: bundleLocation,
  codec: "h264",
  outputLocation: outPath,
  inputProps: { timeline },
  concurrency,
  imageFormat: "jpeg",
  jpegQuality: 92,
  pixelFormat: "yuv420p",
  overwrite: true,
  onProgress: ({ progress, renderedFrames, encodedFrames }) => {
    const pct = Math.floor(progress * 100);
    if (pct !== lastPct) {
      lastPct = pct;
      process.stdout.write(
        `\r[render] ${pct.toString().padStart(3)}%  ` +
        `rendered ${renderedFrames}/${resolvedComposition.durationInFrames}  ` +
        `encoded ${encodedFrames}  `
      );
    }
  },
});

process.stdout.write("\n");
console.log(`[render] ✓ ${outPath}`);
process.exit(0);
