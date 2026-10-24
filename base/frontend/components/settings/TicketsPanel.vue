<script setup lang="ts">
// Settings › Printing (BASE-G96; the old hub's «Impresión», HUB_SHELL-F165): «Printers and ticket» opens the Printing
// app, where printers are added and the ticket is set up; while Printing is not on, it says to install it and opens
// Apps. The printers and the ticket are Printing's, never the shell's: nothing is kept here.
import { useSession } from '@erplora/ui/shell';
import { IonList } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../../lib/i18n';
import SettingsRow from './SettingsRow.vue';

const { t } = useBaseI18n();
const session = useSession();

const printingOn = computed(() => session.me.value?.apps.some((app) => app.label === 'printing' && app.state === 'on'));
</script>

<template>
  <section class="settings-tickets">
    <ion-list lines="none">
      <SettingsRow
        data-testid="tickets-printers"
        icon="ion:ticket-outline"
        :title="t('base.settingsTickets.printers')"
        :hint="printingOn ? t('base.settingsTickets.printersHint') : t('base.settingsTickets.install')"
        :to="printingOn ? '/printing/printers' : '/apps'"
      />
    </ion-list>
  </section>
</template>

<style scoped>
.settings-tickets {
  box-sizing: border-box;
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--ion-color-step-150, #e4e7ec);
  border-radius: var(--ep-radius-lg, 16px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}

.settings-tickets ion-list {
  padding: 0;
  background: transparent;
}
</style>
