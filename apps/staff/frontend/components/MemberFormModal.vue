<script setup lang="ts">
// STAFF-F01, F02, F03, F21 — the record of a staff member, the old side panel as a dialog: «New» (no
// `member`) or «Edit · {name}». Fields in the old order; Status only when editing; the pay (Hourly
// rate, Commission, HR notes) only for whoever may see it. Role and Hub user are Combo fields that search
// the server (a business may have more than the 100 rows it gives at once): the active roles and the
// accounts with access to this business (`staff.account.list`, not a live query), with «No role» and
// «No Hub access» first, as in the old select: the way to empty them. Editing reads the
// whole record and its pay when it opens (the row has not everything) and sends only what changed.
// The server judges: its 422 goes under each field, a 409 on top; the dialog keeps what was typed.
// The hourly rate is typed in the business's currency (its country's, with the decimals the server counts:
// staff-business-currency), its symbol at the end of the field; until the business answers, two decimals and no
// symbol. If it answers with the dialog open, the rate as loaded is rewritten in its decimals and what was
// typed is read in it when saving.
import { Combo, type ComboOption, FormModal, InlineFeedback } from '@erplora/ui/components';
import { ApiError, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption, IonText, IonTextarea, IonToggle } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { MEMBER_STATUSES } from '../lib/enums';
import { currencySymbol, moneyText, useBusinessMoney } from '../lib/format';
import { blankMemberForm, createPayload, formFromRecord, type MemberForm, patchPayload } from '../lib/memberForm';
import { accountSearch, asCombo, roleSearch } from '../lib/pickers';
import type { MemberOut } from '../operations';

