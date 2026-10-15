<script setup lang="ts">
// The shift review of the close (CASH_REGISTER-F08; Toast's shift review): what is still open when the
// drawer closes. It warns, it never prevents: the page asks for a second press when there is pending work.
// Today it is Sales' open checks; the kitchen's tickets and the print queue join with those apps.
import { InlineFeedback } from '@erplora/ui/components';

defineProps<{
  /** The reading is on its way. */
  checking: boolean;
  /** The reading failed: the review may be incomplete. */
  incomplete: boolean;
  /** Checks still open in Sales. */
  openChecks: number;
  /** Their titles, as Sales shows them. */
  labels: string[];
  /** The first press already warned: the next one closes. */
  acknowledged: boolean;
}>();
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
    v-else-if="openChecks > 0"
    tone="warning"
    icon="alert-circle-outline"
    data-testid="cash-register-review"
    :heading="$t('cash_register.review.title')"
  >
    <ul class="shift-review__list">
      <li>
        {{ $t('cash_register.review.openChecks', { count: openChecks }) }}
        <span
          v-if="labels.length"
          class="shift-review__labels"
        >{{ labels.join(' · ') }}</span>
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
