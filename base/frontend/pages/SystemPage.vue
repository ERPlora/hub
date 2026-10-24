<script setup lang="ts">
// System (the old hub's SystemPage): its five tabs in the address hash, the old hub's (BASE-G87; `base/lib/system.ts`):
// Resources (BASE-G88), «Plan and limits» (BASE-G81), Updates (BASE-G89), Failed events (BASE-G91…G94) and Logs
// (BASE-G90). What only who runs the business may read (hub#2519) is asked only for them: anyone else is told who may
// see it, has no Logs tab, and their session never asks the Hub what it would refuse. The old `#backups` lands on
// Settings › Data.
//
// «Plan and limits» (BASE-G81, APP-BASE-4): the live `base.plan.usage`, which the SaaS's photo re-runs — the people
// of the business against the plan's limit (a bar) and the devices in use, with a session open now, against its
// limit (BASE-G57's rule, APP-BASE-3) —, «Close to the limit» with why when every place is taken, and where plans are
// managed (erplora.com; no button: the stores refuse an app that sells, and «Upgrade plan» is in the menu on the web). Memory,
// CPU and database size went with the old process per hub (PLAN-HUB §1a). Only whoever runs the business reads it:
// anyone else is told so, with no useless «Retry».
import { InlineFeedback, StatusPill, UsageMeter } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, type ShellTab, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, watchEffect } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import FailedEvents from '../components/FailedEvents.vue';
import SystemLog from '../components/SystemLog.vue';
import SystemRelease from '../components/SystemRelease.vue';
import SystemResources from '../components/SystemResources.vue';
import { useBaseI18n } from '../lib/i18n';
import { BACKUPS_HASH, BACKUPS_TARGET, type SystemTab, TAB_HASH, tabOf, tabsFor } from '../lib/system';

const { t, locale } = useBaseI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();

/** Who runs the business: the status, Failed events and Logs are theirs (hub#2519). */
const admin = computed(() => session.can('base.administer_hub'));

const TAB_ICON: Record<SystemTab, string> = {
  resources: 'ion:speedometer-outline',
  plan: 'ion:card-outline',
  updates: 'ion:refresh-outline',
  events: 'ion:alert-circle-outline',
  logs: 'ion:list-outline',
};
const tabs = computed<ShellTab[]>(() =>
  tabsFor(admin.value).map((id) => ({
    id,
    label: id === 'plan' ? t('base.systemPlan.tabs.plan') : t(`base.system.tabs.${id}`),
    icon: TAB_ICON[id],
  })),
);
const tab = computed<SystemTab>({
  get: () => tabOf(route.hash, admin.value),
  set: (next) => void router.replace({ path: route.path, hash: TAB_HASH[next] }),
});

// The old `#backups`: its copies live in Settings › Data now.
watchEffect(() => {
  if (route.hash === BACKUPS_HASH) void router.replace(BACKUPS_TARGET);
});

const { data, status, error, refresh } = useLive('base.plan.usage', {});

const usage = computed(() => data.value);
const failed = computed(() => status.value === 'error' && usage.value === undefined);
const denied = computed(() => failed.value && error.value?.code === 'permission_denied');
const peopleLimit = computed(() => (usage.value?.known ? usage.value.people.limit : null));
const devicesLimit = computed(() => (usage.value?.known ? usage.value.devices.limit : null));
/** Every place of the plan taken: what the old hub warned about (the CPU never counted). */
const full = computed(() => peopleLimit.value !== null && (usage.value?.people.used ?? 0) >= peopleLimit.value);
const number = (n: number) => new Intl.NumberFormat(locale.value).format(n);
</script>

