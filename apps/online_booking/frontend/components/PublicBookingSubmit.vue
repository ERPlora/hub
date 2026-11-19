<script setup lang="ts">
import { IonButton, IonSpinner } from '@ionic/vue';
import { openExternalLink } from '@erplora/ui/shell';
import { computed, useId } from 'vue';
import './booking-flow.css';

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
