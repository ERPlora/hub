<script setup lang="ts">
// Apps: the business's apps over the live `base.app.list`, which the SaaS's photo re-runs (a paid app bought on
// erplora.com turns up without reloading). Three tabs in the address: «My apps» (`/apps`), «Add apps» (`#all`, the whole
// catalogue) and «Paid» (`#paid`, only while some app is sold apart). A paid app without its right says it needs a
// subscription and, for whoever runs the business and only on the web, «Upgrade plan» opens erplora.com's Store (the
// stores refuse an app that sells inside the Hub). Whoever runs the business turns an app on or off with its switch: on
// asks first when it brings others it needs; off always asks, naming what goes with it, and one another app on needs says
// which to turn off first; the switch goes back to the real state when nothing changed. A refusal is a notice that stays
// until it is closed or the next change (its reason is often a long sentence a toast took away). The counter says the
// apps on and the plan's chosen ones (hub#1286); at the limit, the notice with the platform's PlanUpgradeLink (BASE-F11).
// An app turned on before its tables exist in the business's database is «Turning on…», its switch waiting, until the
// live list says it is on; one that could not be set up is off, says so and offers «Retry» (`base.app.retry`); both can
// be given up from «⋮». What the server would always refuse is never offered (hub#618, hub#694): the switch cannot move
// and, for whoever runs the business, the row says why; an app off that way is «Not available», not «Off».
import {
  DataTable,
  EmptyState,
  InlineFeedback,
  StatusPill,
  type DataTableColumn,
  type DataTableToggleEvent,
  useConfirm,
} from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, openExternalLink, type ShellTab, toastSuccess, useSession, useSurface } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { sessionChanged } from '../lib/access';
import {
  type AppsTab,
  appsOfTab,
  canOpen,
  canRetry,
  canTurnOff,
  canTurnOn,
  comesWith,
  goesOffWith,
  includedWith,
  offFirst,
  sellsApart,
  TAB_HASH,
  tabOf,
  turnsOnWith,
} from '../lib/apps';
import { appActions, appSwitch } from '../lib/apps-table';
import PlanUpgradeLink from '../components/PlanUpgradeLink.vue';
import { useBaseI18n } from '../lib/i18n';
import type { AppRow } from '../operations/apps';

const { t, locale } = useBaseI18n();
const { confirm } = useConfirm();
const route = useRoute();
const router = useRouter();
const session = useSession();
const { isWeb } = useSurface();

const { data, status, refresh } = useLive('base.app.list', {});
const enable = useCommand('base.app.enable');
const disable = useCommand('base.app.disable');
const retry = useCommand('base.app.retry');

const apps = computed<AppRow[]>(() => data.value?.apps ?? []);
const storeUrl = computed(() => data.value?.store_url ?? '');
const failed = computed(() => status.value === 'error');
const loading = computed(() => data.value === undefined && !failed.value);
/** Who runs the business buys: erplora.com decides the rest by profile. */
const mayBuy = computed(() => isWeb.value && session.can('base.administer_hub') && storeUrl.value !== '');
/** Who runs the business turns apps on and off. */
const mayManage = computed(() => session.can('base.administer_hub'));
/** The plan's page on erplora.com, only on the web (the Hub never sells inside the installed app). */
const planUrl = computed(() => (isWeb.value && mayManage.value ? (data.value?.plan_url ?? '') : ''));
/** The app being turned on or off: only its button waits, and no other starts meanwhile. */
const pending = ref<string | null>(null);
/** The plan's limit the last «Turn on» hit; cleared by the next change. */
const limitHit = ref<number | null>(null);
/** Why the last change was refused; on screen until it is closed or the next change. */
const refusal = ref<string | null>(null);

/** The apps turned on, as «My apps» lists them (those born on and those brought along included), and, against the
 *  plan's limit, the ones the business chose (`enabled`: all the limit counts, hub#1286). */
const counter = computed(() => {
  const answer = data.value;
  if (!answer) return '';
  const on = appsOfTab(apps.value, 'mine').length;
  if (answer.max_apps === null) return t('base.appsPage.counter.unlimited', { on, n: on });
  return t('base.appsPage.counter.limited', { on, n: on, chosen: answer.enabled, max: answer.max_apps });
});

/** Some app is sold apart (none is while every app comes with every plan): only then «Paid» and «Price». */
const paid = computed(() => sellsApart(apps.value));

