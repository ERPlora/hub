// hub#1588 — the build SAYS which OutfitKit went into the image.
//
// **The problem.** `docker/Dockerfile` re-resolves `@erplora/outfitkit@latest` on every build (with
// a per-build cachebust), so the range in `package.json` is not what ships and the lockfile pin is
// not what ships either. Until now the version an image carried could only be DEDUCED from the day
// it was built, cross-referenced by hand against npm's publish dates — which is exactly what
// `module-toolkit` had to encode as a hand-maintained table (`validate-outfitkit-floor.mjs`).
//
// That matters because the `ok-*` a module paints with are the SHELL's, not the ones baked into its
// own bundle: whoever writes a module cannot tell whether their screen will render in the customer's
// hub. It has cost two incidents in four days (hub#1547, ERPlora/sales#259).
//
// **What this does.** The same resolved version the shell reports at runtime
// (`__OUTFITKIT_VERSION__`, see `src/lib/outfitkit-skew.ts`) is also written to
// `dist/outfitkit-version.json`, which `docker/Dockerfile` copies into the image as
// `/app/web/outfitkit-version.json` — served by the runtime's static handler
// (`crates/server/src/routes.rs`, `with_static_frontend`). One source, two outputs: a build cannot
// stamp one version and run another.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Plugin } from 'vite';

/** Name of the stamp inside `dist/` (and therefore inside the image, under `HUB_WEB_DIR`). */
export const OUTFITKIT_VERSION_FILE = 'outfitkit-version.json';

/**
 * Version of `@erplora/outfitkit` REALLY installed for the shell — read from the resolved package,
 * never from the declared range.
 *
 * Looks in the app's own `node_modules` first and falls back to the workspace root, in that order:
 * when both carry a copy, the one the app resolves is the one that ends up in the bundle. Returns
 * `''` when it cannot be resolved; deciding what that means belongs to the caller —
 * `outfitkitVersionStamp` fails the build, the runtime warning just stays quiet.
 */
export function resolveOutfitkitVersion(appDir: string): string {
  for (const base of [appDir, join(appDir, '..', '..')]) {
    try {
      const pkg = JSON.parse(
        readFileSync(join(base, 'node_modules', '@erplora', 'outfitkit', 'package.json'), 'utf8'),
      );
      if (typeof pkg.version === 'string' && pkg.version) return pkg.version;
    } catch {
      // Not installed here (or unreadable): try the next candidate, then give up with ''.
    }
  }
  return '';
}

/**
 * Vite plugin that writes the stamp into `dist/`.
 *
 * Build-only: `vite dev` has no `dist/` to stamp. And a build that cannot name its OutfitKit
 * **fails** rather than shipping `""` — a blank stamp is worse than none, because the consumer
 * cannot tell it apart from a version and would silently go back to guessing by date.
 */
export function outfitkitVersionStamp(versions: { outfitkit: string; hub: string }): Plugin {
  return {
    name: 'erplora-outfitkit-version',
    apply: 'build',
    generateBundle() {
      if (!versions.outfitkit) {
        this.error({
          code: 'OUTFITKIT_VERSION_UNRESOLVED',
          message:
            `Could not resolve the installed @erplora/outfitkit, so this build cannot say which one ` +
            `it carries. Install the shell dependencies (pnpm install) before building: without the ` +
            `stamp, an image's OutfitKit is once again a date to guess from (hub#1588).`,
        });
      }
      this.emitFile({
        type: 'asset',
        fileName: OUTFITKIT_VERSION_FILE,
        source: `${JSON.stringify({ outfitkit: versions.outfitkit, hub: versions.hub }, null, 2)}\n`,
      });
    },
  };
}
