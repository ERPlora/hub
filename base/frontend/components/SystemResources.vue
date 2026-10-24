<script setup lang="ts">
// System › Resources (BASE-G88, G45; the old hub's SystemPage `#resources`, HUB_SHELL-F136), for who runs the business
// (the page tells anyone else who may see it): the live `base.system.status` — «Cloud resources» and the database the
// business is on (phase 1: the one every business shares) — and, instead of CPU, memory and connections, why there are
// none: one service runs every business, so no figure is this hub's own (PLAN-HUB §1a). Never a made-up zero.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();

const { data, status, refresh } = useLive('base.system.status', {});

const failed = computed(() => status.value === 'error' && data.value === undefined);
</script>

<template>
  <section class="system-resources">
    <header class="system-resources-head">
      <h2>{{ t('base.system.resources.heading') }}</h2>
      <StatusPill
        tone="info"
        :dot="false"
        data-testid="system-resources-cloud"
        :label="t('base.system.resources.cloud')"
      />
    </header>
    <p
      v-if="data === undefined && !failed"
      class="system-resources-muted"
      data-testid="system-resources-loading"
      role="status"
    >
      {{ t('base.system.resources.loading') }}
    </p>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      data-testid="system-resources-error"
      :heading="t('base.system.error.heading')"
    >
      {{ t('base.system.error.body') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="system-resources-retry"
          @click="refresh()"
        >
          {{ t('base.system.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <template v-else-if="data">
      <article
        class="system-resources-card"
        data-testid="system-resources-database"
      >
        <HubIcon
          class="system-resources-icon"
          name="ion:cube-outline"
          aria-hidden="true"
        />
        <span class="system-resources-label">{{ t('base.system.resources.database') }}</span>
        <strong class="system-resources-engine">{{ t('base.system.resources.engine') }}</strong>
        <span class="system-resources-muted">
          {{ t(data.shared_database ? 'base.system.resources.shared' : 'base.system.resources.own') }}
        </span>
      </article>
      <InlineFeedback
        tone="info"
        data-testid="system-resources-not-measured"
      >
        {{ t('base.system.resources.notMeasured') }}
      </InlineFeedback>
    </template>
  </section>
</template>

<style scoped>
.system-resources {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.system-resources-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.system-resources-head h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.system-resources-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  max-width: 22rem;
  padding: 20px 16px;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  text-align: center;
}

.system-resources-icon {
  width: 24px;
  height: 24px;
  color: var(--ion-color-medium, #92949c);
}

.system-resources-label {
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.system-resources-engine {
  font-size: 1.5rem;
}

.system-resources-muted {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}
</style>
