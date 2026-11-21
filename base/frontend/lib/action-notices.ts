// The hub's source of the action center (`createShell({ actionNotices })`): every counter of the bell above zero and,
// while a step blocks invoicing, «You cannot issue invoices yet», as data. The shell paints them; no screen does.
// A counter's gravity and words come from the server, already in the person's language. A counter that leads to
// erplora.com (the plan's unpaid invoice) opens it outside the hub, and only on the web: what is paid, like what sells,
// is never offered inside the installed app.
import { useLive } from '@erplora/ui/sdk';
import {
  type ActionNotice,
  type ActionNoticeSource,
  type NoticeAction,
  type NoticeDestination,
  useSurface,
} from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

import type { SetupItem, SetupStatus } from '../operations/home';
import type { BellCounter } from '../operations-bell';
import { useBellCounters } from './bell-counters';
import { blockingItems } from './home';
import { useBaseI18n } from './i18n';

type Translate = ReturnType<typeof useBaseI18n>['t'];

/** The ⛔ steps known today and the label of their button. */
const STEP_ACTIONS: Record<string, string> = {
  'invoice.business_identity': 'base.blocking.steps.businessIdentity',
  'verifactu.sending_route': 'base.blocking.steps.verifactu',
};

const BLOCKING_ICON = 'ion:alert-circle-outline';
/** A route that is an address of another site. */
const OUTSIDE = /^https?:\/\//;

/** Where a counter's button goes: a screen of this hub it has, or an address outside it on the web; none otherwise. */
type Destination = (route: string) => NoticeDestination | undefined;

function counterNotice(counter: BellCounter, destination: Destination): ActionNotice {
  const goes = destination(counter.route);
  return {
    id: counter.key,
    severity: counter.severity,
    icon: counter.icon,
    label: counter.title,
    title: counter.title,
    ...(counter.body ? { body: counter.body } : {}),
    count: counter.count,
    ...(counter.due ? { due: { at: counter.due } } : {}),
    ...(goes ? { action: { label: counter.action_label, ...goes } } : {}),
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
  const { isWeb } = useSurface();
  const bell = useBellCounters();
  const setup = useLive('base.setup.status', {});

  /** A route the router has (its hash aside): one that falls on the 404 leads nowhere. */
  const reachable = (route: string) => route !== '' && router.resolve(route).name !== 'not-found';
  const answered = (data: unknown, status: string) => data !== undefined || status === 'error';
  const destination: Destination = (route) => {
    if (OUTSIDE.test(route)) return isWeb.value ? { href: route } : undefined;
    return reachable(route) ? { to: route } : undefined;
  };

  const notices = computed<readonly ActionNotice[] | undefined>(() => {
    if (!answered(bell.counters.value, bell.status.value) || !answered(setup.data.value, setup.status.value)) return undefined;
    const counters = (bell.counters.value?.counters ?? []).map((counter) => counterNotice(counter, destination));
    const blocking = blockingNotice(setup.data.value, { t, locale: locale.value }, reachable);
    return blocking ? [...counters, blocking] : counters;
  });
  const failed = computed(() => bell.status.value === 'error' || setup.status.value === 'error');

  return { notices, failed, retry: setup.refresh };
}
