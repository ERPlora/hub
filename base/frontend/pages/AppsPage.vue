<script setup lang="ts">
// Apps (BASE-G67…G74; the old hub's AppsPage): the business's apps over the live `base.app.list`, which the SaaS's
// photo re-runs (a paid app bought on erplora.com turns up without reloading). Three tabs in the address, the old
// hub's: «My apps» (`/apps`, the apps on, each with «Open»), «Add apps» (`#all`, the whole catalogue with what it
// does, its price and what comes with it) and «Paid» (`#paid`, only what is bought apart). There is no price here:
// a paid app without its right says it needs a subscription and, for whoever runs the business and only on the web,
// links to erplora.com's Store, where it is bought (never inside the Hub: the stores refuse an app that sells).
// Whoever runs the business turns an app on or off (PLAN-HUB §9; BASE-F18, F19, F23–F25): «Turn on» asks first when
// it brings others it needs, naming them; «Turn off» always asks, naming what goes with it, and one another app on
// needs says which to turn off first. A refusal (another app needs it, the app's own reason, any other failure) is a
// notice that stays until it is closed or the next change: its reason is often a long sentence of what to do first,
// which a toast took away before it could be read (hub#2594). The counter says how many of the plan's apps are on
// (`max_apps`; what came along does not count); at the limit, the notice with «Upgrade plan» (erplora.com's plans,
// only on the web). The menu of this screen is read again after each change; the other screens of the business
// follow the live list (AppsFollower).
import {
  DataTable,
  EmptyState,
  InlineFeedback,
  StatusPill,
  type DataTableAction,
  type DataTableColumn,
  useConfirm,
} from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, type ShellTab, toastSuccess, useSession, useSurface } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { sessionChanged } from '../lib/access';
import {
  type AppsTab,
  appsOfTab,
  canOpen,
  canTurnOff,
  canTurnOn,
  comesWith,
  goesOffWith,
  includedWith,
  offFirst,
  TAB_HASH,
  tabOf,
  turnsOnWith,
} from '../lib/apps';
import { useBaseI18n } from '../lib/i18n';
import type { AppRow } from '../operations';

const { t, locale } = useBaseI18n();
const { confirm } = useConfirm();
const route = useRoute();
const router = useRouter();
const session = useSession();
const { isWeb } = useSurface();

const { data, status, refresh } = useLive('base.app.list', {});
const enable = useCommand('base.app.enable');
const disable = useCommand('base.app.disable');

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
/** Why the last change was refused; on screen until it is closed or the next change (hub#2594). */
const refusal = ref<string | null>(null);

const counter = computed(() => {
  const answer = data.value;
  if (!answer) return '';
  if (answer.max_apps === null) return t('base.appsPage.counter.unlimited', { enabled: answer.enabled, n: answer.enabled });
  return t('base.appsPage.counter.limited', { enabled: answer.enabled, max: answer.max_apps });
});

