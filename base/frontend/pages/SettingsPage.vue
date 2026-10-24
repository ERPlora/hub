<script setup lang="ts">
// Settings (the old hub's `/settings`, APP-BASE-2): the footer tabbar of its sections, the tab in the hash (`#data`)
// so a link opens it and Back leaves the page instead of walking its tabs. Today only «Data and backups»
// (BASE-G101–G109); Hub, Business, Tickets and Permissions arrive with their flows (APP-BASE-6), never painted empty.
import { AppPage, type ShellTab } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import DataPanel from '../components/data/DataPanel.vue';
import { type SettingsTab, settingsTab } from '../lib/data';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();

const tabs = computed<ShellTab[]>(() => [
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
    <DataPanel v-if="tab === 'data'" />
  </AppPage>
</template>
