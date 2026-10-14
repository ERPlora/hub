<script setup lang="ts">
// The preview of the till's customer search, on the dev server only (routes.ts): CustomerSearch as
// the Sales app will mount it in its sale screen, and what it hands the sale, so it can be driven end
// to end (e2e) before Sales exists. Never part of a production build.
import { AppPage } from '@erplora/ui/shell';
import { ref } from 'vue';

import CustomerSearch, { type CustomerSnapshot } from '../components/CustomerSearch.vue';

const customer = ref<CustomerSnapshot | null>(null);
const open = ref(false);
</script>

<template>
  <AppPage
    :title="$t('customer.playground.title')"
    content-layout="detail"
  >
    <p>{{ $t('customer.playground.intro') }}</p>
    <CustomerSearch
      v-model="customer"
      v-model:open="open"
    />
    <dl
      v-if="customer"
      class="customer-preview"
      data-testid="customer-preview-snapshot"
    >
      <template
        v-for="(text, key) in customer"
        :key="key"
      >
        <dt>{{ key }}</dt>
        <dd>{{ text }}</dd>
      </template>
    </dl>
    <p
      v-else
      class="customer-preview__none"
      data-testid="customer-preview-none"
    >
      {{ $t('customer.playground.none') }}
    </p>
  </AppPage>
</template>

<style scoped>
.customer-preview {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
  margin-top: 1rem;
}

.customer-preview dt {
  font-family: ui-monospace, monospace;
  opacity: 0.6;
}

.customer-preview dd {
  margin: 0;
  font-weight: 600;
}

.customer-preview__none {
  margin-top: 1rem;
  opacity: 0.7;
}
</style>
