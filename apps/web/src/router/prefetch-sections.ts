/**
 * Downloads the screens behind a set of sections ahead of time (hub#2325).
 *
 * Every view of the shell is loaded on demand, so a tap on the side menu used to be the moment the
 * section's file left for the network: a blink right then (the till hops wifi→4G, CI's
 * `net::ERR_NETWORK_CHANGED`) or a machine too busy to fetch and compile it in time, and the tap
 * went nowhere. Running the same `import()` the router would run, once the app is idle, leaves the
 * module in the document's module map, so the tap resolves it without a request.
 *
 * Best-effort and silent: a download that fails changes nothing the person sees. But per the HTML
 * module map that file is now remembered as failed for the life of this document, so the section
 * joins the ones rung 4 of `./view-load-recovery` opens in a fresh document — otherwise the first
 * tap would earn a "try again" toast for a blink that happened minutes before.
 */
import type { Router } from 'vue-router';
import { isViewLoadError, sectionOf, sectionsFailedInApp } from './view-load-recovery';

/** The slice of the router (and of the shell) this needs; injected so it can be tested alone. */
export interface PrefetchSectionsIo {
  resolve: (path: string) => { matched: ReadonlyArray<{ components?: Record<string, unknown> | null }> };
  /** Sections whose file failed to arrive in THIS document (shared with `router.onError`). */
  failedInApp: Set<string>;
  /** Resolves when the app has nothing better to do. */
  whenIdle: () => Promise<void>;
}

// Loaders already started in this document. The module map makes a repeat free, but a repeat after
// a failure would just fail again, and the shell asks again every time the menu changes.
const attempted = new WeakSet<object>();

/** Lazy loaders of the screens `path` mounts. A screen the router already loaded is an object. */
function loadersOf(path: string, io: PrefetchSectionsIo): Array<() => unknown> {
  let matched: ReturnType<PrefetchSectionsIo['resolve']>['matched'];
  try {
    matched = io.resolve(path).matched;
  } catch {
    return [];
  }
  return matched
    .flatMap((record) => Object.values(record.components ?? {}))
    .filter((component): component is () => unknown => typeof component === 'function');
}

/** One section after another, each when the app is idle. Never rejects. */
export async function prefetchSections(paths: readonly string[], io: PrefetchSectionsIo): Promise<void> {
  for (const path of paths) {
    for (const load of loadersOf(path, io)) {
      if (attempted.has(load)) continue;
      attempted.add(load);
      await io.whenIdle();
      try {
        await load();
      } catch (error) {
        // A screen whose own code throws is left alone: the tap reports that bug as the bug it is.
        if (isViewLoadError(error)) io.failedInApp.add(sectionOf(path));
      }
    }
  }
}

/** Resolves on the browser's next idle period; Safari has no `requestIdleCallback`, so a timer. */
function browserIdle(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window.requestIdleCallback === 'function') {
      // The timeout keeps a page that is never idle (an animation on screen) from waiting forever.
      window.requestIdleCallback(() => resolve(), { timeout: 5_000 });
    } else {
      setTimeout(resolve, 200);
    }
  });
}

/** The shell's entry point: `paths` (the side menu's) through `router`, when the browser is idle. */
export function prefetchSectionViews(router: Pick<Router, 'resolve'>, paths: readonly string[]): Promise<void> {
  return prefetchSections(paths, {
    resolve: (path) => router.resolve(path),
    failedInApp: sectionsFailedInApp,
    whenIdle: browserIdle,
  });
}