const props = defineProps<{
  /** The row being edited; `null` = «New». */
  member: MemberOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const session = useSession();
const client = useLiveClient();
const money = useBusinessMoney();
/** What the end of the Hourly rate field says: the business's currency symbol, nothing until it answers. */
const symbol = computed(() => currencySymbol(locale.value, money.value));

const canPay = computed(() => session.can('staff.view_compensation'));
const editing = computed(() => props.member !== null);

const form = ref<MemberForm>(blankMemberForm());
/** The form as it was loaded: «Edit» sends only what differs from it. */
const original = shallowRef<MemberForm>(blankMemberForm());
/** The names of the chosen role and Hub user (the record gives ids). */
const roleLabel = ref('');
const userLabel = ref('');
const loading = ref(false);
const loadError = ref('');

const creation = useCommand('staff.member.create');
const update = useCommand('staff.member.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (editing.value ? update.error.value : creation.error.value));

const title = computed(() =>
  props.member ? t('staff.members.form.titleEdit', { name: props.member.full_name }) : t('staff.members.form.titleNew'),
);
const complete = computed(() => form.value.first_name.trim() !== '' && form.value.last_name.trim() !== '');

/** Each opening retires the reads of the previous one: a late answer never lands on another record. */
let opening = 0;
/** The hourly rate the record was loaded with, in minor units (`null`: none loaded). */
let loadedRate: number | null = null;

const findRoles = asCombo(roleSearch(client, { activeOnly: true, by: 'id' }), () => t('staff.members.form.roleNone'));
const findAccounts = asCombo(accountSearch(client), () => t('staff.members.form.hubUserNone'));
/** What the Role and Hub user fields show: the choice, or its «none». */
const roleChoice = computed<ComboOption>(() =>
  form.value.role_id ? { id: form.value.role_id, label: roleLabel.value } : { id: '', label: t('staff.members.form.roleNone') },
);
const userChoice = computed<ComboOption>(() =>
  form.value.user_id ? { id: form.value.user_id, label: userLabel.value } : { id: '', label: t('staff.members.form.hubUserNone') },
);

/** The name of the account the record hangs from; «No access to this business» when it is not among
 *  the active accounts of this business any more (deactivated, or its access withdrawn). */
async function nameAccount(userId: string, ticket: number): Promise<void> {
  const gone = t('staff.members.form.hubUserGone');
  try {
    const answer = await client.api.call('staff.account.list', { user_id: Number(userId), limit: 1 });
    if (ticket === opening) userLabel.value = answer.rows[0]?.name ?? gone;
  } catch {
    if (ticket === opening) userLabel.value = gone;
  }
}

async function loadRecord(member: MemberOut, ticket: number): Promise<void> {
  loading.value = true;
  try {
    const [record, pay] = await Promise.all([
      client.api.call('staff.member.detail', { id: member.id }),
      canPay.value ? client.api.call('staff.member.compensation', { id: member.id, limit: 1 }) : Promise.resolve(null),
    ]);
    if (ticket !== opening) return;
    loadedRate = pay?.rows[0]?.hourly_rate ?? null;
    const loaded = formFromRecord(record, pay?.rows[0] ?? null, locale.value, money.value);
    original.value = loaded;
    form.value = { ...loaded };
    roleLabel.value = record.role_name ?? '';
    if (loaded.user_id) void nameAccount(loaded.user_id, ticket);
  } catch (failure) {
    if (ticket === opening) loadError.value = failure instanceof ApiError ? failure.message : t('staff.members.form.loadError');
  } finally {
    if (ticket === opening) loading.value = false;
  }
}

function start(): void {
  const ticket = ++opening;
  creation.error.value = null;
  update.error.value = null;
  loadError.value = '';
  // A read of a previous opening may still be on its way: it no longer speaks for this one.
  loading.value = false;
  const member = props.member;
  roleLabel.value = member?.role_name ?? '';
  userLabel.value = '';
  loadedRate = null;
  const blank = blankMemberForm();
  // What the row already says, at once; the rest arrives with the record.
  const first: MemberForm = member
    ? {
        ...blank,
        first_name: member.first_name,
        last_name: member.last_name,
        email: member.email,
        phone: member.phone,
        employee_number: member.employee_number,
        role_id: member.role_id ?? '',
        user_id: member.user_id === null ? '' : String(member.user_id),
        status: member.status,
        is_bookable: member.is_bookable,
        hire_date: member.hire_date ?? '',
        color: member.color,
      }
    : blank;
  original.value = first;
  form.value = { ...first };
  if (member) void loadRecord(member, ticket);
}

watch(
  () => [open.value, props.member?.id] as const,
  ([isOpen]) => {
    if (isOpen) start();
    else opening++;
  },
  { immediate: true },
);

// The business answers (or changes currency) with the dialog open: the rate as loaded is written in its decimals;
// a rate already typed stays as typed (it is read in the currency when saving).
watch([() => money.value?.currency, () => money.value?.decimals], () => {
  if (loadedRate === null) return;
  const text = moneyText(loadedRate, locale.value, money.value);
  const untouched = form.value.hourly_rate === original.value.hourly_rate;
  original.value = { ...original.value, hourly_rate: text };
  if (untouched) form.value = { ...form.value, hourly_rate: text };
});

function set<K extends keyof MemberForm>(field: K, value: MemberForm[K]): void {
  form.value = { ...form.value, [field]: value };
}

function pickRole(option: ComboOption | null): void {
  set('role_id', option?.id ?? '');
  roleLabel.value = option?.id ? option.label : '';
}

function pickUser(option: ComboOption | null): void {
  set('user_id', option?.id ?? '');
  userLabel.value = option?.id ? option.label : '';
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

async function save(): Promise<void> {
  const options = { pay: canPay.value, money: money.value };
  try {
    if (props.member) await update.run(patchPayload(props.member.id, original.value, form.value, options));
    else await creation.run(createPayload(form.value, options));
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="staff-member-form"
    :title="title"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete || loading || !!loadError"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <InlineFeedback
        v-if="loadError"
        tone="danger"
        data-testid="staff-member-form-load-error"
      >
        {{ loadError }}
      </InlineFeedback>
      <p
        v-if="loading"
        class="staff-form__loading"
        data-testid="staff-member-form-loading"
      >
        {{ $t('staff.loading') }}
      </p>
      <div
        class="staff-form"
        data-testid="staff-member-form-fields"
      >
        <ion-input
          data-testid="staff-member-form-first_name"
          data-field
          :value="form.first_name"
          :label="$t('staff.members.form.firstName')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          autocomplete="off"
          :error-text="fieldErrors.first_name"
          :class="invalid(fieldErrors.first_name)"
          @ion-input="set('first_name', text($event.detail.value))"
        />
        <ion-input
          data-testid="staff-member-form-last_name"
          data-field
          :value="form.last_name"
          :label="$t('staff.members.form.lastName')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          autocomplete="off"
          :error-text="fieldErrors.last_name"
          :class="invalid(fieldErrors.last_name)"
          @ion-input="set('last_name', text($event.detail.value))"
        />
        <ion-input
          data-testid="staff-member-form-email"
          data-field
          type="email"
          :value="form.email"
          :label="$t('staff.members.form.email')"
          label-placement="floating"
          fill="outline"
          mode="md"
          autocomplete="off"
          :error-text="fieldErrors.email"
          :class="invalid(fieldErrors.email)"
          @ion-input="set('email', text($event.detail.value))"
        />
        <ion-input
          data-testid="staff-member-form-phone"
          data-field
          type="tel"
          :value="form.phone"
          :label="$t('staff.members.form.phone')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="20"
          :error-text="fieldErrors.phone"
          :class="invalid(fieldErrors.phone)"
          @ion-input="set('phone', text($event.detail.value))"
        />
        <ion-input
          data-testid="staff-member-form-employee_number"
          data-field
          :value="form.employee_number"
          :label="$t('staff.members.form.employeeNumber')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="50"
          :error-text="fieldErrors.employee_number"
          :class="invalid(fieldErrors.employee_number)"
          @ion-input="set('employee_number', text($event.detail.value))"
        />
        <Combo
          testid="staff-member-form-role_id"
          data-field
          :model-value="roleChoice"
          :label="$t('staff.members.form.role')"
          :search="findRoles"
          :empty-label="$t('staff.noResults')"
          :clearable="false"
          :error-text="fieldErrors.role_id ?? fieldErrors.role"
          @update:model-value="pickRole"
        />
        <Combo
          testid="staff-member-form-user_id"
          data-field
          :model-value="userChoice"
          :label="$t('staff.members.form.hubUser')"
          :search="findAccounts"
          :empty-label="$t('staff.noResults')"
          :clearable="false"
          :error-text="fieldErrors.user_id"
          @update:model-value="pickUser"
        />
        <p
          v-if="!form.user_id"
          class="staff-form__hint"
          data-testid="staff-member-form-hub-user-hint"
        >
          {{ $t('staff.members.form.hubUserHint') }}
        </p>
        <div class="staff-form__grid">
          <ion-select
            v-if="editing"
            data-testid="staff-member-form-status"
            data-field
            :value="form.status"
            :label="$t('staff.members.form.status')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            :error-text="fieldErrors.status"
            :class="invalid(fieldErrors.status)"
            @ion-change="set('status', ($event.detail.value || 'active') as MemberForm['status'])"
          >
            <ion-select-option
              v-for="status in MEMBER_STATUSES"
              :key="status"
              :value="status"
            >
              {{ $t(`staff.memberStatus.${status}`) }}
            </ion-select-option>
          </ion-select>
          <ion-toggle
            data-testid="staff-member-form-is_bookable"
            data-field
            label-placement="end"
            justify="start"
            :checked="form.is_bookable"
            @ion-change="set('is_bookable', $event.detail.checked)"
          >
            {{ $t('staff.members.form.bookable') }}
          </ion-toggle>
          <ion-input
            data-testid="staff-member-form-booking_buffer"
            data-field
            type="number"
            inputmode="numeric"
            min="0"
            max="240"
            :value="form.booking_buffer"
            :label="$t('staff.members.form.bookingBuffer')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.booking_buffer"
            :class="invalid(fieldErrors.booking_buffer)"
            @ion-input="set('booking_buffer', text($event.detail.value))"
          />
          <ion-input
            data-testid="staff-member-form-hire_date"
            data-field
            type="date"
            :value="form.hire_date"
            :label="$t('staff.members.form.hireDate')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.hire_date"
            :class="invalid(fieldErrors.hire_date)"
            @ion-input="set('hire_date', text($event.detail.value))"
          />
          <ion-input
            data-testid="staff-member-form-color"
            data-field
            :value="form.color"
            :label="$t('staff.members.form.color')"
            placeholder="#RRGGBB"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="7"
            :error-text="fieldErrors.color"
            :class="invalid(fieldErrors.color)"
            @ion-input="set('color', text($event.detail.value))"
          >
            <ion-text
              v-if="/^#[0-9a-fA-F]{6}$/.test(form.color)"
              slot="end"
              aria-hidden="true"
            >
              <span
                class="staff-form__swatch"
                :style="{ background: form.color }"
              />
            </ion-text>
          </ion-input>
          <ion-input
            data-testid="staff-member-form-specialties"
            data-field
            :value="form.specialties"
            :label="$t('staff.members.form.specialties')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.specialties"
            :class="invalid(fieldErrors.specialties)"
            @ion-input="set('specialties', text($event.detail.value))"
          />
          <ion-textarea
            data-testid="staff-member-form-bio"
            data-field
            class="staff-form__wide"
            :value="form.bio"
            :label="$t('staff.members.form.bio')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :auto-grow="true"
            :error-text="fieldErrors.bio"
            :class="invalid(fieldErrors.bio)"
            @ion-input="set('bio', text($event.detail.value))"
          />
        </div>
        <section
          v-if="canPay"
          class="staff-form__grid"
          data-testid="staff-member-form-pay"
          :aria-label="$t('staff.members.form.compensation')"
        >
          <ion-input
            data-testid="staff-member-form-hourly_rate"
            data-field
            inputmode="decimal"
            :value="form.hourly_rate"
            :label="$t('staff.members.form.hourlyRate')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.hourly_rate"
            :class="invalid(fieldErrors.hourly_rate)"
            @ion-input="set('hourly_rate', text($event.detail.value))"
          >
            <ion-text
              v-if="symbol"
              slot="end"
              aria-hidden="true"
              data-testid="staff-member-form-hourly_rate-currency"
            >
              {{ symbol }}
            </ion-text>
          </ion-input>
          <ion-input
            data-testid="staff-member-form-commission_rate"
            data-field
            type="number"
            inputmode="decimal"
            min="0"
            max="100"
            step="0.01"
            :value="form.commission_rate"
            :label="$t('staff.members.form.commission')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.commission_rate"
            :class="invalid(fieldErrors.commission_rate)"
            @ion-input="set('commission_rate', text($event.detail.value))"
          />
          <ion-textarea
            data-testid="staff-member-form-notes"
            data-field
            class="staff-form__wide"
            :value="form.notes"
            :label="$t('staff.members.form.notes')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :auto-grow="true"
            :error-text="fieldErrors.notes"
            :class="invalid(fieldErrors.notes)"
            @ion-input="set('notes', text($event.detail.value))"
          />
        </section>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.staff-form {
  display: grid;
  gap: 14px;
}
/* Two columns when the dialog is wide enough, one on a phone (the old panel's `.grid2`). */
.staff-form__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 12px;
  align-items: center;
  border-top: 1px solid var(--ion-border-color, #e5e3dd);
  padding-top: 12px;
}
.staff-form__wide {
  grid-column: 1 / -1;
}
.staff-form__hint,
.staff-form__loading {
  margin: -0.35rem 0 0;
  font-size: 0.8rem;
  line-height: 1.35;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.staff-form__swatch {
  display: block;
  width: 1.1rem;
  height: 1.1rem;
  border-radius: 50%;
  border: 1px solid var(--ion-border-color, #e5e3dd);
}
</style>
