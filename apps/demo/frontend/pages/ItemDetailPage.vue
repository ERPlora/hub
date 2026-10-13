<script setup lang="ts">
// Detail of a demo item (DEMO-F02–F06). The note has LOCAL state: a new result never overwrites
// text being written, it only warns «Updated elsewhere». «Add line» is optimistic: the line shows
// at once (faded) on this screen and the list, and the SDK undoes it if the server refuses (409 on
// a done item). The server always wins: its next result replaces every provisional line. «Edit»
// opens the item's form as its own page.
import { InlineFeedback } from '@erplora/ui/components';
import { fieldErrors, type InputOf, type OutputOf, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastError, useSession } from '@erplora/ui/shell';
import { IonAlert, IonBadge, IonButton, IonChip, IonInput, IonSpinner, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import ItemLines, { type ShownLine } from '../components/ItemLines.vue';

const props = defineProps<{ id: string }>();

type Detail = OutputOf<'demo.item.detail'>;
type LineIn = InputOf<'demo.item.add_line'>;

const router = useRouter();
const session = useSession();
const canManage = computed(() => session.can('demo.manage'));
const { data: item, status, error } = useLive('demo.item.detail', () => ({ id: props.id }));

// ── Note: local state, never overwritten while it is being written ─────────────────────────────
const note = ref('');
/** The server text the local note started from. */
const syncedNote = ref<string | undefined>(undefined);
const noteStale = ref(false);
/** Before the first result there is nothing to protect. */
const noteDirty = computed(() => syncedNote.value !== undefined && note.value !== syncedNote.value);

function takeServerNote(): void {
  syncedNote.value = item.value?.note ?? '';
  note.value = syncedNote.value;
  noteStale.value = false;
}

watch(
  () => item.value?.note,
  (server) => {
    if (server === undefined) return;
    if (!noteDirty.value || server === note.value) takeServerNote();
    else if (server !== syncedNote.value) noteStale.value = true;
  },
  { immediate: true },
);

// ── Commands ───────────────────────────────────────────────────────────────────────────────────
/** Runs a command; a failure that belongs to no field goes to a toast with the server message. */
async function attempt(run: () => Promise<unknown>): Promise<boolean> {
  try {
    await run();
    return true;
  } catch (err) {
    if (Object.keys(fieldErrors(err)).length === 0) void toastError(err instanceof Error ? err.message : String(err));
    return false;
  }
}

const { run: update, pending: updating } = useCommand('demo.item.update');

async function saveNote(): Promise<void> {
  const text = note.value;
  if (await attempt(() => update({ id: props.id, note: text }))) {
    syncedNote.value = text;
    noteStale.value = false;
  }
}

const toggleDone = () =>
  attempt(() => update({ id: props.id, status: item.value?.status === 'done' ? 'open' : 'done' }));

/** The provisional line, keyed by `client_line_id` like the one the server will save. */
function withLine(current: Detail, input: LineIn): Detail {
  if (current.lines.some((l) => l.client_line_id === input.client_line_id)) return current;
  const line: ShownLine = {
    id: input.client_line_id ?? '',
    text: input.text,
    qty: String(input.qty),
    position: (current.lines.at(-1)?.position ?? 0) + 1,
    client_line_id: input.client_line_id ?? null,
    pending: true,
  };
  return { ...current, line_count: current.line_count + 1, lines: [...current.lines, line] };
}

// Overlays change only a result that already arrived; before it, `undefined` lays none.
const addLine = useCommand('demo.item.add_line', {
  optimistic: {
    'demo.item.detail': (current, input) => (current ? withLine(current, input) : undefined),
    'demo.item.list': (current, input) =>
      current
        ? { ...current, rows: current.rows.map((r) => (r.id === input.id ? { ...r, line_count: r.line_count + 1 } : r)) }
        : undefined,
  },
});
const lineErrors = computed(() => fieldErrors(addLine.error.value));
const lineText = ref('');
const lineQty = ref<string | number>('1');

async function submitLine(): Promise<void> {
  const input: LineIn = { id: props.id, text: lineText.value, qty: lineQty.value, client_line_id: crypto.randomUUID() };
  lineText.value = '';
  // Back to the field to retry, unless something new was typed meanwhile.
  if (!(await attempt(() => addLine.run(input))) && lineText.value === '') lineText.value = input.text;
}

const { run: remove } = useCommand('demo.item.delete');
const confirmingDelete = ref(false);

async function onDeleteDismissed(event: CustomEvent<{ role?: string }>): Promise<void> {
  confirmingDelete.value = false;
  if (event.detail.role !== 'destructive') return;
  if (await attempt(() => remove({ id: props.id }))) await router.replace('/demo/items');
}
</script>

<template>
  <AppPage
    :title="item?.name ?? $t('demo.detail.title')"
    back-href="/demo/items"
    content-layout="detail"
  >
    <template
      v-if="canManage && item"
      #actions
    >
      <ion-button
        data-testid="demo-detail-edit"
        @click="router.push(`/demo/items/${id}/edit`)"
      >
        {{ $t('demo.detail.edit') }}
      </ion-button>
      <ion-button
        data-testid="demo-detail-toggle"
        :disabled="updating"
        @click="toggleDone"
      >
        {{ item.status === 'done' ? $t('demo.detail.reopen') : $t('demo.detail.markDone') }}
      </ion-button>
      <ion-button
        color="danger"
        data-testid="demo-detail-delete"
        @click="confirmingDelete = true"
      >
        {{ $t('demo.detail.delete') }}
      </ion-button>
    </template>

    <ion-chip
      v-if="status === 'reconnecting'"
      color="warning"
      data-testid="demo-detail-reconnecting"
    >
      {{ $t('demo.live.reconnecting') }}
    </ion-chip>
    <InlineFeedback
      v-if="status === 'error'"
      tone="warning"
      data-testid="demo-detail-error"
      :heading="error?.code === 'app_inactive' ? $t('demo.live.appInactive') : $t('demo.detail.loadError')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <div
      v-if="!item && status === 'loading'"
      class="ion-text-center ion-padding"
    >
      <ion-spinner data-testid="demo-detail-loading" />
    </div>

    <template v-if="item">
      <ion-badge
        data-testid="demo-detail-status"
        :color="item.status === 'done' ? 'success' : 'primary'"
      >
        {{ item.status === 'done' ? $t('demo.status.done') : $t('demo.status.open') }}
      </ion-badge>

      <section class="demo-section">
        <InlineFeedback
          v-if="noteStale"
          tone="info"
          data-testid="demo-note-stale"
          :heading="$t('demo.detail.updatedElsewhere')"
        >
          {{ $t('demo.detail.updatedElsewhereBody') }}
          <template #actions>
            <ion-button
              size="small"
              fill="outline"
              data-testid="demo-note-reload"
              @click="takeServerNote"
            >
              {{ $t('demo.detail.reload') }}
            </ion-button>
          </template>
        </InlineFeedback>
        <ion-textarea
          v-model="note"
          data-testid="demo-note"
          :label="$t('demo.detail.note')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :readonly="!canManage"
        />
        <ion-button
          v-if="canManage"
          data-testid="demo-note-save"
          :disabled="!noteDirty || updating"
          @click="saveNote"
        >
          {{ $t('demo.detail.saveNote') }}
        </ion-button>
      </section>

      <h2>{{ $t('demo.detail.lines') }}</h2>
      <ItemLines :lines="item.lines" />
      <form
        v-if="canManage"
        class="demo-line-form"
        data-testid="demo-line-form"
        novalidate
        @submit.prevent="submitLine"
      >
        <ion-input
          v-model="lineText"
          data-testid="demo-line-input-text"
          :label="$t('demo.detail.lineText')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="lineErrors.text"
          :class="{ 'ion-invalid': !!lineErrors.text, 'ion-touched': !!lineErrors.text }"
        />
        <ion-input
          v-model="lineQty"
          data-testid="demo-line-input-qty"
          type="number"
          inputmode="decimal"
          step="any"
          :label="$t('demo.detail.lineQty')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="lineErrors.qty"
          :class="{ 'ion-invalid': !!lineErrors.qty, 'ion-touched': !!lineErrors.qty }"
        />
        <ion-button
          type="submit"
          data-testid="demo-line-add"
          :disabled="!lineText.trim()"
        >
          {{ $t('demo.detail.addLine') }}
        </ion-button>
      </form>
    </template>

    <ion-alert
      :is-open="confirmingDelete"
      :header="$t('demo.detail.deleteConfirm')"
      :buttons="[
        { text: $t('demo.detail.cancel'), role: 'cancel' },
        { text: $t('demo.detail.delete'), role: 'destructive' },
      ]"
      @did-dismiss="onDeleteDismissed"
    />
  </AppPage>
</template>

<style scoped>
.demo-section {
  display: grid;
  gap: 12px;
  margin-block: 16px;
}

.demo-line-form {
  display: grid;
  grid-template-columns: 1fr 8rem auto;
  gap: 12px;
  align-items: start;
  margin-top: 12px;
}

@media (max-width: 575px) {
  .demo-line-form {
    grid-template-columns: 1fr;
  }
}
</style>
