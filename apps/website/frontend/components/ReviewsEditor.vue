<script setup lang="ts">
// ReviewsEditor — the website's Google reviews section: the business on Google Maps (the link of its page there, the
// «Share» button's link or its Place ID; the server checks it and asks Google, never the browser) and a note that says
// whether Google's rating and reviews are there. `status` is the saved draft's (`website.site.get`); `changed` says
// the field holds a link not saved yet, which Google is asked about once it is.
import { useSession } from '@erplora/ui/shell';
import { IonInput, IonItem, IonNote } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import type { ReviewsStatusOut } from '../operations';

/** The field's placeholder, from the script: vue-tsc misreads a literal «https://» in a template attribute. */
const PLACEHOLDER = 'https://maps.app.goo.gl/…';

const props = withDefaults(
  defineProps<{
    modelValue: string;
    status: ReviewsStatusOut;
    changed?: boolean;
    disabled?: boolean;
    /** The server's refusal of the link, if any. */
    error?: string;
  }>(),
  { changed: false, disabled: false, error: undefined },
);

const emit = defineEmits<{ 'update:modelValue': [value: string] }>();

const t = useT();
const session = useSession();

const state = computed(() => (props.changed ? 'changed' : props.status.state));

const note = computed(() => {
  if (state.value !== 'ready') return t(`website.reviews.status.${state.value}`);
  const locale = session.me.value?.language ?? 'en';
  const rating = new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return t('website.reviews.status.ready', {
    rating: props.status.rating === null ? '–' : rating.format(props.status.rating),
    count: new Intl.NumberFormat(locale).format(props.status.count),
  });
});

function typed(value: unknown): void {
  if (!props.disabled) emit('update:modelValue', value === null || value === undefined ? '' : String(value));
}
</script>

<template>
  <ion-item>
    <ion-input
      data-testid="website-field-reviews-place_ref"
      type="url"
      :label="t('website.reviews.label')"
      label-placement="stacked"
      :helper-text="t('website.reviews.help')"
      :placeholder="PLACEHOLDER"
      :maxlength="500"
      :value="modelValue"
      :disabled="disabled"
      :error-text="error"
      :class="{ 'ion-invalid': !!error, 'ion-touched': !!error }"
      @ion-input="typed($event.detail.value)"
    />
  </ion-item>
  <ion-item lines="none">
    <ion-note
      data-testid="website-reviews-status"
      :data-state="state"
      :color="state === 'failed' ? 'danger' : state === 'ready' ? 'success' : 'medium'"
      role="status"
    >
      {{ note }}
    </ion-note>
  </ion-item>
</template>
