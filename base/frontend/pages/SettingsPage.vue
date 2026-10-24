<script setup lang="ts">
// Settings (`/settings`; the old hub's «Ajustes»). Its «General» tab brings the way in's cards (APP-BASE-3): «This
// device» (BASE-G72), «PIN pad» (G151, G62) and «Devices» (G63…G66), whose list is an administrator's: whoever does
// not run the hub reads why instead, and no list is asked for. The other tabs of the old hub (Business, Printing,
// Permissions, Data and copies) come with their parts of base; the tab strip appears once there are two.
import { type ShellTab, AppPage, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';

import DeviceModeCard from '../components/DeviceModeCard.vue';
import DevicesCard from '../components/DevicesCard.vue';
import PinPolicyCard from '../components/PinPolicyCard.vue';
import { useBaseI18n } from '../lib/i18n';
import '../settings.css';

const { t } = useBaseI18n();
const session = useSession();
const canManage = computed(() => session.can('base.administer_hub'));

const tabs = computed<ShellTab[]>(() => [
  { id: 'general', label: t('base.settings.tabs.general'), icon: 'ion:settings-outline', to: '/settings' },
]);
</script>

<template>
  <AppPage
    :title="t('base.settings.title')"
    :tabs="tabs.length > 1 ? tabs : []"
    :tabs-label="t('base.settings.tabs.label')"
    content-layout="detail"
  >
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
  </AppPage>
</template>
