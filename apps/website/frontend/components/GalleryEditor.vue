<script setup lang="ts">
// GalleryEditor — the photos of the website's gallery, the way Squarespace's and Wix's gallery blocks take them: up
// to twelve, in the order the page shows them. Each photo is its own ImageUpload (replace or remove it), with an arrow
// to move it up and one to move it down; while there is room, one more ImageUpload adds a photo at the end. Uploads go
// through `upload` (the editor's `website.image.upload`); `v-model` is the whole list and every change emits a new one.
import { ImageUpload, type ImageUploader, type ImageUploadValue } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonNote } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import type { ImageRef } from '../operations';

/** The most photos the gallery takes (schemas.MAX_GALLERY_IMAGES). */
const MAX_PHOTOS = 12;

const props = withDefaults(
  defineProps<{
    modelValue: ImageRef[];
    upload: ImageUploader;
    disabled?: boolean;
    /** The server's refusal of one of these photos, if any. */
    error?: string;
  }>(),
  { disabled: false, error: undefined },
);

const emit = defineEmits<{ 'update:modelValue': [value: ImageRef[]] }>();

const t = useT();
const room = computed(() => props.modelValue.length < MAX_PHOTOS);

function emitPhotos(photos: ImageRef[]): void {
  if (!props.disabled) emit('update:modelValue', photos);
}

/** The photo at `index` replaced by `value`, or taken out when `value` is null. */
function change(index: number, value: ImageUploadValue | null): void {
  const photos = [...props.modelValue];
  if (value) photos.splice(index, 1, { id: value.id, url: value.url });
  else photos.splice(index, 1);
  emitPhotos(photos);
}

function add(value: ImageUploadValue | null): void {
  if (value) emitPhotos([...props.modelValue, { id: value.id, url: value.url }]);
}

/** The photo at `index` one place up (`-1`) or down (`1`); nothing past either end. */
function move(index: number, step: -1 | 1): void {
  const target = index + step;
  if (target < 0 || target >= props.modelValue.length) return;
  const photos = [...props.modelValue];
  [photos[index], photos[target]] = [photos[target], photos[index]];
  emitPhotos(photos);
}
</script>

<template>
  <div
    class="wg"
    role="group"
    :aria-label="t('website.gallery.label')"
  >
    <ion-note
      class="wg-count"
      data-testid="website-gallery-count"
    >
      {{ t('website.gallery.count', { n: modelValue.length, max: MAX_PHOTOS }) }}
    </ion-note>
    <p
      v-if="!modelValue.length"
      class="wg-empty"
      data-testid="website-gallery-empty"
    >
      {{ t('website.gallery.empty') }}
    </p>
    <div
      v-for="(photo, index) in modelValue"
      :key="`${index}:${photo.id}`"
      class="wg-row"
      :data-testid="`website-gallery-photo-${index}-row`"
    >
      <ImageUpload
        class="wg-upload"
        :model-value="photo"
        :label="t('website.gallery.photo', { n: index + 1 })"
        :upload="upload"
        :disabled="disabled"
        :testid="`website-gallery-photo-${index}`"
        @update:model-value="change(index, $event)"
      />
      <div class="wg-move">
        <ion-button
          fill="clear"
          color="medium"
          :aria-label="t('website.gallery.up')"
          :data-testid="`website-gallery-photo-${index}-up`"
          :disabled="disabled || index === 0"
          @click="move(index, -1)"
        >
          <HubIcon
            slot="icon-only"
            name="ion:chevron-up-outline"
          />
        </ion-button>
        <ion-button
          fill="clear"
          color="medium"
          :aria-label="t('website.gallery.down')"
          :data-testid="`website-gallery-photo-${index}-down`"
          :disabled="disabled || index === modelValue.length - 1"
          @click="move(index, 1)"
        >
          <HubIcon
            slot="icon-only"
            name="ion:chevron-down-outline"
          />
        </ion-button>
      </div>
    </div>
    <ImageUpload
      v-if="room && !disabled"
      :key="modelValue.length"
      :model-value="null"
      :label="t('website.gallery.add')"
      :upload="upload"
      testid="website-gallery-add"
      @update:model-value="add"
    />
    <p
      v-else-if="!room"
      class="wg-empty"
      data-testid="website-gallery-full"
    >
      {{ t('website.gallery.full', { max: MAX_PHOTOS }) }}
    </p>
    <p
      v-if="error"
      class="wg-error"
      role="alert"
      data-testid="website-gallery-error"
    >
      {{ error }}
    </p>
  </div>
</template>

<style scoped>
.wg {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wg-count {
  display: block;
  padding: 8px 16px 0;
}
.wg-empty {
  color: var(--ion-color-medium);
  font-size: 0.875rem;
  margin: 4px 16px;
}
.wg-row {
  display: flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px solid var(--ion-color-step-100, #e6e6e6);
}
.wg-upload {
  flex: 1;
  min-width: 0;
}
.wg-move {
  display: flex;
  flex-direction: column;
}
.wg-error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
  margin: 4px 16px;
}
</style>
