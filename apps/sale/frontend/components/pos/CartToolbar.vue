<script setup lang="ts">
// The bar on top of the check, left to right: «Park this check» (only where parked tickets are
// allowed; nothing to park on an empty check), the slot where the Customers app's button sits, a
// spacer, «Open checks» with how many others are open, and — in the phone's drawer — «Close».
// Icons the product had that are not registered yet (`pause-circle-outline`) use the closest one
// (UI-REQUESTS.md, «POS»).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';

defineProps<{
  parkingEnabled: boolean;
  hasLines: boolean;
  /** Open checks besides the one on screen. */
  openChecks: number;
  checksOpen: boolean;
  /** The check is the phone's drawer: it has its «Close». */
  drawer: boolean;
}>();
const emit = defineEmits<{ park: []; toggleChecks: []; close: [] }>();
</script>

<template>
  <div class="pos-toolbar">
    <ion-button
      v-if="parkingEnabled"
      fill="clear"
      class="pos-toolbar__icon"
      data-testid="pos-park"
      :disabled="!hasLines"
      :title="$t('sale.pos.parkCurrentSale')"
      :aria-label="$t('sale.pos.parkCurrentSale')"
      @click="emit('park')"
    >
      <HubIcon
        slot="icon-only"
        name="ion:time-outline"
      />
    </ion-button>
    <div class="pos-toolbar__slot">
      <slot />
    </div>
    <span class="pos-toolbar__spacer" />
    <ion-button
      fill="clear"
      class="pos-toolbar__icon pos-toolbar__checks"
      data-testid="pos-open-checks"
      :title="$t('sale.pos.parkedTickets')"
      :aria-label="$t('sale.pos.parkedTickets')"
      :aria-expanded="checksOpen ? 'true' : 'false'"
      @click="emit('toggleChecks')"
    >
      <HubIcon
        slot="icon-only"
        name="ion:receipt-outline"
      />
    </ion-button>
    <span
      v-if="openChecks > 0"
      class="pos-toolbar__badge"
      data-testid="pos-open-checks-count"
      aria-hidden="true"
    >{{ openChecks }}</span>
    <ion-button
      v-if="drawer"
      fill="clear"
      class="pos-toolbar__icon"
      data-testid="pos-cart-close"
      :title="$t('sale.pos.closeAction')"
      :aria-label="$t('sale.pos.closeAction')"
      @click="emit('close')"
    >
      <HubIcon
        slot="icon-only"
        name="ion:chevron-forward-outline"
      />
    </ion-button>
  </div>
</template>

<style scoped>
.pos-toolbar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.2rem;
  min-height: 3.6rem;
  padding: 0 0.45rem;
  border-bottom: 1px solid var(--ion-border-color, #e6e3db);
  --pos-hdr-icon-size: 1.75rem;
}
.pos-toolbar__icon {
  width: 2.6rem;
  /* Ionic's icon-only button grows to 2.125em of its icon (60px here), past this width: on a phone the bar
     overflowed and «Assign customer» sat on «Open checks». */
  min-width: 2.6rem;
  height: 2.6rem;
  margin: 0;
  font-size: var(--pos-hdr-icon-size);
  --padding-start: 0.3rem;
  --padding-end: 0.3rem;
  --color: var(--ion-text-color, #1c1b18);
}
.pos-toolbar__slot {
  display: flex;
  align-items: center;
  min-width: 0;
}
.pos-toolbar__spacer {
  flex: 1;
}
.pos-toolbar__badge {
  position: relative;
  min-width: 1.1rem;
  height: 1.1rem;
  margin-left: -1rem;
  margin-top: -1.4rem;
  padding: 0 0.25rem;
  font-size: 0.62rem;
  font-weight: 800;
  line-height: 1.1rem;
  text-align: center;
  color: var(--ion-color-primary-contrast, #fff);
  background: var(--ion-color-primary, #0091ce);
  border-radius: 999px;
  pointer-events: none;
}
</style>
