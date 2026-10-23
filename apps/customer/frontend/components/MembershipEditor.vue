<script setup lang="ts">
// «Groups» or «Tags» of a card (CUSTOMER-F06): a checkbox per group (tag) of the business, followed
// live; the card's own come ticked. «Save groups» sends the whole selection, which REPLACES the
// previous one; the card's live result then ticks what the server kept. While a tick is not saved, a
// live result of the card (its other list saved, someone else's change) does not undo it. A group no
// longer active is still shown on the cards that have it, marked so. Who cannot manage cards only sees.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonCheckbox, IonSearchbar } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useCustomerI18n } from '../lib/useCustomerI18n';

const props = defineProps<{
  kind: 'groups' | 'tags';
  customerId: string;
  /** The card's groups (tags), as saved. */
  selected: string[];
  editable: boolean;
}>();

const { t } = useCustomerI18n();
const isGroups = computed(() => props.kind === 'groups');
const hook = computed(() => `customer-${props.kind}`);

// The groups (tags) of the business by name, 100 at most (the most a query takes); a business with
// more gets a search on the server. The kind of an editor never changes: it follows only its list.
const search = ref('');
const query = () => ({ limit: 100, sort: 'name' as const, ...(search.value.trim() ? { search: search.value.trim() } : {}) });
const source = props.kind === 'groups' ? useLive('customer.group.list', query) : useLive('customer.tag.list', query);
/** More than one query holds: the search is needed (and stays once it was). */
const searchable = computed(() => search.value !== '' || (source.data.value?.total ?? 0) > rows.value.length);
const rows = computed<{ id: string; name: string; is_active: boolean }[]>(() => source.data.value?.rows ?? []);

const setGroups = useCommand('customer.customer.set_groups');
const setTags = useCommand('customer.customer.set_tags');
const command = computed(() => (isGroups.value ? setGroups : setTags));

const sameSelection = (a: readonly string[], b: readonly string[]): boolean =>
  a.length === b.length && a.every((id) => b.includes(id));

const picked = ref<string[]>([...props.selected]);
/** What the server is known to hold: the card's last result, or what was just saved. */
let saved: readonly string[] = props.selected;
/** The user ticked or unticked something not saved yet. */
const unsaved = ref(false);
watch(
  () => props.selected,
  (now) => {
    saved = now;
    if (!unsaved.value) picked.value = [...now];
    else if (sameSelection(picked.value, now)) unsaved.value = false;
  },
);
watch(
  () => props.customerId,
  () => {
    saved = props.selected;
    unsaved.value = false;
    picked.value = [...props.selected];
  },
);

/** The active ones, and the inactive ones the card has. */
const shown = computed(() => rows.value.filter((row) => row.is_active || props.selected.includes(row.id)));

function toggle(id: string, checked: boolean): void {
  picked.value = checked ? [...picked.value.filter((p) => p !== id), id] : picked.value.filter((p) => p !== id);
  unsaved.value = !sameSelection(picked.value, saved);
}

const label = (row: { name: string; is_active: boolean }): string =>
  row.is_active ? row.name : t('customer.membership.inactive', { name: row.name });

const failure = computed(() => {
  const error = command.value.error.value ?? source.error.value;
  return error && error.code !== 'app_inactive' ? error.message : '';
});

async function save(): Promise<void> {
  const sending = [...picked.value];
  try {
    if (isGroups.value) await setGroups.run({ id: props.customerId, group_ids: sending });
    else await setTags.run({ id: props.customerId, tag_ids: sending });
  } catch {
    return; // `error` holds it: the block shows it.
  }
  // Saved: the card's live results lead again, unless something was ticked while it was on its way.
  saved = sending;
  unsaved.value = !sameSelection(picked.value, sending);
  void toastSuccess(t(isGroups.value ? 'customer.membership.groupsSaved' : 'customer.membership.tagsSaved'));
}
</script>

<template>
  <div
    class="customer-membership"
    :data-testid="hook"
  >
    <h3>{{ isGroups ? $t('customer.membership.groups') : $t('customer.membership.tags') }}</h3>
    <InlineFeedback
      v-if="failure"
      tone="danger"
      :data-testid="`${hook}-error`"
    >
      {{ failure }}
    </InlineFeedback>
    <ion-searchbar
      v-if="searchable"
      class="ion-no-border customer-membership__search"
      :data-testid="`${hook}-search`"
      :value="search"
      :placeholder="isGroups ? $t('customer.groups.search') : $t('customer.tags.search')"
      :debounce="250"
      @ion-input="search = String($event.detail.value ?? '')"
    />
    <p
      v-if="!source.data.value && !failure"
      class="customer-membership__empty"
      :data-testid="`${hook}-loading`"
      role="status"
    >
      {{ $t('customer.common.loading') }}
    </p>
    <p
      v-else-if="source.data.value && shown.length === 0"
      class="customer-membership__empty"
      :data-testid="`${hook}-empty`"
    >
      {{
        search.trim()
          ? $t('customer.picker.noResults')
          : isGroups
            ? $t('customer.membership.noGroups')
            : $t('customer.membership.noTags')
      }}
    </p>
    <div
      v-else-if="shown.length"
      class="customer-membership__chips"
    >
      <ion-checkbox
        v-for="row in shown"
        :key="row.id"
        class="customer-membership__check"
        :data-testid="`${hook}-item-${row.id}`"
        label-placement="end"
        justify="start"
        :checked="picked.includes(row.id)"
        :disabled="!editable"
        @ion-change="toggle(row.id, $event.detail.checked)"
      >
        {{ label(row) }}
      </ion-checkbox>
    </div>
    <ion-button
      v-if="editable && (shown.length || searchable)"
      size="small"
      :data-testid="`${hook}-save`"
      :disabled="command.pending.value"
      @click="save"
    >
      {{ isGroups ? $t('customer.membership.saveGroups') : $t('customer.membership.saveTags') }}
    </ion-button>
  </div>
</template>

<style scoped>
.customer-membership h3 {
  margin: 0.25rem 0 0.5rem;
  font-size: 1rem;
}

.customer-membership__chips {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin: 0.35rem 0;
}

.customer-membership__check {
  margin: 0.15rem 0.9rem 0.15rem 0;
}

.customer-membership__empty {
  margin: 0;
  opacity: 0.7;
}
</style>
