<script setup lang="ts">
// «Groups» or «Tags» of a card (CUSTOMER-F06): a checkbox per group (tag) of the business, followed
// live; the card's own come ticked. «Save groups» sends the whole selection, which REPLACES the
// previous one; the card's live result then ticks what the server kept. What the user ticked or
// unticked and has not saved stays so through a live result of the card (its other list saved, someone
// else's change); the rest follows the card, and what is no longer seen is not sent. A group no
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

// What the user touched and has not saved yet, over what the server is known to hold (the card's
// last result, or what was just saved). A live result of the card moves only the rest: what someone
// else added, deleted or took off and the user did not touch follows the card.
const saved = ref<string[]>([...props.selected]);
const ticked = ref<string[]>([]);
const unticked = ref<string[]>([]);

watch(
  () => props.selected,
  (now) => {
    saved.value = [...now];
    ticked.value = ticked.value.filter((id) => !now.includes(id));
    unticked.value = unticked.value.filter((id) => now.includes(id));
  },
);
watch(
  () => props.customerId,
  () => {
    saved.value = [...props.selected];
    ticked.value = [];
    unticked.value = [];
  },
);

/** The whole list is here (no search, nothing past the 100 a query takes): a group not in it is gone. */
const wholeList = computed(() => source.status.value === 'live' && !search.value.trim() && (source.data.value?.total ?? 0) <= rows.value.length);
/** A group (tag) that is no longer seen: not on the card, and deleted, or no longer active. */
function unseen(id: string): boolean {
  if (saved.value.includes(id) || props.selected.includes(id)) return false;
  const row = rows.value.find((r) => r.id === id);
  return row ? !row.is_active : wholeList.value;
}

/** The selection as seen: what is saved, with the user's ticks and unticks. */
const picked = computed(() =>
  [...saved.value.filter((id) => !unticked.value.includes(id)), ...ticked.value.filter((id) => !saved.value.includes(id))].filter(
    (id) => !unseen(id),
  ),
);

/** The active ones, and the inactive ones the card has. */
const shown = computed(() => rows.value.filter((row) => row.is_active || props.selected.includes(row.id)));

function toggle(id: string, checked: boolean): void {
  const onCard = saved.value.includes(id);
  ticked.value = ticked.value.filter((p) => p !== id);
  unticked.value = unticked.value.filter((p) => p !== id);
  if (checked && !onCard) ticked.value.push(id);
  if (!checked && onCard) unticked.value.push(id);
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
    // One deleted meanwhile: what the list no longer has leaves the selection, so the next save works.
    if (command.value.error.value?.code === (isGroups.value ? 'customer.group_unavailable' : 'customer.tag_unavailable')) {
      ticked.value = ticked.value.filter((id) => rows.value.some((row) => row.id === id));
    }
    return; // `error` holds it: the block shows it.
  }
  // Saved: the card's live results lead again; what was touched while it was on its way stays touched.
  const now = picked.value;
  saved.value = sending;
  ticked.value = now.filter((id) => !sending.includes(id));
  unticked.value = sending.filter((id) => !now.includes(id));
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
