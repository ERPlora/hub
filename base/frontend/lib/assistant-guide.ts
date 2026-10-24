// What guides the person in the assistant's panel, as keys of base's catalogue (the component translates them):
// - `setupShortcuts` (BASE-G121): «What is left to set up?» and «How do I set up “<step>”?» for up to four pending
//   steps of the checklist this person can do, in its order (never one done, not available or an administrator's);
// - `errorView` (BASE-G124, G122): the sentence of each failure and its way out (try again, a new conversation, the
//   plan, sign in again); a spent allowance or a plan without the assistant is no breakdown;
// - `usageNote` (BASE-G122): from 80 % of the month's messages, what is left of how many;
// - `screenLabel` (BASE-G114): a screen by the name the person sees in the menu, never its path.
import type { SessionMenuSection } from '@erplora/ui/shell';

import type { AssistantUsage, SetupStatus } from '../operations';

export const MAX_SETUP_SHORTCUTS = 4;

export interface Shortcut {
  key: string;
  title?: string;
}

export function setupShortcuts(status: SetupStatus | undefined): Shortcut[] {
  const steps = (status?.items ?? [])
    .filter((item) => item.state === 'pending' && item.actionable)
    .slice(0, MAX_SETUP_SHORTCUTS)
    .map((item) => ({ key: 'base.assistant.shortcuts.step', title: item.title }));
  return [{ key: 'base.assistant.shortcuts.missing' }, ...steps];
}

export type Recovery = 'retry' | 'new' | 'upgrade' | 'signin' | 'none';

export interface ErrorView {
  key: string;
  values?: Record<string, unknown>;
  recovery: Recovery;
}

export function errorView(code: string, details: Record<string, unknown> = {}): ErrorView {
  switch (code) {
    case 'assistant.unreachable':
      return { key: 'base.assistant.errors.unreachable', recovery: 'retry' };
    case 'assistant.cut':
      return { key: 'base.assistant.errors.cut', recovery: 'retry' };
    case 'assistant.quota_exceeded': {
      const limit = Number(details.limit ?? 0);
      if (limit <= 0) return { key: 'base.assistant.errors.noPlan', recovery: 'upgrade' };
      return {
        key: 'base.assistant.errors.quotaSpent',
        values: { used: Number(details.used ?? limit), limit, resetsAt: details.resets_at ?? null },
        recovery: 'upgrade',
      };
    }
    case 'assistant.rate_limited':
      return { key: 'base.assistant.errors.rateLimited', values: { seconds: Number(details.retry_after ?? 60) }, recovery: 'retry' };
    case 'assistant.too_large':
    case 'payload_too_large':
      return { key: 'base.assistant.errors.tooLarge', recovery: 'new' };
    case 'assistant.too_many_steps':
      return { key: 'base.assistant.errors.tooManySteps', recovery: 'none' };
    case 'unauthorized':
      return { key: 'base.assistant.errors.signedOut', recovery: 'signin' };
    default:
      return { key: 'base.assistant.errors.unavailable', recovery: 'retry' };
  }
}

/** From 80 % of the month's messages: how many are left of how many, and when they come back. */
export const NOTE_FROM = 0.8;

export function usageNote(usage: AssistantUsage | undefined): { left: number; limit: number; resetsAt: string | null } | null {
  if (!usage || usage.limit <= 0 || usage.used / usage.limit < NOTE_FROM) return null;
  return { left: Math.max(usage.limit - usage.used, 0), limit: usage.limit, resetsAt: usage.resets_at };
}

/** The platform's screens, by the key of their name in base's catalogue. */
export const PLATFORM_SCREENS: Record<string, string> = {
  '/': 'base.assistant.screens.home',
  '/apps': 'base.assistant.screens.apps',
  '/settings': 'base.assistant.screens.settings',
  '/system': 'base.assistant.screens.system',
  '/profile': 'base.assistant.screens.profile',
  '/employees': 'base.assistant.screens.employees',
  '/files': 'base.assistant.screens.files',
};

export function screenLabel(
  path: string,
  menu: SessionMenuSection[],
  t: (key: string) => string,
): string | undefined {
  const bare = path.split('#', 1)[0].replace(/\/+$/, '') || '/';
  if (PLATFORM_SCREENS[bare]) return t(PLATFORM_SCREENS[bare]);
  let best: { section: string; item: string; length: number } | undefined;
  for (const section of menu) {
    for (const item of section.items) {
      const matches = bare === item.path || bare.startsWith(`${item.path}/`);
      if (matches && (!best || item.path.length > best.length)) {
        best = { section: section.label, item: item.label, length: item.path.length };
      }
    }
  }
  if (!best) return undefined;
  return best.section && best.section !== best.item ? `${best.section} › ${best.item}` : best.item;
}
