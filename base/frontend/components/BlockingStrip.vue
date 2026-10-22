<script setup lang="ts">
// The blocking strip over every screen (hub#374; BASE-G22): while a ⛔ step is pending (`blocking_pending` of
// `base.setup.status`, live) the invoice is refused, so it says the CONSEQUENCE — never «error»: nothing is
// broken, something is missing — and names each missing step with its way in. On the Home's «Summary» it stands
// down: the checklist there says strictly more, a screenful below; on «Activity» (`/#actividad`) it is back.
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import type { SetupItem } from '../operations';
import { blockingItems } from '../lib/home';

/** The hash of the Home's «Activity» tab. */
const ACTIVITY_HASH = '#actividad';

const route = useRoute();
const router = useRouter();
const { data } = useLive('base.setup.status', {});

const items = computed(() => blockingItems(data.value));
const onSummary = computed(() => route.path === '/' && route.hash !== ACTIVITY_HASH);
const shown = computed(() => items.value.length > 0 && !onSummary.value);

const reachable = (path: string) => path !== '' && router.resolve(path).name !== 'not-found';
const canConfigure = (item: SetupItem) => item.actionable && reachable(item.route);
</script>

<template>
  <div
    v-if="shown"
    class="blocking-strip"
    role="alert"
    data-testid="blocking-strip"
  >
    <HubIcon
      class="blocking-strip-icon"
      name="ion:alert-circle-outline"
    />
    <div class="blocking-strip-body">
      <p class="blocking-strip-title">
        {{ $t('base.blocking.title') }}
      </p>
      <p class="blocking-strip-text">
        {{ $t('base.blocking.body') }}
      </p>
      <ul class="blocking-strip-items">
        <li
          v-for="item in items"
          :key="item.key"
          class="blocking-strip-item"
          data-testid="blocking-item"
        >
          <HubIcon :name="item.icon" />
          <strong>{{ item.title }}</strong>
          <ion-button
            v-if="canConfigure(item)"
            size="small"
            fill="outline"
            color="danger"
            :data-testid="`blocking-configure-${item.key}`"
            @click="router.push(item.route)"
          >
            {{ $t('base.blocking.configure') }}
          </ion-button>
          <em
            v-else-if="!item.actionable"
            class="blocking-strip-note"
          >{{ $t('base.setup.delegatedHint') }}</em>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.blocking-strip {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-inline-start: 4px solid var(--ion-color-danger);
  background: color-mix(in oklab, var(--ion-color-danger) 12%, var(--ion-background-color, #fff));
}

.blocking-strip-icon {
  flex: none;
  font-size: 22px;
  color: var(--ion-color-danger);
}

.blocking-strip-body {
  min-width: 0;
}

.blocking-strip-title {
  margin: 0;
  font-weight: 700;
}

.blocking-strip-text {
  margin: 2px 0 6px;
  font-size: 0.875rem;
}

.blocking-strip-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.blocking-strip-item {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 0.875rem;
}

.blocking-strip-item :deep(ion-icon),
.blocking-strip-item > :first-child {
  color: var(--ion-color-danger);
}

.blocking-strip-note {
  color: var(--ion-color-medium-shade, #555);
}
</style>
