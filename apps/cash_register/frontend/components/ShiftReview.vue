<script setup lang="ts">
// The shift review of the close (CASH_REGISTER-F08; Toast's shift review): what is still open when the
// drawer closes — Sales' open checks, the kitchen tickets not served yet and the prints that did not come
// out, each with what names it. It warns, it never prevents: the page asks for a second press when there is
// pending work.
import { InlineFeedback } from '@erplora/ui/components';
import { computed } from 'vue';

const props = defineProps<{
  /** The reading is on its way. */
  checking: boolean;
  /** The reading failed: the review may be incomplete. */
  incomplete: boolean;
  /** Checks still open in Sales. */
  openChecks: number;
  /** Their titles, as Sales shows them. */
  labels: string[];
  /** Kitchen tickets not served yet (to cook or ready at the pass). */
  unserved: number;
  /** Their table or number, as the kitchen shows them. */
  unservedLabels: string[];
  /** Prints that did not come out (waiting or failed). */
  prints: number;
  /** The printing functions they wait in: receipt, kitchen, bar, label. */
  printUsages: string[];
  /** The first press already warned: the next one closes. */
  acknowledged: boolean;
}>();

const pending = computed(() => props.openChecks + props.unserved + props.prints);
</script>

<template>
  <p
    v-if="checking"
    class="shift-review__checking"
    data-testid="cash-register-review-checking"
  >
    {{ $t('cash_register.review.checking') }}
  </p>
  <InlineFeedback
    v-else-if="pending > 0"
    tone="warning"
    icon="alert-circle-outline"
    data-testid="cash-register-review"
    :heading="$t('cash_register.review.title')"
  >
    <ul class="shift-review__list">
      <li
        v-if="openChecks > 0"
        data-testid="cash-register-review-checks"
      >
        {{ $t('cash_register.review.openChecks', { count: openChecks }) }}
        <span
          v-if="labels.length"
          class="shift-review__labels"
        >{{ labels.join(' · ') }}</span>
      </li>
      <li
        v-if="unserved > 0"
        data-testid="cash-register-review-kitchen"
      >
        {{ $t('cash_register.review.unserved', { count: unserved }) }}
        <span
          v-if="unservedLabels.length"
          class="shift-review__labels"
        >{{ unservedLabels.join(' · ') }}</span>
      </li>
      <li
        v-if="prints > 0"
        data-testid="cash-register-review-prints"
      >
        {{ $t('cash_register.review.prints', { count: prints }) }}
        <span
          v-if="printUsages.length"
          class="shift-review__labels"
        >{{ printUsages.map((usage) => $t(`cash_register.review.usages.${usage}`)).join(' · ') }}</span>
      </li>
      <li v-if="incomplete">
        {{ $t('cash_register.review.unavailable') }}
      </li>
    </ul>
    <p
      v-if="acknowledged"
      class="shift-review__confirm"
      data-testid="cash-register-review-confirm"
    >
      {{ $t('cash_register.review.confirm') }}
    </p>
  </InlineFeedback>
  <InlineFeedback
    v-else-if="incomplete"
    tone="neutral"
    icon="help-circle-outline"
    data-testid="cash-register-review-unavailable"
  >
    {{ $t('cash_register.review.unavailable') }}
  </InlineFeedback>
</template>

<style scoped>
.shift-review__checking {
  margin: 0;
  opacity: 0.75;
}
.shift-review__list {
  margin: 0.25rem 0 0;
  padding-inline-start: 1.1rem;
}
.shift-review__labels {
  display: block;
  opacity: 0.85;
  font-size: 0.9em;
}
.shift-review__confirm {
  margin: 0.5rem 0 0;
  font-weight: 600;
}
</style>