const tabs = computed<ShellTab[]>(() => [
  { id: 'mine', label: t('base.appsPage.tabs.mine'), icon: 'ion:cube-outline' },
  { id: 'all', label: t('base.appsPage.tabs.all'), icon: 'ion:storefront-outline' },
  ...(paid.value ? [{ id: 'paid', label: t('base.appsPage.tabs.paid'), icon: 'ion:wallet-outline' }] : []),
]);
const tab = computed<AppsTab>({
  get: () => tabOf(route.hash, paid.value),
  set: (next) => void router.replace({ path: route.path, hash: TAB_HASH[next] }),
});
const catalogue = computed(() => tab.value !== 'mine');
const rows = computed(() => appsOfTab(apps.value, tab.value));

const categories = computed(() =>
  [...new Map(apps.value.map((app) => [app.category, app.category_label])).entries()]
    .sort((a, b) => a[1].localeCompare(b[1]))
    .map(([value, label]) => ({ value, label })),
);

function stateLabel(app: AppRow): string {
  if (app.state === 'blocked') return t('base.appsPage.state.blocked');
  if (app.state === 'off') return t(app.refusal ? 'base.appsPage.state.unavailable' : 'base.appsPage.state.off');
  if (app.state === 'creating') return t('base.appsPage.state.creating');
  if (app.state === 'failed') return t('base.appsPage.state.failed');
  return t('base.appsPage.state.on');
}

function stateTone(app: AppRow): 'success' | 'info' | 'warning' | 'danger' | 'neutral' {
  if (app.state === 'on') return 'success';
  if (app.state === 'creating') return 'info';
  if (app.state === 'failed') return 'danger';
  return app.state === 'off' ? 'neutral' : 'warning';
}

function priceLabel(app: AppRow): string {
  if (app.right === 'required') {
    const apps_ = includedWith(app, apps.value);
    if (apps_.length) return t('base.appsPage.right.required', { apps: apps_.join(', ') });
    return t('base.appsPage.right.missing');
  }
  return t(`base.appsPage.right.${app.right}`);
}

/** What a row the business's country requires on says beside its state, for everyone (hub#997): the reason it is not
 *  turned off, under it, only for whoever runs the business. */
const mandatoryLabel = computed(() => t('base.appsPage.mandatory', { country: data.value?.country_name ?? '' }));

/** What the table offers on each row, for who reads it and the change on its way. */
const tableState = computed(() => ({ t, mayManage: mayManage.value, mayBuy: mayBuy.value, pending: pending.value }));

/** Whoever reads a row's reason gets a column with room for it: a sentence, not a strip of a dozen short lines. */
const statesSayWhy = computed(() => mayManage.value && apps.value.some((app) => app.refusal));

/** «Add apps» filters by state; «My apps» lists only what is on. */
const stateFilter = computed(() =>
  catalogue.value
    ? {
        type: 'select' as const,
        options: (['on', 'off', 'blocked', 'creating', 'failed'] as const).map((value) => ({
          value,
          label: t(`base.appsPage.state.${value}`),
        })),
      }
    : undefined,
);

const columns = computed<DataTableColumn<AppRow>[]>(() => [
  {
    key: 'name',
    label: t('base.appsPage.columns.app'),
    priority: 'high',
    identity: { icon: (row) => row.icon, subtitle: (row) => priceLabel(row), testid: 'apps-plan' },
  },
  {
    key: 'category',
    label: t('base.appsPage.columns.category'),
    cardIcon: 'ion:pricetag-outline',
    format: (_, row) => row.category_label,
    filter: { type: 'select', options: categories.value },
  },
  ...(catalogue.value
    ? ([
        { key: 'summary', label: t('base.appsPage.columns.summary'), priority: 'low', width: 'minmax(12rem, 2fr)' },
        ...(paid.value
          ? ([
              {
                key: 'right',
                label: t('base.appsPage.columns.price'),
                cell: 'price',
                cardIcon: 'ion:wallet-outline',
                sortValue: (row) => priceLabel(row),
              },
            ] satisfies DataTableColumn<AppRow>[])
          : []),
        {
          key: 'requires',
          label: t('base.appsPage.columns.comesWith'),
          priority: 'low',
          cardIcon: 'ion:cube-outline',
          format: (_, row) => comesWith(row, apps.value).join(', ') || '—',
        },
      ] satisfies DataTableColumn<AppRow>[])
    : []),
  {
    key: 'state',
    label: t('base.appsPage.columns.state'),
    cell: 'state',
    toggle: appSwitch(tableState.value),
    ...(statesSayWhy.value ? { width: 'minmax(15rem, 1.5fr)' } : {}),
    sortValue: (row) => stateLabel(row),
    filter: stateFilter.value,
  },
]);