<template>
  <AppPage
    v-model:tab="tab"
    :title="t('base.systemPlan.title')"
    :tabs="tabs"
    :tabs-label="t('base.systemPlan.tabs.label')"
  >
    <div
      v-if="tab === 'resources'"
      class="system-tab"
    >
      <SystemResources v-if="admin" />
      <InlineFeedback
        v-else
        tone="info"
        data-testid="system-resources-denied"
      >
        {{ t('base.system.resources.denied') }}
      </InlineFeedback>
    </div>
    <section
      v-else-if="tab === 'updates'"
      class="system-tab system-updates"
      data-testid="system-updates"
    >
      <header class="system-updates-head">
        <h2>{{ t('base.system.updates.heading') }}</h2>
        <SystemRelease v-if="admin" />
      </header>
      <p class="system-plan-hint">
        {{ t('base.system.updates.auto') }}
      </p>
    </section>
    <div
      v-else-if="tab === 'events'"
      class="system-tab"
    >
      <FailedEvents v-if="admin" />
      <InlineFeedback
        v-else
        tone="info"
        data-testid="system-events-denied"
      >
        {{ t('base.system.failed.denied') }}
      </InlineFeedback>
    </div>
    <div
      v-else-if="tab === 'logs'"
      class="system-tab"
    >
      <SystemLog />
    </div>
    <section
      v-else
      class="system-plan"
    >
      <p
        v-if="usage === undefined && !failed"
        class="system-plan-loading"
        data-testid="system-plan-loading"
        role="status"
      >
        {{ t('base.systemPlan.loading') }}
      </p>
      <InlineFeedback
        v-else-if="denied"
        tone="info"
        data-testid="system-plan-denied"
      >
        {{ t('base.systemPlan.denied') }}
      </InlineFeedback>
      <InlineFeedback
        v-else-if="failed"
        tone="danger"
        data-testid="system-plan-error"
        :heading="t('base.systemPlan.error.heading')"
      >
        {{ t('base.systemPlan.error.body') }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="system-plan-retry"
            @click="refresh()"
          >
            {{ t('base.systemPlan.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <template v-else-if="usage">
        <header class="system-plan-head">
          <h2>{{ t('base.systemPlan.heading') }}</h2>
          <StatusPill
            v-if="usage.known"
            data-testid="system-plan-status"
            :tone="full ? 'warning' : 'success'"
            :label="t(full ? 'base.systemPlan.status.close' : 'base.systemPlan.status.within')"
          />
        </header>
        <InlineFeedback
          v-if="!usage.known"
          tone="info"
          data-testid="system-plan-unknown"
        >
          {{ t('base.systemPlan.unknown') }}
        </InlineFeedback>
        <InlineFeedback
          v-if="full"
          tone="warning"
          data-testid="system-plan-full"
          :heading="t('base.systemPlan.full.heading')"
        >
          {{ t('base.systemPlan.full.body') }}
        </InlineFeedback>
        <div class="system-plan-cards">
          <article
            class="system-plan-card"
            data-testid="system-plan-people"
          >
            <UsageMeter
              v-if="peopleLimit !== null"
              :label="t('base.systemPlan.people')"
              :value="usage.people.used"
              :max="peopleLimit"
              :hint="t('base.systemPlan.limitHint')"
              :locale="locale"
            />
            <template v-else>
              <h3>{{ t('base.systemPlan.people') }}</h3>
              <p class="system-plan-figure">
                {{ number(usage.people.used ?? 0) }}
              </p>
              <p
                v-if="usage.known"
                class="system-plan-hint"
              >
                {{ t('base.systemPlan.noLimit') }}
              </p>
            </template>
          </article>
          <article
            class="system-plan-card"
            data-testid="system-plan-devices"
          >
            <!-- In use: those with a session open here, the ones the plan's cap keeps (APP-BASE-3, BASE-G57); its
                 limit in the pill, as the old hub did. -->
            <h3>
              {{ t('base.systemPlan.devices') }}
              <StatusPill
                v-if="usage.known"
                tone="neutral"
                :label="devicesLimit === null ? t('base.systemPlan.noLimit') : t('base.systemPlan.upTo', { n: number(devicesLimit) })"
              />
            </h3>
            <p
              class="system-plan-figure"
              data-testid="system-plan-devices-used"
            >
              {{ number(usage.devices.used ?? 0) }}
            </p>
            <p class="system-plan-hint">
              {{ t('base.systemPlan.devicesInUse') }}
            </p>
          </article>
        </div>
        <p class="system-plan-hint">
          {{ t('base.systemPlan.managed') }}
        </p>
      </template>
    </section>
  </AppPage>
</template>

<style scoped>
.system-tab {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

.system-updates-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.system-updates-head h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.system-plan {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

.system-plan-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.system-plan-head h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.system-plan-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
  gap: 12px;
}

.system-plan-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}

.system-plan-card h3 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.system-plan-figure {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.system-plan-hint,
.system-plan-loading {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}
</style>
