// The Hub's configuration of the shared assistant (`@erplora/ui/components`; the SaaS mounts the same chat with its
// own): `configureAssistant(hubAssistant(doc))` when the SPA boots (main.ts), and `HUB_ASSISTANT` in the test helpers
// that mount its pieces (`mountBase`, `mount-sale`).
// - A turn goes to `base.assistant.turn`'s route; the allowance, a dictation and a report through base's operations.
// - «Read aloud» in a server voice (round 2026-11-03n): the mp3 of `base.assistant.speak`'s route; when it fails, the
//   panel reads with the device's voice. Only where the page says erplora.com has a voice (`hub-home.server_voice`,
//   off by default since round 2026-11-04a, `hubAssistant`): else no choice of voice and no request, the device reads.
// - Whoever sees the Home uses it (BASE-G110); whoever administers the business upgrades the plan, on erplora.com's
//   page the Home's block gives (gh:hub#1259).
// - A write a manager must approve goes through APP-BASE-5's approvals (BASE-G118): the dialog «An approval is
//   needed», then the same turn again with the pass in `X-Elevation-Token`.
// - base's words: the verb of each write (`base.assistant.card.actions.<action>`, or of the whole operation when its
//   action's verb does not say it, `base.assistant.card.operations.<app>.<entity>.<action>`; one per action of every
//   write the assistant may run, guardrail: base/tests/test_assistant.py), the platform's screens
//   (`base.assistant.screens.<key>`) and the setup's shortcuts of the empty conversation (BASE-G121).
import type { AssistantApproval, AssistantConfig, AssistantSpeech } from '@erplora/ui/components';
import { parseErrorEnvelope, readCookie, readSpaConfig } from '@erplora/ui/sdk';

import type { SetupStatus } from '../operations';
import en from '../locale/en.json';
import { type AskApproval, approvalPass, questionOf, withApproval } from './approval';
import { type HubHome, readJsonBlock } from './home';

/** The verb of each action a card or a receipt names, base's catalogue; another one is «Do this». */
const ACTIONS: Readonly<Record<string, string>> = en.base.assistant.card.actions;

/** The verb of a write whose action's verb does not say what it does: emptying a cart (`cart_checkout.cart.clear`) is
 *  not taking a route away, Kitchen's `clear`, nor a cash count adding anything
 *  (FIX-HUB-BASE-ASSISTANT-CARD-SAYS-REMOVE-FOR-EMPTYING-A-CART). */
const OPERATIONS: Readonly<Record<string, Readonly<Record<string, Readonly<Record<string, string>>>>>> =
  en.base.assistant.card.operations;

/** The platform's screens a receipt names by their key (the names the server gives them, base/assistant.py
 *  `SCREEN_NAMES`). */
const SCREENS: Readonly<Record<string, string>> = en.base.assistant.screens;

/** The platform's screens by their path. */
const PLATFORM_SCREENS: Readonly<Record<string, string>> = {
  '/': 'home',
  '/apps': 'apps',
  '/settings': 'settings',
  '/system': 'system',
  '/profile': 'profile',
  '/employees': 'employees',
  '/files': 'files',
};

/** The key of the verb of a write, by its operation's name (`<app>.<entity>.<action>`; an action alone is one too):
 *  its own, else its action's, else «Do this». */
export function actionKey(operation: string): string {
  const [app, entity, action] = operation.split('.');
  const entities = Object.hasOwn(OPERATIONS, app) ? OPERATIONS[app] : {};
  const actions = entity !== undefined && Object.hasOwn(entities, entity) ? entities[entity] : {};
  if (action !== undefined && Object.hasOwn(actions, action)) return `base.assistant.card.operations.${operation}`;
  const last = operation.split('.').at(-1) ?? '';
  return `base.assistant.card.actions.${Object.hasOwn(ACTIONS, last) ? last : 'other'}`;
}

/** The key of the name of the platform's screen a receipt names (the server's `screen`); none for an app's. */
export function placeKey(screen: string | undefined): string | null {
  return screen && Object.hasOwn(SCREENS, screen) ? `base.assistant.screens.${screen}` : null;
}

