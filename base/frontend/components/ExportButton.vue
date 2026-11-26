<script setup lang="ts">
// A button that downloads a file the server writes (the rows a list shows, an invoice's PDF): the download icon alone,
// its label as its name and tooltip. `load` asks for it, the Hub's `saveFile` hands it over, and a refusal is told with
// its reason.
import { HubIcon, toastError } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';

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
  /** As tall as the other buttons of a page, not a list's toolbar's. */
  regular?: boolean;
}>();

const { t } = useBaseI18n();
const pending = ref(false);
const name = computed(() => (pending.value ? props.pendingLabel : props.label));

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
    class="ion-no-margin"
    :size="regular ? undefined : 'small'"
    fill="outline"
    :data-testid="testid"
    :disabled="disabled || pending"
    :aria-label="name"
    :title="name"
    @click="exportFile"
  >
    <ion-spinner
      v-if="pending"
      slot="icon-only"
      name="crescent"
    />
    <HubIcon
      v-else
      slot="icon-only"
      name="ion:download-outline"
    />
  </ion-button>
</template>
