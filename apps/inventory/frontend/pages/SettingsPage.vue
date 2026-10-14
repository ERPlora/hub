<script setup lang="ts">
// Inventory → Settings (WORKBOOK «Ajustes», INVENTORY-F19). Only whoever can manage the inventory
// settings sees the tab; anyone else who types its address gets the shell's «This page does not
// exist» (and nothing is asked of the server). Whoever opened it with the permission keeps the form,
// which locks itself if the person changes with the tab open (SettingsForm).
import { EmptyState } from '@erplora/ui/components';
import { AppPage, useSession, useShellConfig } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';

import SettingsForm from '../components/SettingsForm.vue';
import { useInventoryTabs } from '../composables/useInventoryTabs';

const session = useSession();
const tabs = useInventoryTabs();
const { homePath } = useShellConfig();
/** Decided once, when the page opens: a later shift change locks the form instead. */
const allowed = session.can('inventory.manage_settings');
</script>

<template>
  <AppPage
    :title="$t('inventory.title')"
    :tabs="tabs"
    :tabs-label="$t('inventory.tabs.label')"
    content-layout="detail"
  >
    <SettingsForm v-if="allowed" />
    <EmptyState
      v-else
      icon="help-circle-outline"
      data-testid="inventory-settings-not-found"
      :heading="$t('notFound.title')"
      :message="$t('notFound.body')"
    >
      <template #action>
        <ion-button :router-link="homePath">
          {{ $t('notFound.action') }}
        </ion-button>
      </template>
    </EmptyState>
  </AppPage>
</template>
