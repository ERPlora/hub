<template>
  <!-- No band unless the runtime is going to reject the sale. Not an empty box, not a spacer:
       nothing. This sits over EVERY screen of the product, so «harmless when idle» is not good
       enough — silence is the default and the strip has to earn its way out of it. -->
  <ok-inline-feedback
    v-if="view.visible"
    class="setup-strip"
    tone="danger"
    icon="alert-circle-outline"
    :heading="t('setup.blocking.title')"
    data-testid="setup-strip"
  >
    <!-- The consequence first. «Your business details» on its own reads as one more chore; what
         justifies a band across the whole app is that the hub will REFUSE to issue the document. -->
    <p class="setup-strip-body">{{ t('setup.blocking.body') }}</p>
    <ul class="setup-strip-items">
      <li
        v-for="item in view.items"
        :key="item.key"
        class="setup-strip-item"
        :data-testid="`setup-strip-item-${item.key}`"
      >
        <HubIcon class="setup-strip-icon" :name="item.icon || 'settings-outline'" />
        <span class="setup-strip-name">{{ titleOf(item) }}</span>
        <!-- One way in PER thing missing. There are at most two gates (the business identity and the
             certificate), so picking a «primary» one would hide the other behind a guess. -->
        <ion-button
          v-if="isActionable(item)"
          class="setup-strip-cta"
          size="small"
          fill="outline"
          color="danger"
          :router-link="item.route"
          router-direction="forward"
          :data-testid="`setup-strip-action-${item.key}`"
        >
          {{ t('setup.configure') }}
        </ion-button>
        <!-- …and when the way in is not THIS session's to take (hub#435), who can take it. The band
             cannot be dismissed, so a name with neither a button nor an errand is a dead end. -->
        <span v-else class="setup-strip-note" :data-testid="`setup-strip-note-${item.key}`">
          {{ t('setup.delegatedHint') }}
        </span>
      </li>
    </ul>
  </ok-inline-feedback>
</template>

<script setup lang="ts">
// The blocking strip (hub#374) — the third surface of `hub.setup.status`
// (`architecture/hub/setup-status.md`, ADR-0224/0227/0229).
//
// It exists because the two surfaces before it live on the panel, and **whoever works the till never
// opens the panel**. The claim it makes is not «you have things left to configure» (that is the
// card's job): it is that the dispatcher is going to reject the operation — ⛔ is the runtime's own
// verdict, not a colour. Three rules follow from that:
//
// * **It rises for `blocking_pending` and nothing else.** A 🔴 or a 🟡 never raises it. A band that
//   is up on a hub that sells and invoices perfectly teaches people to look past it, and then it is
//   not there when it matters.
// * **It names what is missing and leads to it.** It cannot be dismissed, so a strip without a way
//   out would be a permanent dead end. If the payload cannot be named, it stays down (`blockingView`).
//   When the way out is not this session's to take (hub#435) the way out is a NAME, not a button:
//   whoever is at the till cannot type the tax id, but the refusal is going to land on them.
// * **It does not repeat the panel's card.** Same items, same call to action, one screenful apart.
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton } from '@ionic/vue';

import HubIcon from './HubIcon.vue';
import { blockingView, isActionable, type SetupItem, type SetupStatus } from '../lib/setup-status';

const props = withDefaults(
  defineProps<{
    /** The document `hub.setup.status` answered. `null` until there is an answer. */
    status: SetupStatus | null;
    /** This screen already paints the whole checklist (the panel's card) — stand down there. */
    checklistOnScreen?: boolean;
  }>(),
  { checklistOnScreen: false },
);

const { t, te } = useI18n();

const view = computed(() => blockingView(props.status, { checklistOnScreen: props.checklistOnScreen }));

/**
 * The item's title. A CORE item's key is also its i18n key; a module's `title` travels in English
 * inside its manifest and the runtime does not localize it yet (`setup-status.md` §7), so that is
 * what gets painted. A raw key never reaches the screen.
 */
function titleOf(item: SetupItem): string {
  const key = `setup.items.${item.key}.title`;
  return (te(key) ? t(key) : '') || item.title || item.key;
}
</script>

<style scoped>
/* Page chrome, not content: it lives between the topbar and the scroller so it cannot scroll away.
   `ok-inline-feedback` already brings the tonal background and the accent rail of the danger tone —
   this only gives it the margins of a band and lays out the list. */
.setup-strip {
  --border-radius: 0;
  --padding: 0.7rem 1rem;
  flex: none;
}
.setup-strip-body {
  margin: 0;
  font-size: 0.875rem;
}
.setup-strip-items {
  list-style: none;
  margin: 0.4rem 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1.25rem;
}
.setup-strip-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}
.setup-strip-icon {
  font-size: 1.05rem;
  flex: none;
  color: var(--ion-color-danger, #c5000f);
}
.setup-strip-name {
  font-size: 0.875rem;
  font-weight: 600;
}
.setup-strip-cta {
  flex: none;
  white-space: nowrap;
  text-transform: none;
}
/* The stand-in for the button when the errand is somebody else's: same row, plainly not pressable. */
.setup-strip-note {
  flex: none;
  font-size: 0.8125rem;
  font-style: italic;
  opacity: 0.85;
}
</style>
