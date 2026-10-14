<script setup lang="ts">
// The notices above the till's grid (SALE-F07). The state of the catalogue, a quiet sentence: how many
// articles cannot be sold for lack of VAT (counted on the server: one row asked, its total read), with
// «Review the catalogue» — to Inventory's unconfigured products — only for whoever can fix it. And
// the reason of the last tap on a blocked tile, boxed, where the cashier is looking. When Inventory is
// off the count cannot be read and the grid itself says why.
import { useLive } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

import { useT } from '../../composables/useT';

defineProps<{ tapNotice: string | null }>();

const t = useT();
const router = useRouter();
const session = useSession();
const canFix = computed(() => session.can('inventory.change_product'));

const { data, error } = useLive('inventory.product.list', { needs_tax_setup: true, is_active: true, limit: 1, offset: 0 });

const blocked = computed(() => (error.value ? 0 : (data.value?.total ?? 0)));
const sentence = computed(() =>
  blocked.value === 1 ? t('sale.pos.catalogBlockedOne') : t('sale.pos.catalogBlocked', { count: blocked.value }),
);

function review(): void {
  void router.push({ path: '/inventory/products', query: { status: 'unconfigured' } });
}
</script>

<template>
  <p
    v-if="tapNotice"
    class="pos-notice pos-notice--box"
    role="status"
    data-testid="pos-tap-notice"
  >
    <HubIcon name="ion:alert-circle" />
    <span>{{ tapNotice }}</span>
  </p>
  <p
    v-if="blocked > 0"
    class="pos-notice"
    role="status"
    data-testid="pos-catalog-health"
  >
    <HubIcon name="ion:alert-circle" />{{ sentence }}<ion-button
      v-if="canFix"
      fill="clear"
      size="small"
      class="pos-notice__fix"
      data-testid="pos-catalog-health-fix"
      @click="review"
    >
      {{ $t('sale.pos.catalogBlockedFix') }}
    </ion-button>
  </p>
</template>

<style scoped>
.pos-notice {
  display: block;
  margin: 0 0 0.5rem;
  padding: 0 0.1rem;
  font-size: 0.8rem;
  line-height: 1.35;
  color: var(--ion-color-medium, #8b897f);
}
.pos-notice :deep(ion-icon) {
  display: inline-block;
  margin-right: 0.3rem;
  font-size: 1rem;
  vertical-align: -0.15em;
  color: var(--ion-color-warning-shade, #e0ac08);
}
.pos-notice__fix {
  display: inline-block;
  height: 1.5rem;
  margin: 0;
  font-size: 0.8rem;
  letter-spacing: 0;
  text-transform: none;
  vertical-align: -0.35em;
  --padding-start: 0.25rem;
  --padding-end: 0.25rem;
}
.pos-notice--box {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.6rem;
  font-size: 0.82rem;
  line-height: 1.25;
  color: var(--ion-text-color, #1c1b18);
  background: color-mix(in srgb, var(--ion-color-warning, #ffc409) 16%, transparent);
  border: 1px solid var(--ion-color-warning, #ffc409);
  border-radius: 14px;
}
.pos-notice--box :deep(ion-icon) {
  flex: none;
  margin: 0;
}
</style>
