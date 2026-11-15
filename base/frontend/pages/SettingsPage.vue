<script setup lang="ts">
// The tab goes in the hash, replaced, so a link opens it and Back leaves the page instead of walking its tabs. The list
// of devices is an administrator's: whoever does not run the hub reads why instead, and no list is asked for.
import { AppPage, type ShellTab, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import ApiDocsCard from '../components/ApiDocsCard.vue';
import DeviceModeCard from '../components/DeviceModeCard.vue';
import DevicesCard from '../components/DevicesCard.vue';
import PinPolicyCard from '../components/PinPolicyCard.vue';
import BusinessPanel from '../components/settings/BusinessPanel.vue';
import TicketsPanel from '../components/settings/TicketsPanel.vue';
import DataPanel from '../components/data/DataPanel.vue';
import { type SettingsTab, settingsTab } from '../lib/data';
import { useBaseI18n } from '../lib/i18n';
import '../settings.css';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();
const canManage = computed(() => session.can('base.administer_hub'));

const tabs = computed<ShellTab[]>(() => [
  { id: 'general', label: t('base.settings.tabs.general'), icon: 'ion:settings-outline' },
  { id: 'business', label: t('base.settings.tabs.business'), icon: 'ion:wallet-outline' },
  { id: 'tickets', label: t('base.settings.tabs.tickets'), icon: 'lucide:receipt' },
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
    <template v-if="tab === 'general'">
      <DeviceModeCard />
      <PinPolicyCard />
      <DevicesCard v-if="canManage" />
      <section
        v-else
        class="settings-card"
        data-testid="devices-admin-only"
      >
        <h2 class="settings-card__title">
          {{ t('base.devices.title') }}
        </h2>
        <p class="settings-card__note">
          {{ t('base.devices.adminOnly') }}
        </p>
      </section>
      <ApiDocsCard />
    </template>
    <BusinessPanel v-else-if="tab === 'business'" />
    <TicketsPanel v-else-if="tab === 'tickets'" />
    <DataPanel v-else-if="tab === 'data'" />
  </AppPage>
</template>