const actions = computed(() => appActions(tableState.value));

/** The row's actions, checked again on the answer now on screen: an app that just changed is not misread. */
function onAction({ actionId, row }: { actionId: string; row: AppRow }): void {
  const current = apps.value.find((app) => app.id === row.id);
  if (!current) return;
  if (actionId === 'open' && canOpen(current)) void router.push(current.path as string);
  if (actionId === 'plans' && mayBuy.value) openStore();
  if (actionId === 'off' && pending.value === null) void toggle(current);
  if (actionId === 'retry' && pending.value === null && canRetry(current)) void change('retry', current);
}

/** The Store, opened as its link would be: a new tab, or the system browser in the installed app. */
function openStore(): void {
  const link = Object.assign(document.createElement('a'), { href: storeUrl.value, rel: 'noopener' });
  link.target = '_blank';
  link.addEventListener('click', (event) => openExternalLink(storeUrl.value, event));
  document.body.append(link);
  link.click();
  link.remove();
}

/** The switch moved: on retries a failed app or turns one on; off turns it off. Nothing while another change is sent. */
function onSwitch({ row, checked }: DataTableToggleEvent<AppRow>): void {
  const current = apps.value.find((app) => app.id === row.id);
  if (!current || pending.value !== null) return;
  if (checked && canRetry(current)) void change('retry', current);
  else if (checked ? canTurnOn(current) : canTurnOff(current)) void toggle(current);
}

/** «A», «A and B», «A, B and C», in the screen's language. */
function listOf(names: readonly string[]): string {
  return new Intl.ListFormat(locale.value, { style: 'long', type: 'conjunction' }).format(names);
}

async function toggle(app: AppRow): Promise<void> {
  if (canTurnOff(app)) {
    const first = offFirst(app, apps.value);
    if (first.length) {
      refusal.value = t('base.appsPage.offFirst', { apps: listOf(first) });
      return;
    }
    const along = goesOffWith(app, apps.value);
    const message = [
      t('base.appsPage.confirmOff.message'),
      along.length ? t('base.appsPage.confirmOff.along', { apps: listOf(along), app: app.name, n: along.length }) : '',
    ].filter(Boolean);
    const yes = await confirm({
      title: t('base.appsPage.confirmOff.title', { app: app.name }),
      message: message.join(' '),
      confirmLabel: t('base.appsPage.confirmOff.confirm'),
      cancelLabel: t('base.appsPage.confirmOff.cancel'),
      tone: 'danger',
    });
    if (yes) await change('disable', app);
    return;
  }
  if (!canTurnOn(app)) return;
  const along = turnsOnWith(app, apps.value);
  if (along.length) {
    const yes = await confirm({
      title: t('base.appsPage.confirmOn.title', { app: app.name }),
      message: t('base.appsPage.confirmOn.message', { app: app.name, apps: listOf(along), n: along.length }),
      confirmLabel: t('base.appsPage.confirmOn.confirm'),
      cancelLabel: t('base.appsPage.confirmOn.cancel'),
      tone: 'primary',
    });
    if (!yes) return;
  }
  await change('enable', app);
}

const COMMANDS = { enable, disable, retry };

async function change(kind: 'enable' | 'disable' | 'retry', app: AppRow): Promise<void> {
  pending.value = app.id;
  limitHit.value = null;
  refusal.value = null;
  try {
    const answer = await COMMANDS[kind].run({ app: app.id });
    const along = answer.along.map((other) => other.name);
    const on = kind !== 'disable';
    // «creating»: its tables are being made; its row says when it is on (the live list).
    const done = answer.state === 'creating' ? 'base.appsPage.turningOn' : on ? 'base.appsPage.turnedOn' : 'base.appsPage.turnedOff';
    const said = [t(done, { app: app.name })];
    if (along.length) said.push(t(on ? 'base.appsPage.alsoOn' : 'base.appsPage.alsoOff', { apps: listOf(along) }));
    toastSuccess(said.join(' '));
    // The menu is the session's: read it again (the other screens of the business follow the live list).
    sessionChanged();
  } catch (error) {
    refused(error as ApiError | undefined, app);
  } finally {
    pending.value = null;
  }
}

