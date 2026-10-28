<script setup lang="ts">
// STAFF-F08 «Ver mi propia ficha»: the record of whoever is signed in (`staff.member.mine`, which the
// page follows live), read only, with their own hourly rate and commission — never the HR notes, which
// the server does not send here. «Close» is its only button.
import { FormModal } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney, formatPercent, useBusinessMoney } from '../lib/format';
import type { MemberMineOut } from '../operations';

const props = defineProps<{
  record: MemberMineOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
/** The business's currency (its country's): the rate is painted in it (staff-business-currency). */
const money = useBusinessMoney();

const dash = (value: string | null | undefined): string => (value && value.trim() ? value : '—');

const fields = computed<Array<[string, string]>>(() => {
  const r = props.record;
  if (!r) return [];
  return [
    [t('staff.members.columns.name'), r.full_name],
    [t('staff.members.columns.role'), dash(r.role_name)],
    [t('staff.members.columns.email'), dash(r.email)],
    [t('staff.members.columns.phone'), dash(r.phone)],
    [t('staff.members.form.employeeNumber'), dash(r.employee_number)],
    [t('staff.members.columns.status'), t(`staff.memberStatus.${r.status}`)],
    [t('staff.members.form.bookable'), r.is_bookable ? t('staff.yes') : t('staff.no')],
    [t('staff.members.form.hireDate'), formatDate(r.hire_date, locale.value)],
    [t('staff.members.form.hourlyRate'), formatMoney(r.hourly_rate, locale.value, money.value)],
    [t('staff.members.form.commission'), formatPercent(r.commission_rate, locale.value)],
  ];
});
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="staff-my-record"
    :title="$t('staff.members.mine.title')"
    @submit="open = false"
  >
    <dl
      class="staff-record"
      data-testid="staff-my-record-fields"
    >
      <div
        v-for="[label, value] in fields"
        :key="label"
        class="staff-record__field"
        data-testid="staff-my-record-field"
      >
        <dt>{{ label }}</dt>
        <dd>{{ value }}</dd>
      </div>
    </dl>
    <template #footer>
      <ion-button
        data-testid="staff-my-record-done"
        @click="open = false"
      >
        {{ $t('staff.members.mine.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.staff-record {
  display: grid;
  gap: 10px;
  margin: 0;
}
.staff-record__field {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-size: 14px;
}
.staff-record__field dt {
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.staff-record__field dd {
  margin: 0;
  font-weight: 500;
  text-align: right;
}
</style>
