<script setup lang="ts">
// The «VeriFactu receipt» card of an open invoice (INVOICE-F17 with VERIFACTU-F19; the old detail's card): the
// state of its registration record at the AEAT, its CSV once the AEAT answered, the record's QR and «Check at the
// tax agency ↗», which opens the AEAT's page (the QR's own address) in another tab; a record of the AEAT's test
// environment says so. Every value is VeriFactu's: the page hands it the record it follows.
import { StatusPill, type StatusPillTone } from '@erplora/ui/components';
import type { OutputOf } from '@erplora/ui/sdk';
import { computed } from 'vue';

type FiscalRecord = NonNullable<OutputOf<'verifactu.record.by_invoice'>['record']>;

const props = defineProps<{ record: FiscalRecord }>();

const TONES: Record<string, StatusPillTone> = {
  accepted: 'success',
  accepted_with_errors: 'warning',
  rejected: 'danger',
  sent: 'info',
};
const tone = computed<StatusPillTone>(() => TONES[props.record.status] ?? 'neutral');
</script>

<template>
  <section
    class="verifactu-receipt"
    data-testid="invoice-verifactu"
  >
    <div class="verifactu-receipt__head">
      <h3>{{ $t('invoice.verifactu.heading') }}</h3>
      <StatusPill
        data-testid="invoice-verifactu-status"
        :tone="tone"
        :label="$t(`invoice.verifactu.status.${record.status}`)"
      />
      <span
        v-if="record.environment === 'testing'"
        class="verifactu-receipt__testing"
        data-testid="invoice-verifactu-testing"
      >{{ $t('invoice.verifactu.testing') }}</span>
    </div>
    <div class="verifactu-receipt__body">
      <img
        class="verifactu-receipt__qr"
        data-testid="invoice-verifactu-qr"
        :src="record.qr_svg"
        :alt="$t('invoice.verifactu.qrAlt')"
      >
      <div class="verifactu-receipt__text">
        <p
          v-if="record.csv"
          data-testid="invoice-verifactu-csv"
        >
          {{ $t('invoice.verifactu.csv', { csv: record.csv }) }}
        </p>
        <a
          :href="record.qr_url"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="invoice-verifactu-check"
        >{{ $t('invoice.verifactu.check') }}</a>
      </div>
    </div>
  </section>
</template>

<style scoped>
.verifactu-receipt {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: var(--ep-radius-sm, 10px);
  padding: 1rem;
  margin: 0 0 1rem;
  background: var(--ion-card-background, #fffdf7);
}
.verifactu-receipt__head {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.verifactu-receipt__head h3 {
  margin: 0;
  font-size: 1rem;
}
.verifactu-receipt__testing {
  font-size: 0.8rem;
  color: var(--ion-color-medium, #8a8577);
}
.verifactu-receipt__body {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  margin-top: 0.75rem;
}
.verifactu-receipt__qr {
  width: 7.5rem;
  height: 7.5rem;
  flex: none;
}
.verifactu-receipt__text {
  min-width: 0;
  word-break: break-word;
}
.verifactu-receipt__text p {
  margin: 0 0 0.5rem;
}
.verifactu-receipt__text a {
  color: var(--ion-color-primary, #3880ff);
  font-weight: 600;
  text-decoration: none;
}
</style>
