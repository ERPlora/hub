<script setup lang="ts">
// A toolbar button that downloads a file the server writes with the rows a list shows: `load` asks for it, the Hub's
// `saveFile` hands it over, and a refusal is told with its reason.
import { HubIcon, toastError } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { ref } from 'vue';

import { saveFile } from '../lib/download';
import { useBaseI18n } from '../lib/i18n';

const props = defineProps<{
  testid: string;
  label: string;
  pendingLabel: string;
  /** What a refusal says, with its reason. */
  failed: (reason: string) => string;
  load: () => Promise<{ filename: string; blob: Blob }>;
  disabled?: boolean;
}>();

const { t } = useBaseI18n();
const pending = ref(false);

async function exportFile(): Promise<void> {
  if (props.disabled || pending.value) return;
  pending.value = true;
  try {
    const file = await props.load();
    await saveFile(file.filename, file.blob, t);
  } catch (error) {
    toastError(props.failed(error instanceof Error ? error.message : String(error)));
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <ion-button
    class="export-button"
    size="small"
    fill="outline"
    :data-testid="testid"
    :disabled="disabled || pending"
    @click="exportFile"
  >
    <HubIcon
      slot="start"
      name="ion:download-outline"
    />
    {{ pending ? pendingLabel : label }}
  </ion-button>
</template>

<style scoped>
/* As tall as the toolbar's other controls: a finger's target on a tablet and a phone. */
.export-button {
  margin: 0;
  min-height: 44px;
  --border-radius: 10px;
}
</style>
