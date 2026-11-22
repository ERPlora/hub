<script setup lang="ts">
// Printing → Settings (PRINTING-F06; WORKBOOK «Pantallas · Ajustes»): the ticket settings and the printer
// of each role, in the reading width of a settings page. The menu offers the tab to everyone, so whoever
// lacks `printing.manage_settings` reads them blocked, with the reason, never a refused read. Remounted when
// the person changes (a PIN switch).
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';

import { useAppTabs } from '../../../../base/frontend/lib/app-tabs';
import SettingsCard from '../components/SettingsCard.vue';

const session = useSession();
const tabs = useAppTabs('printing');
const canManage = computed(() => session.can('printing.manage_settings'));
</script>

<template>
  <AppPage
    :title="$t('printing.title')"
    :tabs="tabs"
    :tabs-label="$t('printing.tabs.label')"
    content-layout="detail"
  >
    <SettingsCard
      :key="canManage ? 'manage' : 'read'"
      :editable="canManage"
    />
  </AppPage>
</template>
