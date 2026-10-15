<script setup lang="ts">
// The sheet a voucher's lists open over the packages table (WORKBOOK «Bonos y paquetes · Hojas»): its
// title and what it shows on top, its rows (the slot), «Close», and «Load more» with «Showing {shown} of
// {total}» while there are more. Loading, empty and error states are the slot's.
import { IonButton, IonButtons, IonContent, IonHeader, IonModal, IonTitle, IonToolbar } from '@ionic/vue';

import { useT } from '../composables/useT';

withDefaults(
  defineProps<{
    title: string;
    hint?: string;
    /** Prefix of the hooks: `<testid>`, `-title`, `-hint`, `-close`, `-count`, `-more`. */
    testid: string;
    /** Rows on screen and rows in all, for «Load more». */
    shown: number;
    total: number;
    /** The count's text (`{shown}`, `{total}`). */
    countKey?: string;
  }>(),
  { hint: undefined, countKey: 'service.showing' },
);
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ more: [] }>();

const t = useT();
</script>

<template>
  <ion-modal
    :is-open="open"
    :data-testid="testid"
    @did-dismiss="open = false"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title :data-testid="`${testid}-title`">
          {{ title }}
        </ion-title>
        <ion-buttons slot="end">
          <ion-button
            :data-testid="`${testid}-close`"
            @click="open = false"
          >
            {{ t('service.close') }}
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <p
        v-if="hint"
        class="sheet-modal__hint"
        :data-testid="`${testid}-hint`"
      >
        {{ hint }}
      </p>
      <slot />
      <div
        v-if="shown < total"
        class="sheet-modal__more"
      >
        <span :data-testid="`${testid}-count`">{{ t(countKey, { shown, total }) }}</span>
        <ion-button
          :data-testid="`${testid}-more`"
          fill="clear"
          expand="block"
          @click="emit('more')"
        >
          {{ t('service.loadMore') }}
        </ion-button>
      </div>
    </ion-content>
  </ion-modal>
</template>

<style scoped>
.sheet-modal__hint {
  margin: 0 0 12px;
  font-size: 0.9rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.sheet-modal__more {
  display: grid;
  justify-items: center;
  gap: 4px;
  margin-top: 12px;
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
