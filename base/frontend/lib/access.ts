// The way in's browser rules (APP-BASE-3): entering with a PIN or a badge (BASE-G55, G56, G60: Django's `/auth/pin`
// and `/auth/badge`, which open a session, so they are not operations), the badge reader's burst (G56: a USB reader
// types like a keyboard, ten times faster than a person; the old hub's `badge-scanner.ts`), the lock of a till nobody
// touches (G59; its `idle-logout.ts`), the session's way in that `base/spa.py` embeds (`hub-home.access`), a `next`
// that never leaves the hub, and the «Now serving {name}» note that crosses the reload of «Switch user».
import { ApiError, parseErrorEnvelope, readCookie, readSpaConfig } from '@erplora/ui/sdk';

import { readJsonBlock } from './home';

// ── Entering ─────────────────────────────────────────────────────────────────────────────────────────────────────

export type EntryPath = '/auth/pin' | '/auth/badge';

/** POSTs an entry (`{person, pin, next}` or `{badge, next}`) and answers where to go; a refusal throws the envelope's
 *  ApiError (`base.pin_incorrect`, `base.too_many_attempts` with `details.retry_after`…). */
export async function enterWith(
  path: EntryPath,
  body: Record<string, string>,
  doc: Document = document,
  // `/auth/pin` and `/auth/badge` open a session, which no operation does (Django's `login` needs the request, as the
  // callback's): the SDK has no route to them. Same origin and the SDK's CSRF header, as its own calls.
  // eslint-disable-next-line no-restricted-globals -- see above
  fetcher: typeof fetch = (...args) => fetch(...args),
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

// ── The session's way in, from the HTML ──────────────────────────────────────────────────────────────────────────

/** `hub-home.access` (`base.queries.shell_access`): how this session was opened, whether «Switch user» is offered
 *  and after how many idle minutes the till locks (null: it does not). */
export interface ShellAccess {
  credential: 'account' | 'pin' | 'badge';
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

// ── Once the shell is mounted ────────────────────────────────────────────────────────────────────────────────────

export interface WayInDeps {
  translate: (key: string, values?: Record<string, unknown>) => string;
  /** The Hub's sign out (the shell's `logout`): a form POST, then the way in. */
  logout: () => void;
  toast: (message: string) => void;
  /** The shell's `applyUserThemePreferences`; `null`: the business's. */
  paint: (mode: 'system' | 'light' | 'dark' | null, palette: string | null) => void;
  /** The shell's `resetUserThemePreferences`. */
  reset: () => void;
  /** The name of the person of the session. */
  label: () => string | undefined;
  storage?: Storage;
  target?: EventTarget;
}

interface Appearance {
  theme_mode: '' | 'system' | 'light' | 'dark';
  palette: string;
}

/** What the session's way in asks of the mounted shell: the idle lock of a till that always asks (BASE-G59), the
 *  person's own appearance (BASE-G125) and, after «Switch user», «Now serving {name}» with the appearance of whoever
 *  left forgotten (gh:hub#2506). Returns the function that disarms the lock. */
export function startWayIn(doc: Document, deps: WayInDeps): () => void {
  const access = readAccess(doc);
  const stop = access.idle_minutes ? createIdleLock(access.idle_minutes, deps.logout, deps.target) : () => undefined;
  const appearance = readJsonBlock<{ preferences?: Appearance }>('hub-home', doc)?.preferences;
  const switched = takeSwitchAnnouncement(deps.storage);
  if (appearance && (appearance.theme_mode || appearance.palette)) {
    deps.paint(appearance.theme_mode || null, appearance.palette || null);
  } else if (switched !== null) {
    deps.reset();
  }
  if (switched !== null) deps.toast(deps.translate('base.switchUser.nowServing', { name: deps.label() || switched }));
  return stop;
}
