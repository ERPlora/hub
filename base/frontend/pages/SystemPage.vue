<script setup lang="ts">
// System (the old hub's SystemPage), today with its «Plan and limits» (BASE-G81, tab `#plan`): the live
// `base.plan.usage`, which the SaaS's photo re-runs — the people of the business against the plan's limit (a bar)
// and the devices' limit (the Hub keeps no count of them yet: «n/a», never a made-up figure) —, «Close to the limit»
// with why when every place is taken, and where plans are managed (erplora.com; no button: the stores refuse an app
// that sells, and «Upgrade plan» is in the menu on the web). Memory, CPU and database size went with the old process
// per hub (PLAN-HUB §1a). Only whoever runs the business reads it: anyone else is told so, with no useless «Retry». The
// other sections of System come with its own part; each will be a tab here, in the address hash.
import { InlineFeedback, StatusPill, UsageMeter } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, type ShellTab } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../lib/i18n';

const { t, locale } = useBaseI18n();

const { data, status, error, refresh } = useLive('base.plan.usage', {});

const tabs = computed<ShellTab[]>(() => [{ id: 'plan', label: t('base.systemPlan.tabs.plan'), icon: 'ion:card-outline' }]);
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
    tab="plan"
    :title="t('base.systemPlan.title')"
    :tabs="tabs"
    :tabs-label="t('base.systemPlan.tabs.label')"
  >
    <section class="system-plan">
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