/** The key of the name of a path of the platform (`/settings`); none for an app's, which the menu names. */
export function platformScreenKey(path: string): string | null {
  return Object.hasOwn(PLATFORM_SCREENS, path) ? `base.assistant.screens.${PLATFORM_SCREENS[path]}` : null;
}

export const MAX_SETUP_SHORTCUTS = 4;

export interface Shortcut {
  key: string;
  title?: string;
}

/** «What is left to set up?» and «How do I set up “<step>”?» for up to four pending steps of the checklist this person
 *  can do, in its order (never one done, not available or an administrator's). */
export function setupShortcuts(status: SetupStatus | undefined): Shortcut[] {
  const steps = (status?.items ?? [])
    .filter((item) => item.state === 'pending' && item.actionable)
    .slice(0, MAX_SETUP_SHORTCUTS)
    .map((item) => ({ key: 'base.assistant.shortcuts.step', title: item.title }));
  return [{ key: 'base.assistant.shortcuts.missing' }, ...steps];
}

/** APP-BASE-5's approvals around each request of a turn: `ask` is the dialog «An approval is needed» unless a test
 *  gives its own; nobody approving hands back the refusal, which the assistant hears as a «Cancel». */
export function hubApproval(ask?: AskApproval): AssistantApproval {
  return {
    run: (request) => withApproval(request, ask ? { ask } : {}),
    declined: (error) => questionOf(error) !== null,
  };
}

/** The route of `base.assistant.speak`. */
export const SPEAK_URL = '/api/assistant/speak';

/** The mp3 of `input` read aloud in its server voice, from `base.assistant.speak`'s route; a refusal rejects with the
 *  envelope's ApiError, and the panel reads with the device's voice instead. Its `signal` (the person stopped the
 *  reading before the audio arrived) aborts the request. */
export async function speakAloud(
  { signal, ...input }: AssistantSpeech,
  doc: Document = document,
  // The SDK's client reads JSON only, never an mp3: same origin and the SDK's CSRF header, as its own calls.
  // eslint-disable-next-line no-restricted-globals -- see above
  fetcher: typeof fetch = (...args) => fetch(...args),
): Promise<Blob> {
  const config = readSpaConfig(doc);
  const response = await fetcher(SPEAK_URL, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'audio/mpeg',
      [config.csrfHeader]: readCookie(doc.cookie, config.csrfCookieName) ?? '',
    },
    body: JSON.stringify(input),
    signal,
  });
  if (!response.ok) throw parseErrorEnvelope(response.status, await response.text());
  return response.blob();
}

/** base's modules are read when each piece runs, never when this is built: a test that mocks one of them (an app's
 *  `approval` without `approvalPass`) still loads this file through a helper that configures it. */
export const HUB_ASSISTANT: AssistantConfig = {
  turnUrl: '/api/assistant/turn',
  elevationToken: () => approvalPass(),
  approval: hubApproval(),
  usage: (client) => client.api.call('base.assistant.usage', {}),
  transcribe: (client, clip) => client.api.call('base.assistant.transcribe', clip),
  report: (client, report) => client.api.call('base.assistant.report', report),
  canUse: (session) => session.can('base.view_home'),
  canUpgrade: (session) => session.can('base.administer_hub'),
  planUrl: () => readJsonBlock<HubHome>('hub-home')?.plan_url ?? '',
  verbKey: actionKey,
  placeKey,
  screenKey: platformScreenKey,
};

/** The Hub's configuration for the page `doc`: `HUB_ASSISTANT`, with the server's voice (`speak`) only where the page
 *  says erplora.com has one (`hub-home.server_voice`, `ASSISTANT_SERVER_VOICE`). */
export function hubAssistant(doc: Document = document): AssistantConfig {
  if (readJsonBlock<HubHome>('hub-home', doc)?.server_voice !== true) return HUB_ASSISTANT;
  return { ...HUB_ASSISTANT, speak: (input) => speakAloud(input, doc) };
}
