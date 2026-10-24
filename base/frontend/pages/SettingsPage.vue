<script setup lang="ts">
// Settings (the old hub's `/settings`; BASE-G96): the footer tabbar of its sections, the tab in the hash (`#business`,
// `#tickets`, `#data`) so a link opens it and Back leaves the page instead of walking its tabs. «Business» and
// «Printing» (APP-BASE-6), «Data and backups» (BASE-G101–G109, APP-BASE-2); the old `#tax` opens Business.
import { AppPage, type ShellTab } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import BusinessPanel from '../components/settings/BusinessPanel.vue';
import TicketsPanel from '../components/settings/TicketsPanel.vue';
import DataPanel from '../components/data/DataPanel.vue';
import { type SettingsTab, settingsTab } from '../lib/data';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();

const tabs = computed<ShellTab[]>(() => [
  // ── Business settings (APP-BASE-6) ──
  { id: 'business', label: t('base.settings.tabs.business'), icon: 'ion:wallet-outline' },
  { id: 'tickets', label: t('base.settings.tabs.tickets'), icon: 'lucide:receipt' },
  // ── Data (APP-BASE-2) ──
  { id: 'data', label: t('base.settings.tabs.data'), icon: 'ion:swap-vertical-outline' },
]);
const tab = computed<SettingsTab>({
  get: () => settingsTab(route.hash),
  set: (next) => void router.replace({ path: route.path, query: route.query, hash: `#${next}` }),
});
</script>

<template>
  <AppPage
    v-model:tab="tab"
    :title="t('base.settings.title')"
    :tabs="tabs"
    :tabs-label="t('base.settings.tabs.label')"
    content-layout="detail"
  >
    <BusinessPanel v-if="tab === 'business'" />
    <TicketsPanel v-else-if="tab === 'tickets'" />
    <DataPanel v-else-if="tab === 'data'" />
  </AppPage>
</template>
