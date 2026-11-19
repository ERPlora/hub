<script setup lang="ts">
import { IonButton, IonSpinner } from '@ionic/vue';
import { openExternalLink } from '@erplora/ui/shell';
import { computed, useId } from 'vue';

import { useT } from '../composables/useT';

const props = defineProps<{
  businessName: string;
  privacyPolicyUrl: string;
  ready: boolean;
  pending: boolean;
}>();
const emit = defineEmits<{ submit: [] }>();
const website = defineModel<string>('website', { required: true });
const t = useT();
const trapId = useId();
const business = computed(() => props.businessName || t('online_booking.door.businessFallback'));

function typed(event: Event): void {
  website.value = (event.target as HTMLInputElement).value;
}
</script>

<template>
  <div class="ob-public-submit">
    <p
      class="ob-public-submit__privacy"
      data-testid="ob-preview-privacy"
    >
      {{ $t('online_booking.door.privacy', { business }) }}
      <a
        :href="privacyPolicyUrl"
        target="_blank"
        rel="noopener noreferrer"
        @click="openExternalLink(privacyPolicyUrl, $event)"
      >{{ $t('online_booking.door.privacyLink') }}</a>.
    </p>
    <div
      class="ob-public-submit__trap"
      data-testid="ob-preview-trap"
      aria-hidden="true"
      hidden
    >
      <label :for="trapId">{{ $t('online_booking.door.website') }}</label>
      <input
        :id="trapId"
        data-testid="ob-preview-trap-input"
        name="website"
        type="text"
        :value="website"
        :tabindex="-1"
        autocomplete="off"
        @input="typed"
      >
    </div>
    <ion-button
      class="ob-public-submit__button"
      data-testid="ob-preview-book"
      type="button"
      :disabled="!ready || pending"
      @click="emit('submit')"
    >
      <ion-spinner
        v-if="pending"
        name="crescent"
      />
      {{ $t('online_booking.preview.book') }}
    </ion-button>
  </div>
</template>

<style scoped>
.ob-public-submit {
  display: grid;
  gap: 12px;
}
.ob-public-submit__privacy {
  margin: 0;
  color: var(--ep-text-muted);
  font-size: 0.85rem;
  line-height: 1.5;
}
.ob-public-submit__privacy a {
  color: var(--ion-color-primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.ob-public-submit__trap {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.ob-public-submit__button {
  justify-self: start;
}
@media (max-width: 576px) {
  .ob-public-submit__button {
    width: 100%;
  }
}
</style>
