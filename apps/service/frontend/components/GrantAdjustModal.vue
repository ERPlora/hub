<script setup lang="ts">
// SERVICE-F18 «Regalar sesiones, alargar la caducidad o corregir el saldo»: «Adjust this voucher» adds
// or removes sessions (only a voucher with a limit; removing, up to what is left) and/or extends the
// expiry (only one that expires; up to 366 days), with a required Reason and the preview «After the
// adjustment: {remaining} session(s) left · expires {when}». Adjust sends `service.grant.adjust` with
// the sessions signed (removing is negative) and closes; a refusal stays in the dialog.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonLabel, IonSegment, IonSegmentButton, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDate } from '../lib/format';
import type { GrantOut } from '../operations';

const props = defineProps<{ grant: GrantOut | null }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const adjusting = useCommand('service.grant.adjust');
const direction = ref<'add' | 'remove'>('add');
const uses = ref('');
const days = ref('');
const reason = ref('');

watch(open, (isOpen) => {
  if (!isOpen) return;
  direction.value = 'add';
  uses.value = '';
  days.value = '';
  reason.value = '';
  adjusting.error.value = null;
});

const limited = computed(() => props.grant?.max_uses !== null && props.grant?.max_uses !== undefined);
const expires = computed(() => !!props.grant?.expires_at);
/** A whole number typed (empty = 0); `null` when it is not one. */
const count = (text: string): number | null => (text.trim() === '' ? 0 : /^\d+$/.test(text.trim()) ? Number(text.trim()) : null);
const usesDelta = computed(() => {
  const n = count(uses.value);
  return n === null ? null : direction.value === 'remove' ? -n : n;
});
const daysDelta = computed(() => count(days.value));
const moves = computed(() => usesDelta.value !== null && daysDelta.value !== null && (usesDelta.value !== 0 || daysDelta.value !== 0));

const remaining = computed(() => props.grant?.remaining ?? 0);
const expiryAfter = computed(() => {
  const at = props.grant?.expires_at;
  if (!at) return null;
  const date = new Date(at);
  date.setUTCDate(date.getUTCDate() + (daysDelta.value ?? 0));
  return date.toISOString();
});
const preview = computed(() => {
  const expiry = expiryAfter.value
    ? t('service.adjust.expiresOn', { when: formatDate(expiryAfter.value, locale.value) })
    : t('service.adjust.neverExpires');
  return limited.value
    ? t('service.adjust.preview', { remaining: remaining.value + (usesDelta.value ?? 0), expiry })
    : t('service.adjust.previewUnlimited', { expiry });
});
const usesHelp = computed(() =>
  direction.value === 'remove'
    ? t('service.adjust.usesRemoveHelp', { remaining: remaining.value })
    : t('service.adjust.usesAddHelp', { remaining: remaining.value }),
);

const customer = computed(() => props.grant?.customer_name ?? props.grant?.customer_id ?? '');

async function confirm(): Promise<void> {
  if (!props.grant || !moves.value || !reason.value.trim()) return;
  try {
    await adjusting.run({ id: props.grant.id, uses_delta: usesDelta.value ?? 0, days_delta: daysDelta.value ?? 0, reason: reason.value.trim() });
  } catch {
    return; // The dialog paints the error.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="service-grant-adjust"
    :title="t('service.adjust.title')"
    :submit-label="t('service.adjust.confirm')"
    :cancel-label="t('service.cancel')"
    :pending="adjusting.pending.value"
    :error="adjusting.error.value"
    :submit-disabled="!moves || !reason.trim()"
    @submit="confirm"
  >
    <template #default="{ fieldErrors }">
      <div class="service-grant-adjust">
        <p data-testid="service-grant-adjust-message">
          {{ t('service.adjust.message', { customer }) }}
        </p>
        <template v-if="limited">
          <ion-segment
            data-testid="service-grant-adjust-direction"
            :value="direction"
            @ion-change="direction = $event.detail.value === 'remove' ? 'remove' : 'add'"
          >
            <ion-segment-button value="add">
              <ion-label>{{ t('service.adjust.addSessions') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="remove">
              <ion-label>{{ t('service.adjust.removeSessions') }}</ion-label>
            </ion-segment-button>
          </ion-segment>
          <ion-input
            data-testid="service-grant-adjust-uses"
            type="number"
            inputmode="numeric"
            min="0"
            :max="direction === 'remove' ? remaining : 100"
            :value="uses"
            :label="direction === 'remove' ? t('service.adjust.usesRemove') : t('service.adjust.usesAdd')"
            :helper-text="usesHelp"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.uses_delta"
            @ion-input="uses = String($event.detail.value ?? '')"
          />
        </template>
        <ion-input
          v-if="expires"
          data-testid="service-grant-adjust-days"
          type="number"
          inputmode="numeric"
          min="0"
          max="366"
          :value="days"
          :label="t('service.adjust.days')"
          :helper-text="t('service.adjust.daysHelp', { when: formatDate(grant?.expires_at, locale) })"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.days_delta"
          @ion-input="days = String($event.detail.value ?? '')"
        />
        <ion-textarea
          data-testid="service-grant-adjust-reason"
          :value="reason"
          :label="t('service.adjust.reason')"
          :helper-text="t('service.adjust.reasonHelp')"
          label-placement="floating"
          fill="outline"
          mode="md"
          auto-grow
          :maxlength="500"
          :error-text="fieldErrors.reason"
          @ion-input="reason = String($event.detail.value ?? '')"
        />
        <InlineFeedback
          tone="info"
          data-testid="service-grant-adjust-preview"
        >
          {{ preview }}
        </InlineFeedback>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.service-grant-adjust {
  display: grid;
  gap: 12px;
}
.service-grant-adjust p {
  margin: 0;
}
</style>