const tabs = computed<ShellTab[]>(() => [
  { id: 'mine', label: t('base.appsPage.tabs.mine'), icon: 'ion:cube-outline' },
  { id: 'all', label: t('base.appsPage.tabs.all'), icon: 'ion:storefront-outline' },
  { id: 'paid', label: t('base.appsPage.tabs.paid'), icon: 'ion:wallet-outline' },
]);
const tab = computed<AppsTab>({
  get: () => tabOf(route.hash),
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
  if (app.state === 'off') return t('base.appsPage.state.off');
  return t(catalogue.value ? 'base.appsPage.state.installed' : 'base.appsPage.state.on');
}

function stateTone(app: AppRow): 'success' | 'warning' | 'neutral' {
  if (app.state === 'on') return 'success';
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

const columns = computed<DataTableColumn<AppRow>[]>(() => [
  { key: 'name', label: t('base.appsPage.columns.app'), cell: 'app', priority: 'high' },
  {
    key: 'category',
    label: t('base.appsPage.columns.category'),
    format: (_, row) => row.category_label,
    filter: { type: 'select', options: categories.value },
  },
  ...(catalogue.value
    ? ([
        { key: 'summary', label: t('base.appsPage.columns.summary'), priority: 'low', width: 'minmax(12rem, 2fr)' },
        {
          key: 'right',
          label: t('base.appsPage.columns.price'),
          cell: 'price',
          sortValue: (row) => priceLabel(row),
        },
        {
          key: 'requires',
          label: t('base.appsPage.columns.comesWith'),
          priority: 'low',
          format: (_, row) => comesWith(row, apps.value).join(', ') || '—',
        },
      ] satisfies DataTableColumn<AppRow>[])
    : []),
  {
    key: 'state',
    label: t('base.appsPage.columns.state'),
    cell: 'state',
    sortValue: (row) => stateLabel(row),
    filter: catalogue.value
      ? {
          type: 'select',
          options: [
            { value: 'on', label: t('base.appsPage.state.installed') },
            { value: 'off', label: t('base.appsPage.state.off') },
            { value: 'blocked', label: t('base.appsPage.state.blocked') },
          ],
        }
      : undefined,
  },
]);

const actions = computed<DataTableAction<AppRow>[]>(() => [
  {
    id: 'open',
    label: t('base.appsPage.open'),
    icon: 'ion:open-outline',
    color: 'primary',
    pinned: true,
    hidden: (row) => !canOpen(row),
  },
  {
    id: 'toggle',
    // A text button: what it does is its label («Turn on», «Turn off»).
    label: (row) => t(canTurnOn(row) ? 'base.appsPage.toggle.on' : 'base.appsPage.toggle.off'),
    color: 'primary',
    hidden: (row) => !mayManage.value || !(canTurnOn(row) || canTurnOff(row)),
    loading: (row) => pending.value === row.id,
    disabled: (row) => pending.value !== null && pending.value !== row.id,
  },
]);

/** «Open» and «Turn on/off», checked again on the answer now on screen: an app that just changed is not misread. */
function onAction({ actionId, row }: { actionId: string; row: AppRow }): void {
  const current = apps.value.find((app) => app.id === row.id);
  if (!current) return;
  if (actionId === 'open' && canOpen(current)) void router.push(current.path as string);
  if (actionId === 'toggle' && pending.value === null) void toggle(current);
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

async function change(kind: 'enable' | 'disable', app: AppRow): Promise<void> {
  pending.value = app.id;
  limitHit.value = null;
  refusal.value = null;
  try {
    const answer = await (kind === 'enable' ? enable : disable).run({ app: app.id });
    const along = answer.along.map((other) => other.name);
    const said = [t(kind === 'enable' ? 'base.appsPage.turnedOn' : 'base.appsPage.turnedOff', { app: app.name })];
    if (along.length) said.push(t(kind === 'enable' ? 'base.appsPage.alsoOn' : 'base.appsPage.alsoOff', { apps: listOf(along) }));
    void toastSuccess(said.join(' '));
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
          <a
            class="apps-limit-upgrade"
            data-testid="apps-limit-upgrade"
            :href="planUrl"
            target="_blank"
            rel="noopener"
          >{{ t('base.plan.upgrade') }}</a>
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
        :rows="rows"
        :columns="columns"
        :actions="actions"
        :loading="loading"
        :entity-label="{ one: t('base.appsPage.entity.one'), many: t('base.appsPage.entity.many') }"
        :labels="{ loading: t(catalogue ? 'base.appsPage.loadingCatalogue' : 'base.appsPage.loading') }"
        @action="onAction"
      >
        <template #app="{ row }">
          <span class="apps-name">
            <HubIcon
              class="apps-icon"
              :name="(row as AppRow).icon"
            />
            <span>{{ (row as AppRow).name }}</span>
          </span>
        </template>
        <template #price="{ row }">
          <span data-testid="apps-price">{{ priceLabel(row as AppRow) }}</span>
        </template>
        <template #state="{ row }">
          <span class="apps-state">
            <StatusPill
              data-testid="apps-state"
              :tone="stateTone(row as AppRow)"
              :label="stateLabel(row as AppRow)"
            />
            <template v-if="(row as AppRow).state === 'blocked'">
              <a
                v-if="mayBuy"
                class="apps-buy"
                data-testid="apps-buy"
                :href="storeUrl"
                target="_blank"
                rel="noopener"
              >{{ t('base.appsPage.buy') }}</a>
              <span
                v-else
                class="apps-buy-where"
              >{{ t('base.appsPage.buyWhere') }}</span>
            </template>
          </span>
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
.apps-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-weight: 600;
}

.apps-icon {
  flex: none;
  width: 20px;
  height: 20px;
  color: var(--ion-color-primary);
}

.apps-state {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
}

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

.apps-buy {
  color: var(--ion-color-primary);
  font-size: 0.875rem;
  font-weight: 600;
}

.apps-buy-where {
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.8125rem;
}
</style>
