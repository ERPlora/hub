// The way in's browser rules. Entering with a PIN or a badge goes through Django's `/auth/pin` and `/auth/badge`, not
// operations, because they open a session. A USB badge reader types like a keyboard, ten times faster than a person,
// which is how its burst is told apart from typing.
import { ApiError, parseErrorEnvelope, readCookie, readSpaConfig, type StreamManager } from '@erplora/ui/sdk';

import type { SessionIdle } from '../operations/access';

import { readJsonBlock } from './embedded';
import { sessionDoorFetch } from './sign-out';

// ── Entering ─────────────────────────────────────────────────────────────────────────────────────────────────────

export type EntryPath = '/auth/pin' | '/auth/badge';

/** POSTs an entry (`{person, pin, next}` or `{badge, next}`) and answers where to go; a refusal throws the envelope's
 *  ApiError (`base.pin_incorrect`, `base.too_many_attempts` with `details.retry_after`…). */
export async function enterWith(
  path: EntryPath,
  body: Record<string, string>,
  doc: Document = document,
  fetcher: typeof fetch = sessionDoorFetch,
): Promise<string> {
  const config = readSpaConfig(doc);
  const response = await fetcher(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      [config.csrfHeader]: readCookie(doc.cookie, config.csrfCookieName) ?? '',
    },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) {
    const error = parseErrorEnvelope(response.status, text);
    const wait = Number(response.headers.get('Retry-After'));
    if (!Number.isFinite(wait) || wait <= 0) return Promise.reject(error);
    return Promise.reject(
      new ApiError(error.status, error.code, error.message, error.fields, { ...error.details, retry_after: wait }),
    );
  }
  let answer: unknown;
  try {
    answer = JSON.parse(text);
  } catch {
    answer = {};
  }
  return safeNext((answer as { next?: unknown }).next);
}

