<script setup lang="ts">
// The customer card (WORKBOOK «Ficha de cliente»; CUSTOMER-F03–F07, F13–F16, F19, F23, F24), as the
// product's sheet: the buttons the profile allows (Edit, Delete, Merge with…, Erase personal data),
// the data — or, editing, the card's form with the custom fields and «Active», saved in one call —,
// Health and allergies (F32), Groups and Tags, Marketing consent, Add note and Activity, Purchases, Linked orders and, last, the
// other apps' blocks. Everything is live: what someone else changes shows without reloading; a card
// deleted, merged or erased meanwhile says «This customer is no longer available.».
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import ActivityPanel from '../components/ActivityPanel.vue';
import ConsentPanel from '../components/ConsentPanel.vue';
import HealthPanel from '../components/HealthPanel.vue';
import CustomerCardBlocks from '../components/CustomerCardBlocks.vue';
import CustomerDeleteDialog from '../components/CustomerDeleteDialog.vue';
import CustomerFacts from '../components/CustomerFacts.vue';
import CustomerForm from '../components/CustomerForm.vue';
import ErasePanel from '../components/ErasePanel.vue';
import LinkedOrders from '../components/LinkedOrders.vue';
import MembershipEditor from '../components/MembershipEditor.vue';
import MergePanel from '../components/MergePanel.vue';
import PurchaseHistory from '../components/PurchaseHistory.vue';
import { refusalFields, refusalOutsideFields } from '../lib/apiErrors';
import { type CustomerFields, ESSENTIAL_FIELDS, fieldsFromDetail, MORE_FIELDS, patchInput } from '../lib/customerForm';
import { customerTabs } from '../lib/tabs';
import { useCustomerI18n } from '../lib/useCustomerI18n';

const props = defineProps<{ id: string }>();

const LIST = '/customer/customers';
const NONE: string[] = [];
const router = useRouter();
const session = useSession();
const canManage = computed(() => session.can('customer.manage'));
const canDelete = computed(() => session.can('customer.delete'));
const canMerge = computed(() => session.can('customer.merge'));
const canErase = computed(() => session.can('customer.erase'));
const { t } = useCustomerI18n();

const { data: card, status, error } = useLive('customer.customer.detail', () => ({ id: props.id }));

const gone = computed(() => error.value?.code === 'customer.customer_unavailable' || error.value?.code === 'not_found');
const inactive = computed(() => error.value?.code === 'app_inactive');
/** The card to show: none once it is gone. */
const customer = computed(() => (gone.value || inactive.value ? undefined : card.value));
const who = computed(() => (customer.value ? { id: customer.value.id, name: customer.value.name } : null));
/** The blocks follow the card's id from the start, so the page opens one stream, not one per result. */
const failed = computed(() => gone.value || inactive.value || (status.value === 'error' && !card.value));

// ── The panels on the card: one at a time ────────────────────────────────────────────────────────
type Panel = 'merge' | 'erase' | null;
const panel = ref<Panel>(null);
const deleting = ref<{ id: string; name: string } | null>(null);

function backToList(): void {
  void router.replace(LIST);
}

// ── Edit (F04): the form starts from the card as saved and never follows later results ─────────
const editing = ref(false);
const original = ref<CustomerFields>();
const form = ref<CustomerFields>();
const fieldValues = ref<Record<string, string>>({});
const update = useCommand('customer.customer.update');
const SHOWN = [...ESSENTIAL_FIELDS, ...MORE_FIELDS];
const errors = computed(() => refusalFields(update.error.value));
const failure = computed(() => {
  const shown = [...SHOWN, ...(customer.value?.custom_fields ?? []).map((f) => `field_values.${f.field_id}`)];
  return refusalOutsideFields(update.error.value, shown);
});

function startEdit(): void {
  if (!customer.value) return;
  panel.value = null;
  original.value = fieldsFromDetail(customer.value);
  form.value = { ...original.value };
  fieldValues.value = Object.fromEntries(customer.value.custom_fields.map((f) => [f.field_id, f.value]));
  update.error.value = null;
  editing.value = true;
}

async function save(): Promise<void> {
  if (!original.value || !form.value || !customer.value || !form.value.name.trim()) return;
  try {
    await update.run({
      id: props.id,
      ...patchInput(original.value, form.value),
      // Every custom field travels, the emptied ones too: clearing one is a change (F04).
      field_values: customer.value.custom_fields.map((f) => ({ field_id: f.field_id, value: fieldValues.value[f.field_id] ?? '' })),
    });
  } catch {
    return; // `error` holds it: the form paints it.
  }
  editing.value = false;
  void toastSuccess(t('customer.detail.updated'));
}
</script>

