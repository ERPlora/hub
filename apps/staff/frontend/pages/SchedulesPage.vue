<script setup lang="ts">
// Staff → Schedules (WORKBOOK «Pantallas · Horarios»): the Member picker (searched on the server) above
// the schedules of the chosen member (MemberSchedules) — the first one by name to begin with. The
// picker is the scope of the list, not a field of the form. With no member at all there is nobody to
// schedule: «No staff members yet» and «Add staff member», which opens Staff (the old staff#98).
import { Combo, type ComboOption, EmptyState } from '@erplora/ui/components';
import { useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import MemberSchedules from '../components/MemberSchedules.vue';
import { asCombo, memberSearch } from '../lib/pickers';
import { staffTabs } from '../tabs';

const session = useSession();
const router = useRouter();
const client = useLiveClient();
const canSettings = computed(() => session.can('staff.manage_settings'));
const canSeePay = computed(() => session.can('staff.view_compensation'));

/** The first member by name: whether there is anyone, and whom to show to begin with. */
const { data: first, status } = useLive('staff.member.list', { sort: 'name', limit: 1 });
const findMembers = asCombo(memberSearch(client));

const chosen = ref<{ id: string; name: string } | null>(null);
const member = computed(() => {
  if (chosen.value) return chosen.value;
  const row = first.value?.rows[0];
  return row ? { id: row.id, name: row.full_name } : null;
});
/** The Member field's choice. */
const choice = computed<ComboOption | null>(() => (member.value ? { id: member.value.id, label: member.value.name } : null));
const nobody = computed(() => first.value !== undefined && first.value.total === 0);

function pick(option: ComboOption | null): void {
  chosen.value = option?.id ? { id: option.id, name: option.label } : null;
}

function addMember(): void {
  void router.push('/staff/members');
}
</script>

<template>
  <AppPage
    :title="$t('staff.title')"
    content-layout="fill"
    :tabs="staffTabs($t, { settings: canSettings, commissions: canSeePay })"
    :tabs-label="$t('staff.tabs.label')"
  >
    <p
      v-if="status === 'loading' && !first"
      class="staff-schedules__loading"
      data-testid="staff-schedules-loading-members"
    >
      {{ $t('staff.loading') }}
    </p>
    <EmptyState
      v-else-if="nobody"
      data-testid="staff-schedules-no-members"
      icon="people-outline"
      :heading="$t('staff.schedules.noMembers.title')"
      :message="$t('staff.schedules.noMembers.message')"
    >
      <template #action>
        <ion-button
          data-testid="staff-schedules-add-member"
          @click="addMember"
        >
          {{ $t('staff.schedules.noMembers.action') }}
        </ion-button>
      </template>
    </EmptyState>
    <template v-else-if="member">
      <header class="staff-schedules__scope">
        <Combo
          testid="staff-schedules-member"
          :label="$t('staff.schedules.member')"
          :model-value="choice"
          :search="findMembers"
          :empty-label="$t('staff.noResults')"
          :clearable="false"
          @update:model-value="pick"
        />
      </header>
      <MemberSchedules
        :key="member.id"
        :member-id="member.id"
      />
    </template>
  </AppPage>
</template>

<style scoped>
.staff-schedules__scope {
  max-width: 24rem;
  margin-bottom: 0.75rem;
}
.staff-schedules__loading {
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