/** Why the server said no, from its code: the limit (the notice), another app needs it, the app's own reason. */
function refused(error: ApiError | undefined, app: AppRow): void {
  if (error?.code === 'base.app_limit_reached') {
    limitHit.value = Number(error.details.max_apps) || data.value?.max_apps || 0;
    return;
  }
  if (error?.code === 'base.app_required') {
    const ids = Array.isArray(error.details.required_by) ? (error.details.required_by as string[]) : [];
    const named = offFirst({ ...app, required_by: ids }, apps.value);
    const names = named.length ? named : ids.map((id) => apps.value.find((row) => row.id === id)?.name ?? id);
    refusal.value = t('base.appsPage.offFirst', { apps: listOf(names) });
    return;
  }
  if (error?.code === 'base.app_vetoed') {
    refusal.value = error.message;
    return;
  }
  refusal.value = t('base.appsPage.changeFailed', { app: app.name, reason: error?.message ?? '' });
}

const searchPlaceholder = computed(() => t(`base.appsPage.search.${tab.value}`));
const emptyHeading = computed(() => t(`base.appsPage.empty.${tab.value}`));
</script>

<template>
  <AppPage
    v-model:tab="tab"
    :title="t('base.appsPage.title')"
    :tabs="tabs"
    :tabs-label="t('base.appsPage.tabs.label')"
    content-layout="fill"
  >
    <div class="page-fill apps-page">
      <p
        v-if="counter"
        class="apps-counter"
        data-testid="apps-counter"
      >
        {{ counter }}
      </p>
      <InlineFeedback
        v-if="limitHit !== null"
        tone="warning"
        data-testid="apps-limit"
        :heading="t('base.appsPage.limit.heading')"
      >
        {{ t('base.appsPage.limit.body', { max: limitHit, n: limitHit }) }}
        <template
          v-if="planUrl"
          #actions
        >
          <PlanUpgradeLink
            class="apps-limit-upgrade"
            data-testid="apps-limit-upgrade"
            :url="planUrl"
          />
        </template>
      </InlineFeedback>
      <InlineFeedback
        v-if="refusal !== null"
        tone="danger"
        dismissible
        data-testid="apps-refused"
        :heading="t('base.appsPage.refused')"
        @dismiss="refusal = null"
      >
        {{ refusal }}
      </InlineFeedback>
      <InlineFeedback
        v-if="failed"
        tone="danger"
        data-testid="apps-error"
        :heading="t('base.appsPage.loadError')"
      >
        {{ t('base.appsPage.loadErrorBody') }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="apps-retry"
            @click="refresh()"
          >
            {{ t('base.appsPage.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <DataTable
        v-if="!failed || apps.length > 0"
        :key="tab"
        testid="apps"
        fill
        searchable
        filterable
        column-picker
        :search-keys="['name', 'summary', 'category_label']"
        :search-placeholder="searchPlaceholder"
        :views="['table', 'cards']"
        :card-title="(row: AppRow) => row.name"
        card-title-column="name"
        :rows="rows"
        :columns="columns"
        :actions="actions"
        :loading="loading"
        :entity-label="{ one: t('base.appsPage.entity.one'), many: t('base.appsPage.entity.many') }"
        :labels="{ loading: t(catalogue ? 'base.appsPage.loadingCatalogue' : 'base.appsPage.loading') }"
        @action="onAction"
        @toggle="onSwitch"
      >
        <template #price="{ row }">
          <span data-testid="apps-price">{{ priceLabel(row as AppRow) }}</span>
        </template>
        <template #state="{ row }">
          <StatusPill
            data-testid="apps-state"
            :tone="stateTone(row as AppRow)"
            :label="stateLabel(row as AppRow)"
          />
          <StatusPill
            v-if="(row as AppRow).mandatory"
            data-testid="apps-mandatory"
            tone="info"
            :label="mandatoryLabel"
          />
        </template>
        <template #empty>
          <EmptyState
            data-testid="apps-empty"
            icon="ion:cube-outline"
            :heading="rows.length ? t('base.appsPage.noResults') : emptyHeading"
          />
        </template>
      </DataTable>
    </div>
  </AppPage>
</template>

<style scoped>
.apps-counter {
  margin: 0 0 8px;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
  font-weight: 600;
}

.apps-limit-upgrade {
  color: var(--ion-color-primary);
  font-weight: 600;
}
</style>
