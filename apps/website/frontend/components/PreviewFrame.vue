<script setup lang="ts">
// PreviewFrame — the draft as visitors will see it: `GET /api/website/site/preview` (`website.site.preview`, the
// same render as the public page, framed only by the hub itself), reloaded whenever the page bumps `reloadKey` (after
// each save) or on demand, at a computer's width or a phone's (390 px). Until the page arrives it shows a spinner; a
// load that is not the page (an error answer: the session ended, the permission went) says so instead of a blank.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonLabel, IonSegment, IonSegmentButton, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';

const props = defineProps<{
  /** Bumped by the page after each save: the frame reloads. */
  reloadKey: number;
}>();

const t = useT();
const width = ref<'desktop' | 'mobile'>('desktop');
const manual = ref(0);
const loading = ref(true);
const failed = ref(false);

const src = computed(() => `/api/website/site/preview?v=${props.reloadKey}${manual.value ? `.${manual.value}` : ''}`);

watch(src, () => {
  loading.value = true;
  failed.value = false;
});

function loaded(event: Event): void {
  const doc = (event.target as HTMLIFrameElement).contentDocument;
  loading.value = false;
  // Same origin: the frame's document is readable. The page's body names its template; an error answer has none.
  failed.value = !doc?.body?.hasAttribute('data-ep-template');
}

function reload(): void {
  manual.value += 1;
}
</script>

<template>
  <div class="wp">
    <div class="wp-bar">
      <ion-segment
        data-testid="website-preview-width"
        :value="width"
        :aria-label="t('website.preview.width')"
        @ion-change="width = $event.detail.value === 'mobile' ? 'mobile' : 'desktop'"
      >
        <ion-segment-button value="desktop">
          <HubIcon name="ion:desktop-outline" />
          <ion-label>{{ t('website.preview.desktop') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button value="mobile">
          <HubIcon name="ion:phone-portrait-outline" />
          <ion-label>{{ t('website.preview.mobile') }}</ion-label>
        </ion-segment-button>
      </ion-segment>
      <ion-button
        fill="clear"
        data-testid="website-preview-reload"
        :aria-label="t('website.preview.reload')"
        @click="reload"
      >
        <HubIcon
          slot="icon-only"
          name="ion:refresh-outline"
        />
      </ion-button>
    </div>
    <div
      class="wp-stage"
      :class="`wp-stage--${width}`"
    >
      <iframe
        :key="src"
        class="wp-frame"
        :src="src"
        :title="t('website.preview.frame')"
        data-testid="website-preview-frame"
        @load="loaded"
      />
      <div
        v-if="loading"
        class="wp-overlay"
        data-testid="website-preview-loading"
      >
        <ion-spinner name="crescent" />
      </div>
      <div
        v-else-if="failed"
        class="wp-overlay wp-overlay--error"
        role="alert"
        data-testid="website-preview-error"
      >
        <HubIcon name="ion:warning-outline" />
        <p>{{ t('website.loadError') }}</p>
        <ion-button
          size="small"
          @click="reload"
        >
          {{ t('website.preview.reload') }}
        </ion-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wp {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 480px;
}
.wp-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.wp-bar ion-segment {
  max-width: 320px;
}
.wp-stage {
  position: relative;
  flex: 1;
  display: flex;
  justify-content: center;
  border-radius: 12px;
  background: var(--ion-color-step-50, #f2f2f2);
  overflow: hidden;
}
.wp-frame {
  width: 100%;
  height: 100%;
  min-height: 480px;
  border: 0;
  background: #fff;
}
.wp-stage--mobile .wp-frame {
  width: 390px;
  max-width: 100%;
  border-inline: 1px solid var(--ion-color-step-150, #d9d9d9);
}
.wp-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: color-mix(in srgb, var(--ion-background-color, #fff) 70%, transparent);
}
.wp-overlay--error {
  color: var(--ion-color-danger);
  background: var(--ion-background-color, #fff);
}
</style>
