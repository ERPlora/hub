<script setup lang="ts">
// Cash register → Settings (CASH_REGISTER-F01, F02; WORKBOOK «Pantallas · Ajustes de Caja»): the drawer
// settings and the drawers, in the reading width of a settings page. The menu offers the tab to everyone
// (no permission per menu entry yet), so whoever lacks `cash_register.manage_settings` reads them blocked,
// with the reason, never a refused read. Remounted when the person changes (a PIN switch).
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';

import RegistersCard from '../components/RegistersCard.vue';
import SettingsCard from '../components/SettingsCard.vue';
import { cashRegisterTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('cash_register.manage_settings'));
</script>

<template>
  <AppPage
    :title="$t('cash_register.title')"
    :tabs="cashRegisterTabs($t)"
    :tabs-label="$t('cash_register.tabs.label')"
    content-layout="detail"
  >
    <div class="cash-settings-page">
      <SettingsCard
        :key="canManage ? 'manage' : 'read'"
        :editable="canManage"
      />
      <RegistersCard :editable="canManage" />
    </div>
  </AppPage>
</template>

<style scoped>
.cash-settings-page {
  display: grid;
  gap: 1.5rem;
}
</style>
