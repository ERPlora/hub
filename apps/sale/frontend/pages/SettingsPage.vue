<script setup lang="ts">
// Sales & POS → Settings (SALE-F34; WORKBOOK «Pantallas · Ajustes»): the till settings form, in the reading
// width of a settings page. The menu offers the tab to everyone (no permission per menu entry yet:
// UI-REQUESTS.md), so whoever lacks `sale.manage_settings` gets the business's values blocked with the
// reason, never a refused read. The form is remounted when the person changes with the tab open (a PIN
// switch), so it reads what the new person may read.
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';

import SettingsForm from '../components/backoffice/SettingsForm.vue';
import { saleTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('sale.manage_settings'));
</script>

<template>
  <AppPage
    :title="$t('sale.title')"
    :tabs="saleTabs($t)"
    :tabs-label="$t('sale.tabs.label')"
    content-layout="detail"
  >
    <SettingsForm
      :key="canManage ? 'manage' : 'read'"
      :editable="canManage"
    />
  </AppPage>
</template>
