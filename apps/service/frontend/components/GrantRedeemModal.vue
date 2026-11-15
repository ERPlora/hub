<script setup lang="ts">
// SERVICE-F21 «Gastar una sesión fuera del cobro» (hub#1058): «Spend a session» of a voucher sold, outside the till — the
// customer came only to use her session. It asks the Service (one of those the voucher covers; chosen already when it
// covers one), the Professional who did it (the team's picker of the service forms; optional, as in the operation: what
// the session is worth counts in their production in Sales) and a Note, and shows the balance «N left · M after this
// one». On opening and on each change of service it asks `service.grant.redeem_check` and, when it says no, shows why and
// Spend stays off; a check that cannot be made is said, and the server still has the last word. Spend sends
// `service.grant.redeem` and closes: the sheet's row follows `service.grant.list` live. A refusal stays in the dialog.
// Something chosen or typed asks «Discard changes?» before any way out throws it away (hub#1023, BASE-F05).
import { Combo, type ComboOption, FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useUnsavedChanges } from '../../../../base/frontend/lib/unsaved-changes';

import { useT } from '../composables/useT';
import { searchMembers } from '../lib/pickers';
import type { GrantOut, PackageOut, RedeemCheckOut } from '../operations';

const props = defineProps<{ grant: GrantOut | null; pkg: PackageOut }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const client = useLiveClient();
const searchStaff = searchMembers(client);
const redeeming = useCommand('service.grant.redeem');

const services = computed(() => props.pkg.items);
const service = ref('');
const openedWith = ref('');
const member = ref<ComboOption | null>(null);
const note = ref('');

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    service.value = services.value.length === 1 ? services.value[0].service_id : '';
    openedWith.value = service.value;
    member.value = null;
    note.value = '';
    redeeming.error.value = null;
  },
  { immediate: true },
);

const verdict = ref<RedeemCheckOut | null>(null);
const checking = ref(false);
const checkFailure = ref('');
/** Only the newest check answers: one asked for another service, or before it reopened, is dropped. */
let asked = 0;

async function check(): Promise<void> {
  const grant = props.grant;
  const ask = ++asked;
  verdict.value = null;
  checkFailure.value = '';
  if (!grant) return;
  checking.value = true;
  try {
    const answer = await client.api.call('service.grant.redeem_check', {
      id: grant.id,
      ...(service.value ? { service_id: service.value } : {}),
    });
    if (ask === asked) verdict.value = answer;
  } catch (failure) {
    if (ask === asked) checkFailure.value = failure instanceof Error ? failure.message : String(failure);
  } finally {
    if (ask === asked) checking.value = false;
  }
}

watch(
  () => [open.value, props.grant?.id, service.value] as const,
  ([isOpen]) => {
    if (isOpen) void check();
  },
  { immediate: true },
);

const refusal = computed(() => {
  const answer = verdict.value;
  if (!answer || answer.redeemable) return '';
  return answer.reason ? t(`service.redeem.reason.${answer.reason}`) : t('service.redeem.refused');
});

/** What is left: what the check found (another till may have spent one meanwhile), else what the row said. */
const left = computed(() => (verdict.value ? verdict.value.remaining : (props.grant?.remaining ?? null)));
const balance = computed(() => {
  if (!props.grant || refusal.value) return '';
  if (left.value === null) return t('service.redeem.unlimited');
  return left.value > 0 ? t('service.redeem.balance', { n: left.value, after: left.value - 1 }) : '';
});

const message = computed(() =>
  props.grant
    ? t('service.redeem.message', { customer: props.grant.customer_name ?? props.grant.customer_id, package: props.grant.package_name })
    : '',
);

const blocked = computed(() => !props.grant || checking.value || !!refusal.value || (services.value.length > 0 && !service.value));

const unsaved = computed(() => open.value && (service.value !== openedWith.value || member.value !== null || note.value.trim() !== ''));
const canDismiss = useUnsavedChanges('service-grant-redeem', unsaved);

async function spend(): Promise<void> {
  const grant = props.grant;
  if (!grant || blocked.value) return;
  const said = note.value.trim();
  try {
    await redeeming.run({
      id: grant.id,
      ...(service.value ? { service_id: service.value } : {}),
      ...(member.value ? { member_id: member.value.id } : {}),
      ...(said ? { note: said } : {}),
    });
  } catch {
    return; // The dialog paints the refusal.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="service-grant-redeem"
    :title="t('service.redeem.title')"
    :submit-label="t('service.redeem.confirm')"
    :cancel-label="t('service.cancel')"
    :pending="redeeming.pending.value"
    :error="redeeming.error.value"
    :submit-disabled="blocked"
    :can-dismiss="canDismiss"
    @submit="spend"
  >
    <template #default="{ fieldErrors }">
      <p
        class="ion-margin-bottom"
        data-testid="service-grant-redeem-message"
      >
        {{ message }}
      </p>
      <InlineFeedback
        v-if="balance"
        class="ion-margin-bottom"
        tone="info"
        data-testid="service-grant-redeem-balance"
      >
        {{ balance }}
      </InlineFeedback>
      <p
        v-if="checking"
        class="ion-margin-bottom"
        data-testid="service-grant-redeem-checking"
      >
        {{ t('service.redeem.checking') }}
      </p>
      <InlineFeedback
        v-else-if="refusal"
        class="ion-margin-bottom"
        tone="warning"
        data-testid="service-grant-redeem-refused"
        :heading="t('service.redeem.refused')"
      >
        {{ refusal }}
      </InlineFeedback>
      <InlineFeedback
        v-else-if="checkFailure"
        class="ion-margin-bottom"
        tone="danger"
        data-testid="service-grant-redeem-check-error"
        :heading="t('service.redeem.checkError')"
      >
        {{ checkFailure }}
      </InlineFeedback>
      <ion-select
        v-if="services.length"
        class="ion-margin-bottom"
        data-testid="service-grant-redeem-service"
        name="service_id"
        interface="popover"
        :value="service"
        :label="t('service.redeem.service')"
        :placeholder="t('service.redeem.servicePlaceholder')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="fieldErrors.service_id"
        @ion-change="service = String($event.detail.value ?? '')"
      >
        <ion-select-option
          v-for="item in services"
          :key="item.service_id"
          :value="item.service_id"
        >
          {{ item.service_name }}
        </ion-select-option>
      </ion-select>
      <Combo
        class="ion-margin-bottom"
        testid="service-grant-redeem-member"
        name="member_id"
        clearable
        :model-value="member"
        :search="searchStaff"
        :label="t('service.redeem.member')"
        :helper-text="t('service.redeem.memberHelp')"
        :error-text="fieldErrors.member_id"
        @update:model-value="member = $event"
      />
      <ion-textarea
        data-testid="service-grant-redeem-note"
        name="note"
        :value="note"
        :label="t('service.redeem.note')"
        label-placement="floating"
        fill="outline"
        mode="md"
        auto-grow
        :maxlength="500"
        :error-text="fieldErrors.note"
        @ion-input="note = String($event.detail.value ?? '')"
      />
    </template>
  </FormModal>
</template>
