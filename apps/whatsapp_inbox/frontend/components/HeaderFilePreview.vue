<script setup lang="ts">
// The file of a template's photo, video or document header as the template's sheet (WHATSAPP_INBOX-F29, F30) and
// «Send a template» (F33) show it, as WhatsApp Manager, WATI or respond.io do: the photo's thumbnail, the video's first
// frame with a play sign, a document's icon (the one Files gives a PDF); what the sheet puts in the slot (its name and
// size) next to it. The Hub serves the file at `sample.url` (`/p/media/…`, to the hub's people only: `'self'` in the
// CSP). While the photo or the video loads, a spinner; if it cannot be shown, a notice, and the name stays.
//   <HeaderFilePreview :sample="sample" testid="…-preview"><p>{{ name }} · {{ size }}</p></HeaderFilePreview>
// `data-testid` hooks: `<testid>` on the root, `-image`, `-video`, `-play`, `-document`, `-broken`, `-loading`, `-error`.
import { HubIcon } from '@erplora/ui/shell';
import { IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import type { TemplateSampleOut } from '../operations';

const props = defineProps<{
  sample: TemplateSampleOut;
  testid: string;
}>();

/** The photo or the video could not be loaded from its address. */
const failed = ref(false);
const loaded = ref(false);
watch(
  () => props.sample.url,
  () => {
    failed.value = false;
    loaded.value = false;
  },
);

const kind = computed(() => props.sample.header_format);
const media = computed(() => kind.value === 'IMAGE' || kind.value === 'VIDEO');
/** A photo or a video without an address cannot be shown either. */
const broken = computed(() => media.value && (failed.value || !props.sample.url));
const loading = computed(() => media.value && !broken.value && !loaded.value);
</script>

<template>
  <div
    class="wa-header-file"
    :data-testid="testid"
  >
    <div
      class="wa-header-file__thumb"
      :aria-busy="loading ? 'true' : undefined"
    >
      <img
        v-if="kind === 'IMAGE' && !broken"
        class="wa-header-file__media"
        :src="sample.url"
        :alt="sample.name"
        decoding="async"
        :data-testid="`${testid}-image`"
        @load="loaded = true"
        @error="failed = true"
      >
      <template v-else-if="kind === 'VIDEO' && !broken">
        <!-- #t=0.1: the first frame, which some browsers paint only once the video is at a time. -->
        <video
          class="wa-header-file__media"
          :src="`${sample.url}#t=0.1`"
          :aria-label="sample.name"
          preload="metadata"
          muted
          playsinline
          disablepictureinpicture
          :data-testid="`${testid}-video`"
          @loadeddata="loaded = true"
          @error="failed = true"
        />
        <HubIcon
          v-if="!loading"
          class="wa-header-file__play"
          name="ion:play-circle-outline"
          :data-testid="`${testid}-play`"
        />
      </template>
      <HubIcon
        v-else-if="kind === 'DOCUMENT'"
        class="wa-header-file__icon"
        name="ion:receipt-outline"
        :data-testid="`${testid}-document`"
      />
      <HubIcon
        v-else-if="kind === 'VIDEO'"
        class="wa-header-file__icon"
        name="ion:play-circle-outline"
        :data-testid="`${testid}-broken`"
      />
      <HubIcon
        v-else
        class="wa-header-file__icon"
        name="ion:image-outline"
        :data-testid="`${testid}-broken`"
      />
      <ion-spinner
        v-if="loading"
        class="wa-header-file__loading"
        name="crescent"
        aria-hidden="true"
        :data-testid="`${testid}-loading`"
      />
    </div>
    <div class="wa-header-file__text">
      <slot />
      <p
        v-if="broken"
        class="wa-header-file__error"
        role="status"
        :data-testid="`${testid}-error`"
      >
        {{ $t(`whatsapp_inbox.templates.editor.previewFailed.${kind}`) }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.wa-header-file {
  display: flex;
  flex: 1 1 14rem;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.wa-header-file__thumb {
  position: relative;
  display: grid;
  place-items: center;
  flex: none;
  width: 64px;
  height: 64px;
  border-radius: var(--ep-radius-sm, 6px);
  overflow: hidden;
  background: var(--ep-surface-muted, var(--ion-color-step-50, #f2f2f2));
  color: var(--ion-color-medium-shade);
}
/* A thumbnail: the header's photo or frame fills the square, cropped as WhatsApp crops a header. */
.wa-header-file__media {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.wa-header-file__icon {
  font-size: 28px;
}
.wa-header-file__play {
  position: absolute;
  font-size: 28px;
  color: #fff;
  filter: drop-shadow(0 1px 2px rgb(0 0 0 / 0.55));
}
.wa-header-file__loading {
  position: absolute;
  width: 24px;
  height: 24px;
}
.wa-header-file__text {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.wa-header-file__text :slotted(p) {
  margin: 0;
  overflow-wrap: anywhere;
}
.wa-header-file__error {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-danger);
}
</style>
