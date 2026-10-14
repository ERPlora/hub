<script setup lang="ts">
// The quick notes over the line-note box (SALE-F13, F36): the business's notes in their order as
// chips, a window at a time; a chip is pressed while the note holds it, a tap adds it after a comma or
// takes it out (never twice). «Loading quick notes…» meanwhile; if they cannot be read, the note is
// typed by hand. Mounted only while the note sheet is open.
import { IonButton } from '@ionic/vue';

import { useLiveWindows } from '../../composables/pos/useLiveWindows';
import type { QuickNoteOut } from '../../operations';
import { noteHasChip, toggleNoteChip } from './till';

const text = defineModel<string>({ required: true });

const notes = useLiveWindows<'sale.quick_note.list', QuickNoteOut>(
  'sale.quick_note.list',
  () => ({ sort: 'sort_order', dir: 'asc' }),
  24,
);
</script>

<template>
  <p
    v-if="notes.error.value"
    class="pos-sheet-hint"
    role="status"
    data-testid="pos-quick-notes-error"
  >
    {{ $t('sale.pos.lineNoteQuickError') }}
  </p>
  <p
    v-else-if="notes.status.value === 'loading' && !notes.rows.value.length"
    class="pos-sheet-hint"
    data-testid="pos-quick-notes-loading"
  >
    {{ $t('sale.pos.lineNoteQuickLoading') }}
  </p>
  <div
    v-if="notes.rows.value.length"
    class="pos-sheet-chips"
  >
    <button
      v-for="item in notes.rows.value"
      :key="item.id"
      type="button"
      class="pos-sheet-chip"
      :data-testid="`pos-quick-note-${item.id}`"
      :aria-pressed="noteHasChip(text, item.text) ? 'true' : 'false'"
      @click="text = toggleNoteChip(text, item.text)"
    >
      {{ item.text }}
    </button>
    <ion-button
      v-if="notes.hasMore.value"
      size="small"
      fill="clear"
      data-testid="pos-quick-notes-more"
      @click="notes.loadMore()"
    >
      {{ $t('sale.pos.loadMore') }}
    </ion-button>
  </div>
</template>
