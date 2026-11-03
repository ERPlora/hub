<script setup lang="ts">
// System (the old hub's SystemPage): its four tabs in the address hash (BASE-F39; `base/lib/system.ts`): «Usage and plan»
// (BASE-F40), Updates (BASE-G89), Failed events (BASE-G91…G94) and Logs (BASE-G90). What only who runs the business may read
// (hub#2519) is asked only for them: anyone else is told who may see it, has no Logs tab, and their session never asks the
// Hub what it would refuse. The old `#backups` lands on Settings › Data.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage, type ShellTab, useSession } from '@erplora/ui/shell';
import { computed, watchEffect } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import FailedEvents from '../components/FailedEvents.vue';
import SystemLog from '../components/SystemLog.vue';
import SystemRelease from '../components/SystemRelease.vue';
import SystemUsage from '../components/SystemUsage.vue';
import { useBaseI18n } from '../lib/i18n';
import { BACKUPS_HASH, BACKUPS_TARGET, type SystemTab, TAB_HASH, tabOf, tabsFor } from '../lib/system';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();

/** Who runs the business: the status, Failed events and Logs are theirs (hub#2519). */
const admin = computed(() => session.can('base.administer_hub'));

const TAB_ICON: Record<SystemTab, string> = {
  usage: 'ion:speedometer-outline',
  updates: 'ion:refresh-outline',
  events: 'ion:alert-circle-outline',
  logs: 'ion:list-outline',
};
const tabs = computed<ShellTab[]>(() =>
  tabsFor(admin.value).map((id) => ({
    id,
    label: t(`base.system.tabs.${id}`),
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
      <SystemUsage v-if="admin" />
      <InlineFeedback
        v-else
        tone="info"
        data-testid="system-usage-denied"
      >
        {{ t('base.system.usage.denied') }}
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
      <p class="system-updates-hint">
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
