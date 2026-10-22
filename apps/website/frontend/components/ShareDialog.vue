<script setup lang="ts">
// ShareDialog — «Share and QR»: the website's address to copy, its QR code to download (a PNG to print, an SVG to
// scale; `website.qr.get`, served as the image file it is) and, honestly, why that address opens the app on the
// owner's own device: she is signed in there, and a session gets the shell on `/`. While the site is not online the
// address still opens the team's sign-in page, and the dialog says so.
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonContent, IonHeader, IonModal, IonTitle, IonToolbar } from '@ionic/vue';
import { ref } from 'vue';

import { useT } from '../composables/useT';

defineProps<{
  open: boolean;
  /** The hub's public address (`website.site.get`'s `public_url`). */
  url: string;
  isLive: boolean;
}>();

const emit = defineEmits<{ 'update:open': [value: boolean] }>();

const t = useT();
const QR = '/api/website/qr';
const copyFailed = ref(false);

function close(): void {
  copyFailed.value = false;
  emit('update:open', false);
}

async function copy(url: string): Promise<void> {
  copyFailed.value = false;
  try {
    await navigator.clipboard.writeText(url);
    void toastSuccess(t('website.share.copied'));
  } catch {
    copyFailed.value = true;
  }
}
</script>

<template>
  <ion-modal
    :is-open="open"
    class="ws-share"
    data-testid="website-share"
    @did-dismiss="close"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title>{{ t('website.share.title') }}</ion-title>
        <ion-buttons slot="end">
          <ion-button
            data-testid="website-share-close"
            :aria-label="t('website.share.close')"
            @click="close"
          >
            <HubIcon
              slot="icon-only"
              name="ion:close-outline"
            />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <p class="ws-share__label">
        {{ t('website.share.url') }}
      </p>
      <p class="ws-share__url">
        <code data-testid="website-share-url">{{ url }}</code>
      </p>
      <ion-button
        expand="block"
        data-testid="website-share-copy"
        @click="copy(url)"
      >
        <HubIcon
          slot="start"
          name="ion:copy-outline"
        />
        {{ t('website.share.copy') }}
      </ion-button>
      <p
        v-if="copyFailed"
        class="ws-share__error"
        role="alert"
        data-testid="website-share-copy-error"
      >
        {{ t('website.share.copyError') }}
      </p>
      <p
        v-if="!isLive"
        class="ws-share__note ws-share__note--warning"
        data-testid="website-share-not-live"
      >
        {{ t('website.share.notLive') }}
      </p>
      <p
        class="ws-share__note"
        data-testid="website-share-signed-in"
      >
        {{ t('website.share.signedIn') }}
      </p>
      <img
        class="ws-share__qr"
        :src="`${QR}?format=svg`"
        :alt="t('website.share.qr')"
        width="220"
        height="220"
        data-testid="website-share-qr"
      >
      <div class="ws-share__downloads">
        <ion-button
          fill="outline"
          :href="`${QR}?format=png`"
          download="website-qr.png"
          data-testid="website-share-png"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
          />
          {{ t('website.share.downloadPng') }}
        </ion-button>
        <ion-button
          fill="outline"
          :href="`${QR}?format=svg`"
          download="website-qr.svg"
          data-testid="website-share-svg"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
          />
          {{ t('website.share.downloadSvg') }}
        </ion-button>
      </div>
    </ion-content>
  </ion-modal>
</template>

<style scoped>
.ws-share__label {
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
}
.ws-share__url {
  margin: 4px 0 12px;
  font-size: 1rem;
  word-break: break-all;
}
.ws-share__note {
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
.ws-share__note--warning {
  color: var(--ion-color-warning-shade);
}
.ws-share__error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
.ws-share__qr {
  display: block;
  margin: 16px auto;
  background: #fff;
  border-radius: 8px;
}
.ws-share__downloads {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
</style>
