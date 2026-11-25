<script setup lang="ts">
// QrSheet (ONLINE_ORDER-F02): the paper the tables' QR codes are printed on, three cards to a row, each one to cut out
// along its dashed edge and leave on its table: «Scan to order», the QR, the table's number and its zone. Only the
// tables with a code and a drawn QR are on it. Black on white whatever the theme, so every phone reads the print.
import { computed } from 'vue';

import type { TableCodeOut } from '../operations';

const props = defineProps<{
  rows: readonly TableCodeOut[];
  /** The drawn QR of each table's address (`useQrImages`). */
  images: Readonly<Record<string, string>>;
}>();

const cards = computed(() =>
  props.rows.flatMap((row) => {
    const image = row.url ? props.images[row.url] : undefined;
    return image ? [{ row, image }] : [];
  }),
);
</script>

<template>
  <section
    class="qr-sheet"
    data-testid="online-order-qr-sheet"
  >
    <article
      v-for="{ row, image } in cards"
      :key="row.table_id"
      class="qr-sheet__card"
      data-testid="online-order-qr-sheet-card"
    >
      <p class="qr-sheet__scan">
        {{ $t('online_order.sheet.scan') }}
      </p>
      <img
        class="qr-sheet__code"
        :src="image"
        :alt="$t('online_order.sheet.alt', { table: row.table })"
      >
      <p class="qr-sheet__table">
        {{ $t('online_order.sheet.table', { number: row.number }) }}
      </p>
      <p
        v-if="row.zone_name"
        class="qr-sheet__zone"
      >
        {{ row.zone_name }}
      </p>
    </article>
  </section>
</template>

<style scoped>
@page online-order-qr-sheet {
  size: A4;
  margin: 12mm;
}

.qr-sheet {
  page: online-order-qr-sheet;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4mm;
  color: #000;
  background: #fff;
  font-family: sans-serif;
}

.qr-sheet__card {
  break-inside: avoid;
  padding: 5mm 3mm;
  border: 0.3mm dashed #000;
  text-align: center;
}

.qr-sheet__card p {
  margin: 0;
}

.qr-sheet__scan,
.qr-sheet__zone {
  font-size: 11pt;
}

.qr-sheet__code {
  display: block;
  width: 45mm;
  height: 45mm;
  margin: 2mm auto;
}

.qr-sheet__table {
  font-size: 18pt;
  font-weight: 700;
}
</style>
