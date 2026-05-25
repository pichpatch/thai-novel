/**
 * Remotion config — intentionally empty.
 *
 * All renderer options (codec, concurrency, pixel format, overwrite, props)
 * are passed via CLI flags from src/thai_novel/remotion/__init__.py, which
 * is more portable across Remotion 4.x point releases (the Config setter
 * names have shifted across versions).
 *
 * If you want to tweak settings persistently for `npx remotion studio`,
 * add `Config.setX(...)` calls here using setter names that exist in your
 * installed @remotion/cli (verify with `npx remotion versions`).
 */
export {};
