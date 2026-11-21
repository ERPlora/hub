<script setup lang="ts">
// The till's sheet (the product's `.scrim` + `.sheet`): an `ion-modal` as tall as its content — a
// 24rem card on a tablet or a desktop, a sheet from the bottom on a phone — with the title and its ✕,
// the big figure on top (`#top`), the middle that scrolls (default slot) and the foot with the confirm
// button always in view (`#foot`). A tap outside or Escape closes it (Ionic's own dismissal).
//   <PosSheet v-model:open="pricing" :title="t('sale.pos.openPrice')" testid="pos-open-price">…</PosSheet>
// Hooks: `<testid>` (the modal), `-title`, `-close`.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonModal } from '@ionic/vue';

withDefaults(defineProps<{ title: string; testid: string; wide?: boolean }>(), { wide: false });
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ closed: [] }>();

function onDidDismiss(): void {
  open.value = false;
  emit('closed');
}
</script>

<template>
  <ion-modal
    class="pos-sheet"
    :class="{ 'pos-sheet--wide': wide }"
    :is-open="open"
    :aria-label="title"
    :data-testid="testid"
    @did-dismiss="onDidDismiss"
  >
    <div class="pos-sheet__content">
      <div class="pos-sheet__head">
        <h2
          class="pos-sheet__title"
          :data-testid="`${testid}-title`"
        >
          {{ title }}
        </h2>
        <ion-button
          fill="clear"
          class="pos-sheet__close"
          :aria-label="$t('sale.pos.close')"
          :data-testid="`${testid}-close`"
          @click="open = false"
        >
          <HubIcon
            slot="icon-only"
            name="ion:close-outline"
          />
        </ion-button>
      </div>
      <div
        v-if="$slots.top"
        class="pos-sheet__top"
      >
        <slot name="top" />
      </div>
      <div class="pos-sheet__body">
        <slot />
      </div>
      <div
        v-if="$slots.foot"
        class="pos-sheet__foot"
      >
        <slot name="foot" />
      </div>
    </div>
  </ion-modal>
</template>

<style>
/* Not scoped: Ionic moves the modal to ion-app. Every rule hangs from `ion-modal.pos-sheet`. */
ion-modal.pos-sheet {
  --width: min(92vw, 24rem);
  --height: auto;
  --max-height: calc(100vh - 2rem);
  --border-radius: 16px;
  --box-shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
  --backdrop-opacity: 0.6;
}
ion-modal.pos-sheet.pos-sheet--wide {
  --width: min(94vw, 34rem);
}
ion-modal.pos-sheet .ion-delegate-host {
  position: relative;
  display: block;
  contain: content;
}
ion-modal.pos-sheet .pos-sheet__content {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 2rem);
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-background-color, #fff);
}
ion-modal.pos-sheet .pos-sheet__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.75rem 0.5rem 0.25rem 1rem;
}
ion-modal.pos-sheet .pos-sheet__title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
}
ion-modal.pos-sheet .pos-sheet__close {
  margin: 0;
  --color: var(--ion-color-medium, #8b897f);
}
ion-modal.pos-sheet .pos-sheet__top {
  padding: 0 1rem;
}
ion-modal.pos-sheet .pos-sheet__body {
  flex: 1 1 auto;
  min-height: 0;
  padding: 0.25rem 1rem 0.75rem;
  overflow-y: auto;
}
ion-modal.pos-sheet .pos-sheet__foot {
  position: sticky;
  bottom: 0;
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.75rem 1rem 1rem;
  background: var(--ion-background-color, #fff);
  border-top: 1px solid var(--ion-border-color, #e6e3db);
}
ion-modal.pos-sheet .pos-sheet__foot ion-button {
  margin: 0;
}
/* The parts every sheet uses: the big figure, a section label, the foot's column (refusal over the
   confirm button), the refusal and the confirm button. */
ion-modal.pos-sheet .pos-sheet-figure {
  margin: 0.2rem 0 0.6rem;
  font-size: 2.4rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  text-align: center;
}
ion-modal.pos-sheet .pos-sheet-label {
  margin: 0.8rem 0 0.4rem;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ion-color-medium, #8b897f);
}
ion-modal.pos-sheet .pos-sheet-hint {
  margin: 0.4rem 0;
  font-size: 0.86rem;
  color: var(--ion-color-medium, #8b897f);
}
ion-modal.pos-sheet .pos-sheet-foot {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.4rem;
}
ion-modal.pos-sheet .pos-sheet-actions {
  display: flex;
  gap: 0.5rem;
}
ion-modal.pos-sheet .pos-sheet-actions ion-button {
  flex: 1;
}
ion-modal.pos-sheet .pos-sheet-error {
  margin: 0;
  color: var(--ion-color-danger, #d9480f);
}
ion-modal.pos-sheet .pos-sheet-confirm {
  min-height: 3rem;
  margin: 0;
  font-weight: 700;
  text-transform: none;
}
ion-modal.pos-sheet .pos-sheet-danger {
  --background: var(--ion-color-danger, #c5000f);
  --color: var(--ion-color-danger-contrast, #fff);
}
ion-modal.pos-sheet .pos-sheet-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.3rem 0 0.6rem;
}
ion-modal.pos-sheet .pos-sheet-chip {
  min-height: 2.25rem;
  padding: 0 0.85rem;
  font: inherit;
  font-size: 0.85rem;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 999px;
  cursor: pointer;
}
ion-modal.pos-sheet .pos-sheet-chip[aria-pressed='true'] {
  color: var(--ion-color-primary-contrast, #fff);
  background: var(--ion-color-primary, #0091ce);
  border-color: var(--ion-color-primary, #0091ce);
}
ion-modal.pos-sheet .pos-sheet-text {
  box-sizing: border-box;
  width: 100%;
  padding: 0.6rem 0.7rem;
  font: inherit;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-background-color, #fff);
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
  resize: vertical;
}
/* Phone: a sheet from the bottom, with the top corners rounded. */
@media (max-width: 820px) {
  ion-modal.pos-sheet,
  ion-modal.pos-sheet.pos-sheet--wide {
    --width: 100%;
    --max-width: 100%;
    --border-radius: 18px 18px 0 0;
    align-items: flex-end;
  }
  ion-modal.pos-sheet .pos-sheet__foot {
    padding-bottom: calc(1rem + var(--ion-safe-area-bottom, 0px));
  }
}
</style>
