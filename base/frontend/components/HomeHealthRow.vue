<script setup lang="ts">
// The Home's health row (BASE-F02), under the greeting: for who runs the business, how each app on says it is, the way
// to fix what can be fixed and «View system». What it says moves with time and no event (a printer goes quiet), so it
// is not live: it is asked when the Home opens and again each time the person comes back to it. A reading that fails
// says so instead of the last one, which could say ready when it no longer is.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonSkeletonText } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { HEALTH_PILLS } from '../lib/home-health';
import { useBaseI18n } from '../lib/i18n';
import type { HomeHealthItem } from '../operations/home';

const { t } = useBaseI18n();
const client = useLiveClient();
const session = useSession();
const route = useRoute();
const router = useRouter();

const runsTheBusiness = computed(() => session.can('base.administer_hub'));
const items = ref<HomeHealthItem[]>();
const failed = ref(false);
const loading = computed(() => items.value === undefined && !failed.value);
const shown = computed(() => runsTheBusiness.value && (items.value === undefined || items.value.length > 0));
/** How many readings were asked: an answer to an older one is dropped. */
let asked = 0;

async function read(): Promise<void> {
  const reading = ++asked;
  try {
    const answer = await client.api.call('base.health.list', {});
    if (reading !== asked) return;
    items.value = answer.items;
    failed.value = false;
  } catch (error) {
    console.warn('base: the Home could not read how the business is working', error);
    if (reading !== asked) return;
    items.value = undefined;
    failed.value = true;
  }
}

function retry(): void {
  failed.value = false;
  void read();
}

watch(
  runsTheBusiness,
  (runs) => {
    if (runs && items.value === undefined) void read();
  },
  { immediate: true },
);

const homePath = route.path;
watch(
  () => route.path,
  (path, before) => {
    if (runsTheBusiness.value && path === homePath && before !== homePath) void read();
  },
);
</script>

<template>
  <section
    v-if="shown"
    class="home-health"
    data-testid="home-health"
    :aria-label="t('base.home.health.label')"
    :aria-busy="loading"
  >
    <ion-skeleton-text
      v-if="loading"
      animated
      class="home-health-skeleton"
      data-testid="home-health-loading"
    />
    <InlineFeedback
      v-else-if="failed"
      class="home-health-error"
      tone="neutral"
      data-testid="home-health-error"
    >
      {{ t('base.home.health.loadError') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="home-health-retry"
          @click="retry"
        >
          {{ t('base.home.health.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <ul
      v-else
      class="home-health-items"
    >
      <li
        v-for="item in items"
        :key="item.key"
        class="home-health-item"
        data-testid="home-health-item"
        :data-app="item.app"
        :data-state="item.state"
      >
        <StatusPill
          :label="item.title"
          :tone="HEALTH_PILLS[item.state].tone"
          :icon="HEALTH_PILLS[item.state].icon"
        />
        <ion-button
          v-if="item.action && item.route"
          size="small"
          fill="clear"
          class="home-health-action"
          data-testid="home-health-action"
          @click="router.push(item.route)"
        >
          {{ item.action }}
        </ion-button>
      </li>
    </ul>
    <ion-button
      size="small"
      fill="clear"
      class="home-health-system"
      data-testid="home-health-system"
      @click="router.push('/system')"
    >
      {{ t('base.home.health.viewSystem') }}
      <HubIcon
        slot="end"
        name="ion:chevron-forward-outline"
      />
    </ion-button>
  </section>
</template>

<style scoped>
.home-health {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin: 0 0 16px;
}

.home-health-items {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.home-health-item {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.home-health-action,
.home-health-system {
  margin: 0;
}

.home-health-system {
  margin-inline-start: auto;
}

.home-health-error {
  flex: 1 1 280px;
  margin: 0;
}

.home-health-skeleton {
  flex: 1 1 240px;
  max-width: 420px;
  height: 28px;
  margin: 0;
  border-radius: 999px;
}
</style>
