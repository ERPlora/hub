<script setup lang="ts">
// Apps (BASE-G67…G74; the old hub's AppsPage): the business's apps over the live `base.app.list`, which the SaaS's
// photo re-runs (a paid app bought on erplora.com turns up without reloading). Three tabs in the address, the old
// hub's: «My apps» (`/apps`, the apps on, each with «Open»), «Add apps» (`#all`, the whole catalogue with what it
// does, its price and what comes with it) and «Paid» (`#paid`, only what is bought apart). There is no price here:
// a paid app without its right says it needs a subscription and, for whoever runs the business and only on the web,
// links to erplora.com's Store, where it is bought (never inside the Hub: the stores refuse an app that sells).
// Phase 1 has every app the business has a right to on: turning one on or off comes with the activation per hub.
import { DataTable, EmptyState, InlineFeedback, StatusPill, type DataTableAction, type DataTableColumn } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, type ShellTab, useSession, useSurface } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { type AppsTab, appsOfTab, canOpen, comesWith, includedWith, TAB_HASH, tabOf } from '../lib/apps';
import { useBaseI18n } from '../lib/i18n';
import type { AppRow } from '../operations';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();
const { isWeb } = useSurface();

const { data, status, refresh } = useLive('base.app.list', {});

const apps = computed<AppRow[]>(() => data.value?.apps ?? []);
const storeUrl = computed(() => data.value?.store_url ?? '');
const failed = computed(() => status.value === 'error');
const loading = computed(() => data.value === undefined && !failed.value);
/** Who runs the business buys: erplora.com decides the rest by profile. */
const mayBuy = computed(() => isWeb.value && session.can('base.administer_hub') && storeUrl.value !== '');

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
  return t(catalogue.value ? 'base.appsPage.state.installed' : 'base.appsPage.state.on');
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
]);

/** «Open», checked again on the answer now on screen: an app that just stopped being on does not open. */
function onAction({ actionId, row }: { actionId: string; row: AppRow }): void {
  if (actionId !== 'open') return;
  const current = apps.value.find((app) => app.id === row.id);
  if (current && canOpen(current)) void router.push(current.path as string);
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
              :tone="(row as AppRow).state === 'on' ? 'success' : 'warning'"
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
