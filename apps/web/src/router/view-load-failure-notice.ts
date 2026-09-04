/**
 * The last rung of the view-load recovery (hub#1518): a message written straight into the
 * document.
 *
 * It is used in exactly one situation — the app's first navigation could not fetch the screen's
 * code, the one recovery reload did not help either, and therefore Vue was never mounted. There is
 * no Ionic, no toast and no router outlet to speak through, so the plain DOM is all that is left.
 * The alternative is the white page this issue is about, and a till that shows nothing tells the
 * person nothing.
 *
 * Text comes from the catalogue (ADR-0055), styling from the Ionic theme tokens when they are
 * already on the page and from safe fallbacks when they are not. Styles are set through the CSSOM
 * rather than a `style` attribute or an injected stylesheet, so the strict CSP holds.
 */
import { i18n } from '../i18n';

/** Id of the notice element; also how a second call recognises the one already on screen. */
export const VIEW_LOAD_FAILURE_ID = 'view-load-failure';

export interface ViewLoadFailureIo {
  doc?: Document;
  reload?: () => void;
}

export function showViewLoadFailure({
  doc = document,
  reload = () => window.location.reload(),
}: ViewLoadFailureIo = {}): void {
  // Idempotent: a second failure must not stack a second wall of text on top of the first.
  if (doc.getElementById(VIEW_LOAD_FAILURE_ID)) return;

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
  title.textContent = i18n.global.t('viewLoad.blockedTitle');
  title.style.margin = '0';
  title.style.fontSize = '20px';
  title.style.fontWeight = '600';

  const body = doc.createElement('p');
  body.textContent = i18n.global.t('viewLoad.blockedBody');
  body.style.margin = '0';
  body.style.maxWidth = '32rem';

  const action = doc.createElement('button');
  action.type = 'button';
  action.textContent = i18n.global.t('viewLoad.blockedAction');
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
