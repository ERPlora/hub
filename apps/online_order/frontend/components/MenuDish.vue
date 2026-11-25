<script setup lang="ts">
// One line of a table's menu: a dish or a set menu, with its photo when it has one, what it is, its allergens and its
// price. The whole line is one touch, which opens it.
import { AllergenRow, formatMoney, type Money } from '@erplora/ui/components';
import { IonItem, IonLabel, IonNote, IonThumbnail } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../../../../base/frontend/lib/i18n';

const props = defineProps<{
  name: string;
  detail: string;
  price: number;
  imageUrl: string;
  allergens: string[];
  money: Money | undefined;
  testid: string;
}>();
defineEmits<{ open: [] }>();

const { t, locale } = useBaseI18n();
// The Hub serves the photos itself: only an address of its own is drawn.
const photo = computed(() => (props.imageUrl.startsWith('/') && !props.imageUrl.startsWith('//') ? props.imageUrl : ''));
</script>

<template>
  <ion-item
    button
    detail
    :data-testid="testid"
    @click="$emit('open')"
  >
    <ion-thumbnail
      v-if="photo"
      slot="start"
    >
      <img
        :src="photo"
        :alt="t('online_order.menu.photo', { name })"
        loading="lazy"
      >
    </ion-thumbnail>
    <ion-label class="ion-text-wrap">
      <h3>{{ name }}</h3>
      <p v-if="detail">
        {{ detail }}
      </p>
      <AllergenRow :codes="allergens" />
    </ion-label>
    <ion-note slot="end">
      {{ formatMoney(price, locale, money) }}
    </ion-note>
  </ion-item>
</template>

