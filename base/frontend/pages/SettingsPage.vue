<script setup lang="ts">
// Settings (the old hub's `/settings`; BASE-G96): the footer tabbar of its sections, the tab in the hash (`#general`,
// `#business`, `#tickets`, `#data`) so a link opens it and Back leaves the page instead of walking its tabs. In the old
// hub's order: «General» first (APP-BASE-3), with «This device» (BASE-G72), «PIN pad» (G151, G62) and «Devices»
// (G63…G66), whose list is an administrator's: whoever does not run the hub reads why instead, and no list is asked
// for. Then «Business» and «Printing» (APP-BASE-6) and «Data and backups» (BASE-G101–G109, APP-BASE-2); the old `#hub`
// opens General and `#tax` Business. Permissions arrives with its flows, never painted empty.
import { AppPage, type ShellTab, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

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
  // ── General: this device, the PIN pad and the devices (APP-BASE-3) ──
  { id: 'general', label: t('base.settings.tabs.general'), icon: 'ion:settings-outline' },
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
    </template>
    <BusinessPanel v-else-if="tab === 'business'" />
    <TicketsPanel v-else-if="tab === 'tickets'" />
    <DataPanel v-else-if="tab === 'data'" />
  </AppPage>
</template>
