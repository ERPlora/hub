<script setup lang="ts">
// ShareDialog — «Share and QR»: the website's address to copy, its QR code to download (a PNG to print, an SVG to
// scale; `website.qr.get`, served as the image file it is) and, honestly, why that address opens the app on the
// owner's own device: she is signed in there, and a session gets the shell on `/`. While the site is not online the
// address still opens the team's sign-in page, and the dialog says so. With a catalog on the page, a second address
// and QR open it right at the catalog (its section's anchor), to print for the tables. Each download brings the image
// with the session and hands it to the Hub's `saveFile`: the browser's downloads, or the installed app's, which says
// where (hub#1041).
import { fetchFile } from '@erplora/ui/sdk';
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonContent, IonHeader, IonModal, IonTitle, IonToolbar } from '@ionic/vue';
import { computed, ref } from 'vue';

import { saveFile } from '../../../../base/frontend/lib/download';
import { useT } from '../composables/useT';

const props = defineProps<{
  open: boolean;
  /** The hub's public address (`website.site.get`'s `public_url`). */
  url: string;
  isLive: boolean;
  /** The page shows a catalog: offer its own address and QR too. */
  catalog?: boolean;
}>();

const emit = defineEmits<{ 'update:open': [value: boolean] }>();

type Target = 'page' | 'catalog';

const t = useT();
const QR = '/api/website/qr';
const QR_TYPES = { png: 'image/png', svg: 'image/svg+xml' } as const;
/** The target whose link could not be copied, if any. */
const copyFailed = ref<Target | null>(null);

/** What the dialog shares: the page and, with a catalog on it, the page right at its catalog. */
const targets = computed(() => [
  { target: 'page' as Target, testid: 'website-share', url: props.url, label: t('website.share.url'), qr: t('website.share.qr') },
  ...(props.catalog
    ? [{ target: 'catalog' as Target, testid: 'website-share-catalog', url: `${props.url}#catalog`, label: t('website.share.catalog.url'), qr: t('website.share.catalog.qr') }]
    : []),
]);

function qrUrl(format: keyof typeof QR_TYPES, target: Target): string {
  return target === 'page' ? `${QR}?format=${format}` : `${QR}?format=${format}&target=${target}`;
}

function close(): void {
  copyFailed.value = null;
  emit('update:open', false);
}

async function downloadQr(format: keyof typeof QR_TYPES, target: Target): Promise<void> {
  try {
    const { blob, name } = await fetchFile(qrUrl(format, target), QR_TYPES[format]);
    await saveFile(name || `website-qr.${format}`, blob, t);
  } catch (error) {
    console.error('website: the QR did not come', error);
    toastError(t('base.download.refusal.failed'));
  }
}

async function copy(url: string, target: Target): Promise<void> {
  copyFailed.value = null;
  try {
    await navigator.clipboard.writeText(url);
    toastSuccess(t('website.share.copied'));
  } catch {
    copyFailed.value = target;
  }
}
</script>

<template>
  <ion-modal
    :is-open="open"
    class="ws-share"
    data-testid="website-share-dialog"
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
      <section
        v-for="one in targets"
        :key="one.target"
        class="ws-share__target"
      >
        <p
          class="ws-share__label"
          :data-testid="`${one.testid}-label`"
        >
          {{ one.label }}
        </p>
        <p class="ws-share__url">
          <code :data-testid="`${one.testid}-url`">{{ one.url }}</code>
        </p>
        <ion-button
          expand="block"
          :data-testid="`${one.testid}-copy`"
          @click="copy(one.url, one.target)"
        >
          <HubIcon
            slot="start"
            name="ion:copy-outline"
          />
          {{ t('website.share.copy') }}
        </ion-button>
        <p
          v-if="copyFailed === one.target"
          class="ws-share__error"
          role="alert"
          :data-testid="`${one.testid}-copy-error`"
        >
          {{ t('website.share.copyError') }}
        </p>
        <template v-if="one.target === 'page'">
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
        </template>
        <p
          v-else
          class="ws-share__note"
          :data-testid="`${one.testid}-hint`"
        >
          {{ t('website.share.catalog.hint') }}
        </p>
        <img
          class="ws-share__qr"
          :src="qrUrl('svg', one.target)"
          :alt="one.qr"
          width="220"
          height="220"
          :data-testid="`${one.testid}-qr`"
        >
        <div class="ws-share__downloads">
          <ion-button
            fill="outline"
            :data-testid="`${one.testid}-png`"
            @click="downloadQr('png', one.target)"
          >
            <HubIcon
              slot="start"
              name="ion:download-outline"
            />
            {{ t('website.share.downloadPng') }}
          </ion-button>
          <ion-button
            fill="outline"
            :data-testid="`${one.testid}-svg`"
            @click="downloadQr('svg', one.target)"
          >
            <HubIcon
              slot="start"
              name="ion:download-outline"
            />
            {{ t('website.share.downloadSvg') }}
          </ion-button>
        </div>
      </section>
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
.ws-share__target + .ws-share__target {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--ep-border);
}
</style>