<template>
  <AppPage
    :title="customer?.name ?? $t('customer.detail.title')"
    :back-href="LIST"
    content-layout="detail"
    :tabs="customerTabs($t)"
    :tabs-label="$t('customer.tabs.label')"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="customer-detail-reconnecting"
    >
      {{ $t('customer.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="gone"
      tone="warning"
      data-testid="customer-detail-gone"
      :heading="$t('customer.common.unavailable')"
    />
    <InlineFeedback
      v-else-if="inactive"
      tone="warning"
      data-testid="customer-detail-inactive"
      :heading="$t('customer.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <InlineFeedback
      v-else-if="status === 'error' && !card"
      tone="danger"
      data-testid="customer-detail-error"
      :heading="$t('customer.detail.loadError')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <div
      v-if="!card && status === 'loading'"
      class="ion-text-center ion-padding"
    >
      <ion-spinner data-testid="customer-detail-loading" />
    </div>

    <template v-if="customer">
      <div
        class="customer-detail__actions"
        data-testid="customer-detail-actions"
      >
        <ion-button
          v-if="canManage && !editing"
          size="small"
          data-testid="customer-detail-edit"
          @click="startEdit"
        >
          {{ $t('customer.detail.edit') }}
        </ion-button>
        <ion-button
          v-if="canDelete"
          size="small"
          fill="outline"
          color="danger"
          data-testid="customer-detail-delete"
          @click="deleting = who"
        >
          {{ $t('customer.detail.delete') }}
        </ion-button>
        <ion-button
          v-if="canMerge"
          size="small"
          fill="outline"
          data-testid="customer-detail-merge"
          @click="(panel = 'merge'), (editing = false)"
        >
          {{ $t('customer.detail.merge') }}
        </ion-button>
        <ion-button
          v-if="canErase"
          size="small"
          fill="clear"
          color="danger"
          data-testid="customer-detail-erase"
          @click="(panel = 'erase'), (editing = false)"
        >
          {{ $t('customer.detail.erase') }}
        </ion-button>
      </div>

      <MergePanel
        v-if="panel === 'merge' && canMerge && who"
        :customer="who"
        @done="panel = null"
      />
      <ErasePanel
        v-if="panel === 'erase' && canErase && who"
        :customer="who"
        @erased="backToList"
        @cancel="panel = null"
      />

      <section class="customer-detail__panel">
        <form
          v-if="editing && form"
          data-testid="customer-edit-form"
          novalidate
          @submit.prevent="save"
        >
          <InlineFeedback
            v-if="failure"
            tone="danger"
            data-testid="customer-edit-error"
          >
            {{ failure }}
          </InlineFeedback>
          <CustomerForm
            v-model="form"
            v-model:field-values="fieldValues"
            mode="edit"
            :errors="errors"
            :custom-fields="customer.custom_fields"
          />
          <div class="customer-detail__form-actions">
            <ion-button
              type="submit"
              size="small"
              data-testid="customer-edit-save"
              :disabled="update.pending.value || !form.name.trim()"
            >
              {{ $t('customer.common.save') }}
            </ion-button>
            <ion-button
              size="small"
              fill="outline"
              data-testid="customer-edit-cancel"
              :disabled="update.pending.value"
              @click="editing = false"
            >
              {{ $t('customer.common.cancel') }}
            </ion-button>
          </div>
        </form>
        <CustomerFacts
          v-else
          :customer="customer"
        />
      </section>
    </template>

    <div
      v-if="!failed"
      v-show="customer"
      data-testid="customer-detail-blocks"
    >
      <section class="customer-detail__panel">
        <HealthPanel
          :customer-id="id"
          :editable="canManage"
        />
      </section>

      <section class="customer-detail__panel">
        <MembershipEditor
          kind="groups"
          :customer-id="id"
          :selected="customer?.group_ids ?? NONE"
          :editable="canManage"
        />
        <MembershipEditor
          kind="tags"
          class="customer-detail__tags"
          :customer-id="id"
          :selected="customer?.tag_ids ?? NONE"
          :editable="canManage"
        />
      </section>

      <section class="customer-detail__panel">
        <ConsentPanel
          :customer-id="id"
          :consent="customer?.consent ?? []"
          :editable="canManage"
        />
      </section>

      <section class="customer-detail__panel">
        <ActivityPanel
          :customer-id="id"
          :can-add-note="canManage"
        />
      </section>

      <section class="customer-detail__panel">
        <PurchaseHistory :customer-id="id" />
      </section>

      <section class="customer-detail__panel">
        <LinkedOrders :customer-id="id" />
      </section>

      <CustomerCardBlocks :customer-id="id" />
    </div>

    <CustomerDeleteDialog
      v-if="canDelete"
      v-model:customer="deleting"
      @deleted="backToList"
    />
  </AppPage>
</template>

<style scoped>
.customer-detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.75rem;
}

.customer-detail__actions ion-button {
  margin: 0;
}

/* The product's `.panel`: each block of the card in a bordered, tinted box. */
.customer-detail__panel {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: var(--ep-radius-sm, 10px);
  padding: 0.75rem 1rem;
  margin: 0 0 1rem;
  background: var(--ep-surface-2, var(--ion-color-step-50, rgba(24, 24, 27, 0.04)));
}

.customer-detail__tags {
  margin-top: 0.75rem;
}

.customer-detail__form-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}
</style>
