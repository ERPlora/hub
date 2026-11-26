<script setup lang="ts">
import { computed } from 'vue';

import { ownImageUrl } from '../../../../base/frontend/lib/own-image';
import { useT } from '../composables/useT';
import type { PageOut } from '../operations';

type HeaderInfo = Pick<PageOut, 'business_name' | 'logo_url'> &
  Partial<Pick<PageOut, 'title' | 'welcome_message'>>;

const props = defineProps<{ info: HeaderInfo }>();
const t = useT();
const logoAlt = computed(() => t('online_booking.door.logoAlt', { business: props.info.business_name || props.info.title || t('online_booking.door.businessFallback') }));
const logoUrl = computed(() => ownImageUrl(props.info.logo_url));
</script>

<template>
  <header class="ob-business">
    <img
      v-if="logoUrl"
      class="ob-business__logo"
      data-testid="ob-preview-business-logo"
      :src="logoUrl"
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
        v-if="info.title"
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

<style scoped>
.ob-business {
  display: flex;
  align-items: center;
  gap: 16px;
}
.ob-business__logo {
  width: 80px;
  height: 80px;
  flex: 0 0 auto;
  object-fit: contain;
  border-radius: var(--ep-radius-md);
  background: var(--ep-surface-muted);
  padding: 8px;
}
.ob-business__copy {
  min-width: 0;
}
.ob-business__name {
  margin: 0 0 4px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.ob-business__title {
  margin: 0;
}
.ob-business__welcome {
  margin: 8px 0 0;
  color: var(--ep-text-muted);
  white-space: pre-line;
}
@media (max-width: 576px) {
  .ob-business {
    align-items: flex-start;
    gap: 12px;
  }
  .ob-business__logo {
    width: 64px;
    height: 64px;
  }
}
</style>
