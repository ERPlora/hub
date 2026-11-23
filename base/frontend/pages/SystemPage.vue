<script setup lang="ts">
// System is for whoever runs the business: the app gate says «No access» to anyone else before this page mounts.
// Below «Usage and plan» go the cards the apps that are on put there. The old `#backups` lands on Settings › Data.
import { AppPage, type ShellTab } from '@erplora/ui/shell';
import { computed, watchEffect } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import FailedEvents from '../components/FailedEvents.vue';
import SystemAppCards from '../components/SystemAppCards.vue';
import SystemLog from '../components/SystemLog.vue';
import SystemRelease from '../components/SystemRelease.vue';
import SystemReleaseNotes from '../components/SystemReleaseNotes.vue';
import SystemUsage from '../components/SystemUsage.vue';
import { useBaseI18n } from '../lib/i18n';
import { BACKUPS_HASH, BACKUPS_TARGET, SYSTEM_TABS, type SystemTab, TAB_HASH, tabOf } from '../lib/system';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();

const TAB_ICON: Record<SystemTab, string> = {
  usage: 'ion:speedometer-outline',
  updates: 'ion:refresh-outline',
  events: 'ion:alert-circle-outline',
  logs: 'ion:list-outline',
};
const tabs = computed<ShellTab[]>(() =>
  SYSTEM_TABS.map((id) => ({
    id,
    label: t(`base.system.tabs.${id}`),
    icon: TAB_ICON[id],
  })),
);
const tab = computed<SystemTab>({
  get: () => tabOf(route.hash),
  set: (next) => void router.replace({ path: route.path, hash: TAB_HASH[next] }),
});

// The old `#backups`: its copies live in Settings › Data now.
watchEffect(() => {
  if (route.hash === BACKUPS_HASH) void router.replace(BACKUPS_TARGET);
});
</script>

<template>
  <AppPage
    v-model:tab="tab"
    :title="t('base.systemPlan.title')"
    :tabs="tabs"
    :tabs-label="t('base.systemPlan.tabs.label')"
  >
    <div
      v-if="tab === 'usage'"
      class="system-tab"
    >
      <SystemUsage />
      <SystemAppCards />
    </div>
    <section
      v-else-if="tab === 'updates'"
      class="system-tab system-updates"
      data-testid="system-updates"
    >
      <header class="system-updates-head">
        <h2>{{ t('base.system.updates.heading') }}</h2>
        <SystemRelease />
      </header>
      <p class="system-updates-hint">
        {{ t('base.system.updates.auto') }}
      </p>
      <SystemReleaseNotes />
    </section>
    <div
      v-else-if="tab === 'events'"
      class="system-tab"
    >
      <FailedEvents />
    </div>
    <div
      v-else
      class="system-tab"
    >
      <SystemLog />
    </div>
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

.system-updates-hint {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}
</style>