/** A path of this hub, else `/`: never another origin (`//host`, `/\host`, a scheme). */
export function safeNext(raw: unknown): string {
  if (typeof raw !== 'string' || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return '/';
  return raw;
}

/** `next` with the fragment of the Access page's own address (`/login?next=/settings#data`): the browser keeps a
 * link's fragment over the jump to `/login`, and the person goes back to the tab it named. A `next` that
 * names its own fragment keeps it. */
export function nextWithHash(next: string, hash: string): string {
  return hash && !next.includes('#') ? `${next}${hash}` : next;
}

// ── The badge reader ─────────────────────────────────────────────────────────────────────────────────────────────

/** The longest gap between two keys of one burst: five times the slowest reader, half a fast person's. */
export const BADGE_MAX_GAP_MS = 50;
/** The shortest badge: an EM4100 UID is 10 digits, the shortest on sale 4; under it, a shortcut. */
export const BADGE_MIN_LENGTH = 4;
const BADGE_CHARACTER = /^[A-Za-z0-9_-]$/;

export interface BadgeReaderOptions {
  target?: EventTarget;
  now?: () => number;
}

/** Hears the bursts of a badge reader on `target` until the returned function is called. The keys of a burst (from
 *  its second on) and its Enter go nowhere else; a person's keys and Enter are left alone. */
export function createBadgeReader(
  onBadge: (badge: string) => void,
  { target = document, now = () => Date.now() }: BadgeReaderOptions = {},
): () => void {
  let buffer = '';
  let lastKeyAt = 0;
  const onKeyDown = (event: Event): void => {
    const key = event as KeyboardEvent;
    if (key.ctrlKey || key.metaKey || key.altKey) {
      buffer = '';
      return;
    }
    const at = now();
    const withinBurst = buffer !== '' && at - lastKeyAt <= BADGE_MAX_GAP_MS;
    lastKeyAt = at;
    if (key.key === 'Enter') {
      const badge = withinBurst ? buffer : '';
      buffer = '';
      if (badge.length < BADGE_MIN_LENGTH) return;
      key.preventDefault();
      key.stopPropagation();
      onBadge(badge);
      return;
    }
    if (!BADGE_CHARACTER.test(key.key)) {
      buffer = '';
      return;
    }
    buffer = withinBurst ? buffer + key.key : key.key;
    if (buffer.length > 1) {
      key.preventDefault();
      key.stopPropagation();
    }
  };
  target.addEventListener('keydown', onKeyDown, true);
  return () => {
    target.removeEventListener('keydown', onKeyDown, true);
    buffer = '';
  };
}

// ── The idle lock ────────────────────────────────────────────────────────────────────────────────────────────────

/** What counts as somebody using the till: a finger, a key, the wheel. */
export const IDLE_ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const;

/** Calls `onIdle` once, after `minutes` without activity on `target`; the returned function disarms it. */
export function createIdleLock(minutes: number, onIdle: () => void, target: EventTarget = window): () => void {
  const span = minutes * 60_000;
  let last = Date.now();
  let done = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const check = (): void => {
    if (done) return;
    const left = span - (Date.now() - last);
    if (left > 0) {
      timer = setTimeout(check, left);
      return;
    }
    stop();
    onIdle();
  };
  const activity = (): void => {
    last = Date.now();
  };
  function stop(): void {
    done = true;
    if (timer !== undefined) clearTimeout(timer);
    for (const type of IDLE_ACTIVITY_EVENTS) target.removeEventListener(type, activity, true);
  }
  for (const type of IDLE_ACTIVITY_EVENTS) target.addEventListener(type, activity, { capture: true, passive: true });
  timer = setTimeout(check, span);
  return stop;
}

/** The idle lock of `minutes` (none while null), armed again only when `set` brings other minutes: the same ones
 *  answered again (the live stream reconnecting) keep counting from the last touch. Once stopped, it stays so. */
function followIdleLock(minutes: number | null, onIdle: () => void, target?: EventTarget) {
  let current = minutes;
  let stopped = false;
  const arm = (value: number | null) => (value ? createIdleLock(value, onIdle, target) : () => undefined);
  let disarm = arm(current);
  return {
    set(next: number | null): void {
      if (stopped || next === current) return;
      current = next;
      disarm();
      disarm = arm(next);
    },
    stop(): void {
      stopped = true;
      disarm();
    },
  };
}

// ── The session's way in, from the HTML ──────────────────────────────────────────────────────────────────────────

/** `hub-home.access` (`base.queries.shell_access`): how this session was opened (`support`: a person of ERPlora's
 *  support), whether «Switch user» is offered and after how many idle minutes the till locks (null: it does not). */
export interface ShellAccess {
  credential: 'account' | 'pin' | 'badge' | 'support';
  switch_user: boolean;
  idle_minutes: number | null;
}

const NO_ACCESS: ShellAccess = Object.freeze({ credential: 'account', switch_user: false, idle_minutes: null });

export function readAccess(doc: Document = document): ShellAccess {
  const access = readJsonBlock<{ access?: ShellAccess }>('hub-home', doc)?.access;
  return access ? { ...NO_ACCESS, ...access } : { ...NO_ACCESS };
}

// ── «Now serving {name}», across the reload of «Switch user» ─────────────────────────────────────────────────────

const SWITCHED_KEY = 'erplora.base.switched';

/** Leaves the name of whoever just entered for the page that the reload paints. A browser that keeps nothing
 *  (a private window) tells nothing: the switch itself already happened. */
export function announceSwitch(name: string, storage: Storage = sessionStorage): void {
  try {
    storage.setItem(SWITCHED_KEY, name);
  } catch {
    // Nothing kept: the toast is not told, the session is already the new person's.
  }
}

/** The name left by `announceSwitch`, once. */
export function takeSwitchAnnouncement(storage: Storage = sessionStorage): string | null {
  try {
    const name = storage.getItem(SWITCHED_KEY);
    storage.removeItem(SWITCHED_KEY);
    return name;
  } catch {
    return null;
  }
}

/** Leaves for `url` with a full load: an entry's new session cookie, or erplora.com's sign-in. */
export function leaveTo(url: string): void {
  window.location.assign(url);
}

/** Reloads on `url` in place of this page: after «Switch user», Back never returns to what whoever left had open. */
export function replaceWith(url: string): void {
  window.location.replace(url);
}

// ── What the session says of the person, read again ──────────────────────────────────────────────────────────────

/** Dispatched on the window when what the session says of the person changed (their name, saved in «My profile»):
 *  the entry point owns the session the shell paints, so it reads `base.session.me` again. */
export const SESSION_CHANGED = 'erplora:base-session-changed';

export function sessionChanged(target: EventTarget = window): void {
  target.dispatchEvent(new Event(SESSION_CHANGED));
}

/** Listens for `sessionChanged`; returns the function that stops listening. */
export function onSessionChanged(listener: () => void, target: EventTarget = window): () => void {
  target.addEventListener(SESSION_CHANGED, listener);
  return () => target.removeEventListener(SESSION_CHANGED, listener);
}

// ── Once the shell is mounted ────────────────────────────────────────────────────────────────────────────────────

export interface WayInDeps {
  translate: (key: string, values?: Record<string, unknown>) => string;
  /** The Hub's sign out (the shell's `logout`): a form POST, then the way in. */
  logout: () => void;
  toast: (message: string) => void;
  /** The shell's `applyUserThemePreferences`; `null`: the business's. */
  paint: (mode: 'system' | 'light' | 'dark' | null, palette: string | null, scale: number) => void;
  /** The shell's `resetUserThemePreferences`. */
  reset: () => void;
  /** The name of the person of the session. */
  label: () => string | undefined;
  storage?: Storage;
  target?: EventTarget;
  /** The tab's live stream (the client's): `base.session.idle` brings an open till the business's new idle minutes. */
  stream: Pick<StreamManager, 'subscribe'>;
}

interface Appearance {
  theme_mode: '' | 'system' | 'light' | 'dark';
  palette: string;
  ui_scale: number;
}

/** What the session's way in asks of the mounted shell: the idle lock of a till that always asks, with the minutes the
 *  page came with and then those the business changes while it is open, the person's own appearance and, after
 *  «Switch user», «Now serving {name}» with the appearance of whoever left forgotten. Returns the function that
 *  disarms the lock. Only a session in the hub follows the minutes: the live stream refuses a page without one. */
export function startWayIn(doc: Document, deps: WayInDeps): () => void {
  const home = readJsonBlock<{ access?: ShellAccess; preferences?: Appearance }>('hub-home', doc);
  const lock = followIdleLock(readAccess(doc).idle_minutes, deps.logout, deps.target);
  const leave = home?.access
    ? deps.stream.subscribe('base.session.idle', {}, (event) => {
        // A read that fails keeps the minutes the till had.
        if (event.type === 'result') lock.set((event.data as SessionIdle).idle_minutes);
      })
    : () => undefined;
  const appearance = home?.preferences;
  const switched = takeSwitchAnnouncement(deps.storage);
  if (appearance && (appearance.theme_mode || appearance.palette || appearance.ui_scale !== 100)) {
    deps.paint(appearance.theme_mode || null, appearance.palette || null, appearance.ui_scale);
  } else if (switched !== null) {
    deps.reset();
  }
  if (switched !== null) deps.toast(deps.translate('base.switchUser.nowServing', { name: deps.label() || switched }));
  return () => {
    leave();
    lock.stop();
  };
}
