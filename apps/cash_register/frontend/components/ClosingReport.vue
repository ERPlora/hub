<script setup lang="ts">
// The shift report on paper (CASH_REGISTER-F16; the market's X and Z reports): «Cash closing (Z)» for a
// closed session, «Partial report (X)» for an open one, with its number and the very figures the detail
// shows (one list for both). The detail page prints it with `printPaper`; on screen it stays hidden. The
// time it was printed is the page's to give, at the moment of printing.
import { formatDateTime } from '@erplora/ui/components';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { useBusinessMoney } from '../lib/money';
import { summaryItems } from '../lib/summary';
import type { SessionOut } from '../operations';

const props = withDefaults(defineProps<{ session: SessionOut; printedAt?: Date | null }>(), { printedAt: null });

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const items = computed(() => summaryItems(props.session, t, locale.value, (iso) => formatDateTime(iso, locale.value), business.value));
const printedOn = computed(() => (props.printedAt ? formatDateTime(props.printedAt, locale.value) : ''));
</script>

<template>
  <section
    class="cash-report"
    data-testid="cash-register-report"
  >
    <h1
      class="cash-report__title"
      data-testid="cash-register-report-title"
    >
      {{ session.status === 'closed' ? $t('cash_register.report.z') : $t('cash_register.report.x') }}
    </h1>
    <p class="cash-report__number">
      {{ $t('cash_register.report.session') }} {{ session.number }}
    </p>
    <dl class="cash-report__lines">
      <div
        v-for="item in items"
        :key="item.key"
        class="cash-report__line"
      >
        <dt>{{ item.label }}</dt>
        <dd>{{ item.value }}</dd>
      </div>
    </dl>
    <p
      v-if="printedOn"
      class="cash-report__printed"
    >
      {{ $t('cash_register.report.printedAt', { when: printedOn }) }}
    </p>
  </section>
</template>

<style scoped>
/* A receipt-width paper, black on white, for the browser's print dialog. */
.cash-report {
  width: 72mm;
  padding: 4mm;
  color: #000;
  background: #fff;
  font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
  font-size: 11px;
}
.cash-report__title {
  margin: 0 0 2mm;
  font-size: 14px;
  text-align: center;
}
.cash-report__number {
  margin: 0 0 3mm;
  text-align: center;
}
.cash-report__lines {
  margin: 0;
}
.cash-report__line {
  display: flex;
  justify-content: space-between;
  gap: 2mm;
  border-bottom: 1px dashed #999;
  padding: 1mm 0;
}
.cash-report__line dd {
  margin: 0;
  text-align: right;
}
.cash-report__printed {
  margin: 3mm 0 0;
  text-align: center;
}
</style>
