<script setup lang="ts">
// The sparkles «Assistant» of the topbar (BASE-G110; the old hub's, before the bell): opens and closes the panel,
// pressed while open (`aria-pressed`: `ion-button` follows no `aria-expanded` once painted). Only to a person who may use the assistant: it answers to whoever sees the Home.
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useAssistant } from '../../lib/assistant';
import { useBaseI18n } from '../../lib/i18n';

const { t } = useBaseI18n();
const session = useSession();
const assistant = useAssistant();
const allowed = computed(() => session.can('base.view_home'));
</script>

<template>
  <ion-button
    v-if="allowed"
    class="assistant-button"
    data-testid="assistant-button"
    :aria-label="t('base.assistant.open')"
    :title="t('base.assistant.open')"
    :aria-pressed="assistant.state.open ? 'true' : 'false'"
    :color="assistant.state.open ? 'primary' : undefined"
    @click="assistant.toggle()"
  >
    <HubIcon
      slot="icon-only"
      name="ion:sparkles-outline"
    />
  </ion-button>
</template>
