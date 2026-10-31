<script setup lang="ts">
// «Photo» of a product's, a service's or a set menu's form (INVENTORY-F30/F31, SERVICE-F34/F35, COMBO-F14), the way
// Square's and Shopify's item editors ask for it: the photo (or the item's initials, «No photo: its initials are
// shown»), «Choose from the library» and «Upload photo» while it has none, «Change» (the library, which offers an
// upload too) and «Remove photo» once it has one. `v-model` is the form's draft (`ImageDraft`): an image of the shared
// library, a photo of its own read on the device (shown at once, in base64 for `upload_image`), or none. Nothing is
// sent from here: the form sends the step once the record is saved (`useImageSave`). A file past 2 MB or that is not
// a JPG, PNG or WebP says why next to «Photo» and changes nothing, as the server would. Hooks (`testid`): the root,
// `-label`, `-preview`, `-none`, `-library`, `-upload`, `-change`, `-remove`, `-rules`, `-error`, `-file`, and the
// library's under `-library-modal`.
import { IonButton, IonNote } from '@ionic/vue';
import { ref, shallowRef } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import { type ImageDraft, readPhoto } from '../lib/item-image';
import type { CatalogImage } from '../operations';
import ImageLibraryModal from './ImageLibraryModal.vue';
import ItemImage from './ItemImage.vue';

const props = withDefaults(
  defineProps<{
    modelValue: ImageDraft;
    /** The item's name: its initials, and what the library searches first. */
    name: string;
    /** The library's sectors that go first (a service's: Hair and Beauty). */
    folders?: readonly string[];
    /** The form is saving: nothing changes meanwhile. */
    disabled?: boolean;
    testid: string;
  }>(),
  { folders: () => [], disabled: false },
);
const emit = defineEmits<{ 'update:modelValue': [value: ImageDraft] }>();

const { t } = useBaseI18n();

const picker = shallowRef<HTMLInputElement | null>(null);
const libraryOpen = ref(false);
const reading = ref(false);
const error = ref('');

const tid = (part: string) => `${props.testid}-${part}`;
const locked = () => props.disabled || reading.value;

function openLibrary(): void {
  if (locked()) return;
  libraryOpen.value = true;
}

/** The device's picker; the library's «Upload photo» comes here too, inside the person's tap. */
function choose(): void {
  if (locked()) return;
  picker.value?.click();
}

function pick(image: CatalogImage): void {
  error.value = '';
  emit('update:modelValue', { reference: image.reference, url: image.url, data: null });
}

function remove(): void {
  if (locked()) return;
  error.value = '';
  emit('update:modelValue', { reference: '', url: '', data: null });
}

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  // Ready for the next choice, the same file included.
  input.value = '';
  if (!file || locked()) return;
  error.value = '';
  reading.value = true;
  try {
    const read = await readPhoto(file);
    if (!read.ok) {
      error.value = t(read.reason === 'too_big' ? 'base.imageField.tooBig' : 'base.imageField.notAPhoto');
      return;
    }
    emit('update:modelValue', { reference: '', url: read.url, data: read.data });
  } finally {
    reading.value = false;
  }
}
</script>

<template>
  <div
    class="image-field"
    :data-testid="testid"
  >
    <span
      class="image-field__label"
      :data-testid="tid('label')"
    >{{ t('base.imageField.label') }}</span>
    <div class="image-field__row">
      <ItemImage
        class="image-field__preview"
        :src="modelValue.url"
        :name="name"
        :data-testid="tid('preview')"
      />
      <div class="image-field__side">
        <span
          v-if="!modelValue.url"
          class="image-field__none"
          :data-testid="tid('none')"
        >{{ t('base.imageField.none') }}</span>
        <div class="image-field__actions">
          <template v-if="!modelValue.url">
            <ion-button
              :data-testid="tid('library')"
              fill="outline"
              size="small"
              :disabled="disabled || reading"
              @click="openLibrary()"
            >
              {{ t('base.imageField.library') }}
            </ion-button>
            <ion-button
              :data-testid="tid('upload')"
              fill="outline"
              size="small"
              :disabled="disabled || reading"
              @click="choose()"
            >
              {{ t('base.imageField.upload') }}
            </ion-button>
          </template>
          <template v-else>
            <ion-button
              :data-testid="tid('change')"
              fill="outline"
              size="small"
              :disabled="disabled || reading"
              @click="openLibrary()"
            >
              {{ t('base.imageField.change') }}
            </ion-button>
            <ion-button
              :data-testid="tid('remove')"
              fill="clear"
              color="danger"
              size="small"
              :disabled="disabled || reading"
              @click="remove()"
            >
              {{ t('base.imageField.remove') }}
            </ion-button>
          </template>
        </div>
        <ion-note
          class="image-field__rules"
          :data-testid="tid('rules')"
        >
          {{ t('base.imageField.rules') }}
        </ion-note>
        <ion-note
          v-if="error"
          class="image-field__error"
          color="danger"
          role="alert"
          :data-testid="tid('error')"
        >
          {{ error }}
        </ion-note>
      </div>
    </div>
    <input
      ref="picker"
      class="image-field__file"
      type="file"
      accept="image/*"
      tabindex="-1"
      aria-hidden="true"
      :data-testid="tid('file')"
      @change="onFile"
    >
    <ImageLibraryModal
      v-model:open="libraryOpen"
      :query="name"
      :folders="folders"
      :testid="tid('library-modal')"
      @pick="pick"
      @upload="choose()"
    />
  </div>
</template>

<style scoped>
.image-field {
  display: grid;
  gap: 8px;
}
.image-field__label {
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.image-field__row {
  display: flex;
  align-items: center;
  gap: 16px;
}
.image-field__preview {
  flex: none;
  width: 96px;
  height: 96px;
  font-size: 1.8rem;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 14px;
}
.image-field__side {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.image-field__none {
  font-size: 0.85rem;
}
.image-field__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.image-field__actions ion-button {
  margin: 0;
}
.image-field__rules,
.image-field__error {
  font-size: 0.8rem;
}
.image-field__file {
  display: none;
}
</style>
