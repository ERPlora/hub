<script setup lang="ts">
// Price Lists (WORKBOOK «Pantallas · Tarifas»): the old module's one screen, «Price lists» on top and
// «Discount rules» under it, each its own live table (PRICING-F01 to F05, F09 to F12). A list opens its
// detail with its prices (ListDetailPage).
import { AppPage } from '@erplora/ui/shell';

import PriceListsTable from '../components/PriceListsTable.vue';
import RulesTable from '../components/RulesTable.vue';
</script>

<template>
  <AppPage :title="$t('pricing.title')">
    <div class="pricing-page">
      <h2 class="pricing-page__heading">
        {{ $t('pricing.lists.heading') }}
      </h2>
      <PriceListsTable />
      <h2 class="pricing-page__heading">
        {{ $t('pricing.rules.heading') }}
      </h2>
      <RulesTable />
    </div>
  </AppPage>
</template>

<style scoped>
.pricing-page {
  display: grid;
  gap: 8px;
}
.pricing-page__heading {
  margin: 0.5rem 0 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--ion-color-medium, #5c594f);
}
</style>
