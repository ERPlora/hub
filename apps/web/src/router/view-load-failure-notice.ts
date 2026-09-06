/**
 * The message the shell writes straight into the document when the app never got to mount.
 *
 * Two different causes end at this same wall of text, both on the app's FIRST navigation, which is
 * the only moment where an aborted navigation leaves a white page (`main.ts` mounts inside
 * `router.isReady().then(...)`):
 *
 *   - the screen's file could not be FETCHED and the one recovery reload did not help either
 *     (hub#1518) — see `./view-load-recovery` for that ladder;
 *   - the screen's own code THREW while it was being evaluated (hub#1524) — no ladder at all:
 *     reloading a code failure lands on the very same code, which is a boot loop.
 *
 * There is no Ionic, no toast and no router outlet to speak through in either case, so the plain
 * DOM is all that is left. What changes between them is the WORDS: hub#1518's copy blames the
 * connection, and saying that when nothing dropped sends the person off to restart a router that
 * is working fine. Hence `kind`, and a second set of strings behind it.
 *
 * Text comes from the catalogue (ADR-0055), styling from the Ionic theme tokens when they are
 * already on the page and from safe fallbacks when they are not. Styles are set through the CSSOM
 * rather than a `style` attribute or an injected stylesheet, so the strict CSP holds.
 */
import { i18n } from '../i18n';

/** Id of the notice element; also how a second call recognises the one already on screen. */
export const VIEW_LOAD_FAILURE_ID = 'view-load-failure';

/** Why the screen never opened. The two causes read differently to the person in front of it. */
export type ViewLoadFailureKind =
  /** The screen's file never arrived (hub#1518): the connection is the thing to check. */
  | 'download'
  /** The screen's own code threw (hub#1524): the connection has nothing to do with it. */
  | 'code';

/** Catalogue keys per cause. Keeping them together is what stops the two sets from drifting. */
const COPY: Record<ViewLoadFailureKind, { title: string; body: string; action: string }> = {
  download: {
    title: 'viewLoad.blockedTitle',
    body: 'viewLoad.blockedBody',
    action: 'viewLoad.blockedAction',
  },
  code: {
    title: 'viewLoad.brokenTitle',
    body: 'viewLoad.brokenBody',
    action: 'viewLoad.brokenAction',
  },
};

export interface ViewLoadFailureIo {
  doc?: Document;
  reload?: () => void;
  /** Defaults to hub#1518's original cause, so its callers and its tests read unchanged. */
  kind?: ViewLoadFailureKind;
}

export function showViewLoadFailure({
  doc = document,
  reload = () => window.location.reload(),
  kind = 'download',
}: ViewLoadFailureIo = {}): void {
  // Idempotent: a second failure must not stack a second wall of text on top of the first.
  if (doc.getElementById(VIEW_LOAD_FAILURE_ID)) return;

  const copy = COPY[kind];

  const notice = doc.createElement('div');
  notice.id = VIEW_LOAD_FAILURE_ID;
  notice.setAttribute('role', 'alert');
  notice.style.position = 'fixed';
  notice.style.inset = '0';
  notice.style.zIndex = '99999';
  notice.style.display = 'flex';
  notice.style.flexDirection = 'column';
  notice.style.alignItems = 'center';
  notice.style.justifyContent = 'center';
  notice.style.gap = '16px';
  notice.style.padding = '24px';
  notice.style.textAlign = 'center';
  notice.style.font = '16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  notice.style.background = 'var(--ion-background-color, #ffffff)';
  notice.style.color = 'var(--ion-text-color, #1f1f1f)';

  const title = doc.createElement('h1');
  title.textContent = i18n.global.t(copy.title);
  title.style.margin = '0';
  title.style.fontSize = '20px';
  title.style.fontWeight = '600';

  const body = doc.createElement('p');
  body.textContent = i18n.global.t(copy.body);
  body.style.margin = '0';
  body.style.maxWidth = '32rem';

  const action = doc.createElement('button');
  action.type = 'button';
  action.textContent = i18n.global.t(copy.action);
  action.style.minHeight = '44px'; // touch target: this is a till, not a desktop
  action.style.padding = '0 24px';
  action.style.border = '0';
  action.style.borderRadius = '8px';
  action.style.cursor = 'pointer';
  action.style.font = 'inherit';
  action.style.fontWeight = '600';
  action.style.background = 'var(--ion-color-primary, #3880ff)';
  action.style.color = 'var(--ion-color-primary-contrast, #ffffff)';
  action.addEventListener('click', () => reload());

  notice.append(title, body, action);
  doc.body.append(notice);
}
