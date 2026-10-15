<script setup lang="ts">
// WhatsApp inbox → Settings, the product's «Ajustes del canal» (WHATSAPP_INBOX-F01, F02, F13, F27, F28):
// owner and admin only. Its body (the number, the month, the Meta templates) is ChannelSettings, mounted
// only for whoever configures, so nobody else subscribes to it; everyone else reads «You do not have
// permission», as the old menu entry answered.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed } from 'vue';

import ChannelSettings from '../components/ChannelSettings.vue';
import { inboxTabs } from '../tabs';

const session = useSession();
const canConfigure = computed(() => session.can('whatsapp_inbox.configure'));
</script>

<template>
  <AppPage
    :title="$t('whatsapp_inbox.settingsTitle')"
    content-layout="detail"
    :tabs="inboxTabs($t)"
    :tabs-label="$t('whatsapp_inbox.tabs.label')"
  >
    <ChannelSettings v-if="canConfigure" />
    <InlineFeedback
      v-else
      tone="warning"
      data-testid="whatsapp-inbox-settings-forbidden"
      :heading="$t('whatsapp_inbox.noPermission')"
    />
  </AppPage>
</template>
