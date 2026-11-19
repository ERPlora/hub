<script setup lang="ts">
import { computed } from 'vue';
import './booking-flow.css';

import { useT } from '../composables/useT';
import type { PageOut } from '../operations';

const props = defineProps<{ info: PageOut }>();
const t = useT();
const logoAlt = computed(() => t('online_booking.door.logoAlt', { business: props.info.business_name || props.info.title }));
</script>

<template>
  <header class="ob-business">
    <img
      v-if="info.logo_url"
      class="ob-business__logo"
      data-testid="ob-preview-business-logo"
      :src="info.logo_url"
      :alt="logoAlt"
      width="80"
      height="80"
    >
    <div class="ob-business__copy">
      <p
        v-if="info.business_name"
        class="ob-business__name"
        data-testid="ob-preview-business-name"
      >
        {{ info.business_name }}
      </p>
      <h3
        class="ob-business__title"
        data-testid="ob-preview-title"
      >
        {{ info.title }}
      </h3>
      <p
        v-if="info.welcome_message"
        class="ob-business__welcome"
      >
        {{ info.welcome_message }}
      </p>
    </div>
  </header>
</template>
