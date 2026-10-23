<script setup lang="ts">
// «Who is serving this check» / «Whose line is this» (SALE-F16). First «Me (whoever is signed in)» —
// for a line, «The check's professional» — which clears the choice; then Staff's active team, 20 at a
// time and searched on the server. The choice in use is marked. A team that cannot be loaded (Staff
// off, no permission) says the sale stays with whoever is signed in; «Me» still works. It follows the
// team while it is mounted: the page mounts it only while someone is picking. For the check it asks Staff
// once whose record the session is (the server attributes «Me» to it): without one, it warns that a sale
// left on «Me» counts for nobody. Staff unable to answer (off, the network) warns nothing: the list
// already says the team could not be loaded.
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton, IonSearchbar } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';

import { useT } from '../../composables/useT';
import PosSheet from './PosSheet.vue';

const props = defineProps<{ mode: 'check' | 'line'; current: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ choose: [choice: { id: string | null; name: string | null }] }>();

const t = useT();
const term = shallowRef('');
const { data, status, error } = useLive('staff.member.list', () => ({
  status: 'active' as const,
  search: term.value,
  sort: 'name',
  limit: 20,
  offset: 0,
}));
const rows = computed(() => data.value?.rows ?? []);

const sessionRecord = useCommand('staff.member.current');
const unlinked = shallowRef(false);
onMounted(async () => {
  if (props.mode !== 'check') return;
  try {
    unlinked.value = (await sessionRecord.run({})).member === null;
  } catch {
    unlinked.value = false;
  }
});

const title = computed(() => (props.mode === 'check' ? t('sale.pos.staffPickerTitle') : t('sale.pos.lineStaffPickerTitle')));
const hint = computed(() => (props.mode === 'check' ? t('sale.pos.staffPickerHint') : t('sale.pos.lineStaffPickerHint')));
const meLabel = computed(() => (props.mode === 'check' ? t('sale.pos.staffMeOption') : t('sale.pos.lineStaffTicketOption')));
const empty = computed(() => (term.value ? t('sale.pos.staffNoResults') : t('sale.pos.staffPickerEmpty')));

function onInput(event: CustomEvent<{ value?: string | null }>): void {
  term.value = (event.detail.value ?? '').trim();
}
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="title"
    testid="pos-staff"
  >
    <p
      class="pos-sheet-hint"
      data-testid="pos-staff-hint"
    >
      {{ hint }}
    </p>
    <p
      v-if="mode === 'check' && unlinked"
      class="pos-sheet-hint pos-staff__unlinked"
      role="status"
      data-testid="pos-staff-unlinked"
    >
      {{ $t('sale.pos.staffUnlinked') }}
    </p>
    <div class="pos-staff">
      <button
        type="button"
        class="pos-staff__option"
        data-testid="pos-staff-me"
        :aria-pressed="current === null ? 'true' : 'false'"
        @click="emit('choose', { id: null, name: null })"
      >
        {{ meLabel }}
      </button>
      <ion-searchbar
        :placeholder="$t('sale.pos.staffSearch')"
        :debounce="250"
        :maxlength="100"
        @ion-input="onInput"
      />
      <p
        v-if="error"
        class="pos-sheet-hint"
        role="status"
        data-testid="pos-staff-error"
      >
        {{ $t('sale.pos.staffLoadFailed') }}
      </p>
      <p
        v-else-if="status === 'loading' && !rows.length"
        class="pos-sheet-hint"
        data-testid="pos-staff-loading"
      >
        {{ $t('sale.pos.staffLoading') }}
      </p>
      <p
        v-else-if="!rows.length"
        class="pos-sheet-hint"
        data-testid="pos-staff-empty"
      >
        {{ empty }}
      </p>
      <div
        v-else
        class="pos-staff__list"
      >
        <button
          v-for="row in rows"
          :key="row.id"
          type="button"
          class="pos-staff__option"
          :data-testid="`pos-staff-${row.id}`"
          :aria-pressed="current === row.id ? 'true' : 'false'"
          @click="emit('choose', { id: row.id, name: row.full_name })"
        >
          {{ row.full_name }}
        </button>
      </div>
    </div>
    <template #foot>
      <ion-button
        fill="clear"
        color="medium"
        data-testid="pos-staff-cancel"
        @click="open = false"
      >
        {{ $t('sale.pos.cancel') }}
      </ion-button>
    </template>
  </PosSheet>
</template>

<style scoped>
.pos-staff {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.pos-staff__list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  max-height: min(50vh, 18rem);
  overflow-y: auto;
}
.pos-staff__option {
  width: 100%;
  padding: 0.7rem 0.8rem;
  font: inherit;
  text-align: left;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
  cursor: pointer;
}
.pos-staff__unlinked {
  padding: 0.5rem 0.7rem;
  font-weight: 600;
  color: var(--ion-text-color, #1c1b18);
  background: color-mix(in srgb, var(--ion-color-warning, #ffc409) 18%, transparent);
  border: 1px solid var(--ion-color-warning, #ffc409);
  border-radius: 10px;
}
.pos-staff__option[aria-pressed='true'] {
  font-weight: 700;
  color: var(--ion-color-primary, #0091ce);
  border-color: var(--ion-color-primary, #0091ce);
}
</style>
