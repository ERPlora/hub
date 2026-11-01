<script setup lang="ts">
// «Why it does not open» (BASE-G132, G134; the old hub's ModuleView states): mounted by the app gate (`lib/app-gate.ts`)
// in the address of a screen whose app `base.session.me` gives `off`. Which app it is comes from the address (the
// app's own route, `meta.app`); why, from the live `base.app.list`: a paid app without its right gets «Subscription
// needed» — its data is safe and comes back once it is bought on erplora.com (the Store's link only for whoever runs
// the business and only on the web: the Hub never sells) —; an app the business does not have says so; one whose tables
// its own database is getting (S3) says it opens in a moment, and one that could not be set up leads to Apps, where it
// is tried again. Bought
// meanwhile (the SaaS's photo re-runs the list), it offers to open the app with a full load, which brings the
// session (a snapshot of the page load) up to date. A failed check says so; it never makes up a reason. The Store's
// link goes the Hub's one way out, `openExternalLink` (gh:hub#439: the installed app opens nothing on `_blank`).
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, openExternalLink, useSession, useSurface } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useBaseI18n } from '../lib/i18n';
import type { AppRow } from '../operations';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();
const { isWeb } = useSurface();

const { data, status, refresh } = useLive('base.app.list', {});

/** The app whose screen the address names: its own route, the first that matches it. */
const appId = computed(() => router.resolve(route.fullPath).meta.app);
const row = computed<AppRow | undefined>(() => data.value?.apps.find((app) => app.id === appId.value));
const storeUrl = computed(() => data.value?.store_url ?? '');
const failed = computed(() => status.value === 'error' && data.value === undefined);
const checking = computed(() => data.value === undefined && !failed.value);
const mayBuy = computed(() => isWeb.value && session.can('base.administer_hub') && storeUrl.value !== '');
const title = computed(() => row.value?.name ?? t('base.appsPage.title'));

function toApps(): void {
  void router.push({ path: '/apps', hash: '#all' });
}

/** «My apps», where an app that could not be set up is tried again. */
function toMyApps(): void {
  void router.push({ path: '/apps' });
}
</script>

<template>
  <AppPage :title="title">
    <div class="app-blocked">
      <p
        v-if="checking"
        class="app-blocked-checking"
        data-testid="app-blocked-checking"
        role="status"
      >
        {{ t('base.appBlocked.checking') }}
      </p>
      <InlineFeedback
        v-else-if="failed"
        tone="danger"
        data-testid="app-blocked-error"
        :heading="t('base.appBlocked.error.heading')"
      >
        {{ t('base.appBlocked.error.body') }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="app-blocked-retry"
            @click="refresh()"
          >
            {{ t('base.appsPage.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <EmptyState
        v-else-if="row?.state === 'on'"
        data-testid="app-blocked-ready"
        icon="ion:checkmark-circle-outline"
        :heading="t('base.appBlocked.ready.heading', { app: row.name })"
        :message="t('base.appBlocked.ready.body')"
      >
        <template #action>
          <a
            class="app-blocked-button"
            data-testid="app-blocked-open"
            :href="route.fullPath"
          >{{ t('base.appBlocked.ready.open', { app: row.name }) }}</a>
        </template>
      </EmptyState>
      <EmptyState
        v-else-if="row?.state === 'creating'"
        data-testid="app-blocked-creating"
        icon="ion:time-outline"
        :heading="t('base.appBlocked.creating.heading', { app: row.name })"
        :message="t('base.appBlocked.creating.body')"
      />
      <EmptyState
        v-else-if="row?.state === 'failed'"
        data-testid="app-blocked-failed"
        icon="ion:alert-circle-outline"
        :heading="t('base.appBlocked.failed.heading', { app: row.name })"
        :message="t('base.appBlocked.failed.body')"
      >
        <template #action>
          <ion-button
            fill="outline"
            data-testid="app-blocked-to-apps"
            @click="toMyApps"
          >
            {{ t('base.appBlocked.toApps') }}
          </ion-button>
        </template>
      </EmptyState>
      <EmptyState
        v-else-if="row?.state === 'blocked'"
        data-testid="app-blocked-subscription"
        icon="ion:lock-closed-outline"
        :heading="t('base.appBlocked.subscription.heading')"
        :message="t('base.appBlocked.subscription.body', { app: row.name })"
      >
        <p
          v-if="!mayBuy"
          class="app-blocked-where"
        >
          {{ t('base.appsPage.buyWhere') }}
        </p>
        <template #action>
          <div class="app-blocked-actions">
            <a
              v-if="mayBuy"
              class="app-blocked-button"
              data-testid="app-blocked-buy"
              :href="storeUrl"
              target="_blank"
              rel="noopener"
              @click="openExternalLink(storeUrl, $event)"
            >{{ t('base.appsPage.buy') }}</a>
            <ion-button
              fill="outline"
              data-testid="app-blocked-to-apps"
              @click="toApps"
            >
              {{ t('base.appBlocked.toApps') }}
            </ion-button>
          </div>
        </template>
      </EmptyState>
      <EmptyState
        v-else
        data-testid="app-blocked-missing"
        icon="ion:cube-outline"
        :heading="t('base.appBlocked.missing.heading')"
        :message="t('base.appBlocked.missing.body')"
      >
        <template #action>
          <ion-button
            fill="outline"
            data-testid="app-blocked-to-apps"
            @click="toApps"
          >
            {{ t('base.appBlocked.toApps') }}
          </ion-button>
        </template>
      </EmptyState>
    </div>
  </AppPage>
</template>

<style scoped>
.app-blocked {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 60%;
  padding: 24px 16px;
}

.app-blocked-checking {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  text-align: center;
}

.app-blocked-where {
  margin: 8px 0 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.app-blocked-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.app-blocked-button {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 0 16px;
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-color-primary);
  color: var(--ion-color-primary-contrast, #fff);
  font-weight: 600;
  text-decoration: none;
}
</style>
