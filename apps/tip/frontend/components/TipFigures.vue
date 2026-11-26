<script setup lang="ts">
// The four figures of some tips — in all, by card, in cash and any other way — as a row of figure cards, the total
// saying how many tips it adds up.
import { StatCard, type StatCardTone } from '@erplora/ui/components';
import { computed } from 'vue';

import { useLocale, useT } from '../../../sale/frontend/composables/useT';
import { formatMoney } from '../../../sale/frontend/lib/format';
import { useBusinessMoney } from '../../../../base/frontend/lib/money';
import type { TipFiguresOut } from '../operations';

const props = defineProps<{
  /** None while they load. */
  figures: TipFiguresOut | null | undefined;
  /** The row's hook; each card's is `<testid>-<figure>`. */
  testid: string;
}>();

type Figure = 'total' | 'card' | 'cash' | 'other';

const SHOWN: readonly { id: Figure; icon: string; tone: StatCardTone }[] = [
  { id: 'total', icon: 'ion:wallet-outline', tone: 1 },
  { id: 'card', icon: 'ion:card-outline', tone: 2 },
  { id: 'cash', icon: 'ion:cash-outline', tone: 3 },
  { id: 'other', icon: 'ion:swap-horizontal-outline', tone: 4 },
];

const t = useT();
const locale = useLocale();
const money = useBusinessMoney();

const cards = computed(() => {
  const shown = props.figures;
  return SHOWN.map(({ id, icon, tone }) => ({
    id,
    icon,
    tone,
    label: t(`tip.figures.${id}`),
    value: shown ? formatMoney(shown[id], locale.value, money.value) : null,
    note: shown && id === 'total' ? t('tip.figures.count', { count: shown.count }) : undefined,
  }));
});
</script>

<template>
  <div
    class="ep-stat-grid"
    :data-testid="testid"
  >
    <StatCard
      v-for="card in cards"
      :key="card.id"
      :label="card.label"
      :value="card.value"
      :icon="card.icon"
      :tone="card.tone"
      :note="card.note"
      :loading="!figures"
      :testid="`${testid}-${card.id}`"
    />
  </div>
</template>
