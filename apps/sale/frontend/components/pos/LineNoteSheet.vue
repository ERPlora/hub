<script setup lang="ts">
// «Note on <item>» (SALE-F13): the quick-note chips, the box (up to 255 characters) with what the line
// already says, «The kitchen reads this note on the ticket.», and «Remove» | «Save». Saving trims the
// text; an empty note (or «Remove») takes it off. The page writes it (`sale.order.update_line`); a
// refusal is read here, over the buttons. The box starts again from the line's note on every opening.
import { IonButton } from '@ionic/vue';
import { shallowRef, watch } from 'vue';

import PosSheet from './PosSheet.vue';
import QuickNoteChips from './QuickNoteChips.vue';

const props = defineProps<{ name: string; note: string; pending: boolean; error: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ save: [note: string] }>();

const text = shallowRef(props.note);
watch(
  () => [open.value, props.note] as const,
  ([isOpen, note]) => {
    if (isOpen) text.value = note;
  },
);
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="$t('sale.pos.lineNoteOf', { name })"
    testid="pos-note"
  >
    <QuickNoteChips v-model="text" />
    <textarea
      v-model="text"
      class="pos-sheet-text"
      data-testid="pos-note-text"
      rows="3"
      maxlength="255"
      :aria-label="$t('sale.pos.lineNote')"
      :placeholder="$t('sale.pos.lineNotePlaceholder')"
    />
    <p
      class="pos-sheet-hint"
      data-testid="pos-note-hint"
    >
      {{ $t('sale.pos.lineNoteHint') }}
    </p>
    <template #foot>
      <div class="pos-sheet-foot">
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-note-error"
        >
          {{ error }}
        </p>
        <div class="pos-sheet-actions">
          <ion-button
            fill="clear"
            color="medium"
            data-testid="pos-note-remove"
            :disabled="pending"
            @click="emit('save', '')"
          >
            {{ $t('sale.pos.lineNoteRemove') }}
          </ion-button>
          <ion-button
            class="pos-sheet-confirm"
            data-testid="pos-note-save"
            :disabled="pending"
            @click="emit('save', text.trim())"
          >
            {{ $t('sale.pos.lineNoteSave') }}
          </ion-button>
        </div>
      </div>
    </template>
  </PosSheet>
</template>
