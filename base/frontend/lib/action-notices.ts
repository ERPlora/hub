// The hub's source of the action center (`createShell({ actionNotices })`): every counter of the bell above zero and,
// while a step blocks invoicing, «You cannot issue invoices yet», as data. The shell paints them; no screen does.
// The server does not say yet how grave a counter is nor what its button says: the ones known today take theirs from
// the table below, and the rest are warnings with «Open». What the server does send of a counter wins.
import { useLive } from '@erplora/ui/sdk';
import type { ActionNotice, ActionNoticeSource, NoticeAction, NoticeDue, NoticeSeverity } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

import type { BellCounter, SetupItem, SetupStatus } from '../operations';
import { useBellCounters } from './bell-counters';
import { blockingItems } from './home';
import { useBaseI18n } from './i18n';

type Translate = ReturnType<typeof useBaseI18n>['t'];

/** What a counter of the bell may also say of itself; each one missing takes its default here. */
interface CounterWords {
  severity?: NoticeSeverity;
  title?: string;
  body?: string;
  action_label?: string;
  due?: NoticeDue;
}

type HubCounter = BellCounter & CounterWords;

/** The i18n keys of a counter known today: its title, with the count, and the label of its button. */
interface KnownCounter {
  severity?: NoticeSeverity;
  title: string;
  action: string;
}

const KNOWN_COUNTERS: Record<string, KnownCounter> = {
  'base.failed_events': { severity: 'danger', title: 'base.notices.failedEvents.title', action: 'base.notices.failedEvents.action' },
  'base.plan_limits': { severity: 'warning', title: 'base.notices.planLimits.title', action: 'base.notices.planLimits.action' },
  'appointment.to_confirm': { title: 'base.notices.appointments.title', action: 'base.notices.appointments.action' },
  'whatsapp_inbox.awaiting_reply': { title: 'base.notices.whatsapp.title', action: 'base.notices.whatsapp.action' },
  'demo.open_items': { severity: 'info', title: 'base.notices.demo.title', action: 'base.notices.demo.action' },
};
/** Printing declares one counter per printing function: `printing.stalled_<usage>`. */
const PRINTING_STALLED = 'printing.stalled_';
const PRINTING: KnownCounter = { title: 'base.notices.printing.title', action: 'base.notices.printing.action' };

/** The ⛔ steps known today and the label of their button. */
const STEP_ACTIONS: Record<string, string> = {
  'invoice.business_identity': 'base.blocking.steps.businessIdentity',
  'verifactu.sending_route': 'base.blocking.steps.verifactu',
};

const BELL_ICON = 'ion:notifications-outline';
const BLOCKING_ICON = 'ion:alert-circle-outline';

const knownCounter = (key: string): KnownCounter | undefined =>
  KNOWN_COUNTERS[key] ?? (key.startsWith(PRINTING_STALLED) ? PRINTING : undefined);

function counterTitle(counter: HubCounter, known: KnownCounter | undefined, t: Translate): string {
  if (counter.title) return counter.title;
  const values = { label: counter.label, count: counter.count };
  return t(known?.title ?? 'base.notices.counter', values);
}

function counterNotice(counter: HubCounter, t: Translate, reachable: (route: string) => boolean): ActionNotice {
  const known = knownCounter(counter.key);
  const title = counterTitle(counter, known, t);
  const action = reachable(counter.route)
    ? { label: counter.action_label || t(known?.action ?? 'base.notices.open'), to: counter.route }
    : undefined;
  return {
    id: counter.key,
    severity: counter.severity ?? known?.severity ?? 'warning',
    icon: counter.icon || BELL_ICON,
    label: title,
    title,
    ...(counter.body ? { body: counter.body } : {}),
    count: counter.count,
    ...(counter.due ? { due: counter.due } : {}),
    ...(action ? { action } : {}),
  };
}

function stepAction(item: SetupItem, t: Translate): NoticeAction {
  const known = STEP_ACTIONS[item.key];
  return { label: known ? t(known) : t('base.blocking.configureStep', { step: item.title }), to: item.route };
}

/** «You cannot issue invoices yet» while a ⛔ step is pending: a button to each of the first two that this person can
 *  set up from a screen of this hub, or, when none, who has to. */
function blockingNotice(
  status: SetupStatus | undefined,
  words: { t: Translate; locale: string },
  reachable: (route: string) => boolean,
): ActionNotice | undefined {
  const items = blockingItems(status);
  if (items.length === 0) return undefined;
  const { t, locale } = words;
  const steps = new Intl.ListFormat(locale, { type: 'conjunction' }).format(items.map((item) => item.title));
  const [action, secondary] = items.filter((item) => item.actionable && reachable(item.route)).map((item) => stepAction(item, t));
  const missing = t('base.blocking.body', { steps });
  const title = t('base.blocking.title');
  return {
    id: 'base.blocking',
    severity: 'danger',
    icon: BLOCKING_ICON,
    label: title,
    title,
    body: action ? missing : `${missing} ${t('base.setup.delegatedHint')}`,
    ...(action ? { action } : {}),
    ...(secondary ? { secondary } : {}),
  };
}

export function useHubActionNotices(): ActionNoticeSource {
  const { t, locale } = useBaseI18n();
  const router = useRouter();
  const bell = useBellCounters();
  const setup = useLive('base.setup.status', {});

  /** A route the router has (its hash aside): one that falls on the 404 leads nowhere. */
  const reachable = (route: string) => route !== '' && router.resolve(route).name !== 'not-found';
  const answered = (data: unknown, status: string) => data !== undefined || status === 'error';

  const notices = computed<readonly ActionNotice[] | undefined>(() => {
    if (!answered(bell.counters.value, bell.status.value) || !answered(setup.data.value, setup.status.value)) return undefined;
    const counters = (bell.counters.value?.counters ?? []).map((counter) => counterNotice(counter, t, reachable));
    const blocking = blockingNotice(setup.data.value, { t, locale: locale.value }, reachable);
    return blocking ? [...counters, blocking] : counters;
  });
  const failed = computed(() => bell.status.value === 'error' || setup.status.value === 'error');

  return { notices, failed, retry: setup.refresh };
}
