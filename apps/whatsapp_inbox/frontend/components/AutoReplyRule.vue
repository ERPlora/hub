<script setup lang="ts">
// How the bookings by WhatsApp confirm (WHATSAPP_INBOX-F16), under a card of «What do you use it for?» that is on:
// Citas' «confirm the customer's bookings by themselves» (`auto_confirm_online`) or Reservas' «confirm new
// reservations by themselves» (`auto_confirm`), read live and saved at once in that app, never in this one. Mounted only
// under a card that is on, so nobody else subscribes to the rule. Each choice is a full-width row whose words wrap
// (whatsapp_inbox#285: a segment cut «Las reservas se co…» on a phone).
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonItem, IonList, IonRadio, IonRadioGroup } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';

type Choice = 'auto' | 'review';

const props = defineProps<{ which: 'appointments' | 'tables' }>();
const t = useT();

const appointments = props.which === 'appointments';
const rule = appointments ? useLive('appointment.settings.get', {}) : useLive('reservation.settings.get', {});
const saveAppointments = useCommand('appointment.settings.update');
const saveTables = useCommand('reservation.settings.update');

const saved = computed<Choice | null>(() => {
  const data = rule.data.value as { auto_confirm_online?: boolean; auto_confirm?: boolean } | undefined;
  if (!data) return null;
  return (appointments ? data.auto_confirm_online : data.auto_confirm) ? 'auto' : 'review';
});
const chosen = ref<Choice | null>(null);
const failed = ref(false);
watch(saved, (value) => (chosen.value = value), { immediate: true });

async function choose(value: Choice): Promise<void> {
  if (value === chosen.value) return;
  const before = chosen.value;
  chosen.value = value;
  failed.value = false;
  try {
    if (appointments) await saveAppointments.run({ auto_confirm_online: value === 'auto' });
    else await saveTables.run({ auto_confirm: value === 'auto' });
  } catch {
    failed.value = true;
    chosen.value = before;
  }
}
</script>

<template>
  <div
    class="wa-rule"
    :data-testid="`whatsapp-inbox-autoreply-${which}-confirm`"
  >
    <p
      v-if="chosen === null"
      class="wa-rule__hint"
      :data-testid="`whatsapp-inbox-autoreply-${which}-confirm-loading`"
    >
      {{ t('whatsapp_inbox.loading') }}
    </p>
    <template v-else>
      <IonList
        lines="none"
        class="wa-rule__list"
      >
        <IonRadioGroup
          :value="chosen"
          @ion-change="choose($event.detail.value)"
        >
          <IonItem class="wa-rule__item">
            <IonRadio
              value="auto"
              justify="start"
              label-placement="end"
            >
              {{ t(`whatsapp_inbox.autoReplies.${which}.confirmSelf`) }}
            </IonRadio>
          </IonItem>
          <IonItem class="wa-rule__item">
            <IonRadio
              value="review"
              justify="start"
              label-placement="end"
            >
              {{ t('whatsapp_inbox.autoReplies.reviewFirst') }}
            </IonRadio>
          </IonItem>
        </IonRadioGroup>
      </IonList>
      <p
        v-if="chosen === 'review'"
        class="wa-rule__hint"
        :data-testid="`whatsapp-inbox-autoreply-${which}-review`"
      >
        {{ t(`whatsapp_inbox.autoReplies.${which}.review`) }}
      </p>
    </template>
    <InlineFeedback
      v-if="failed"
      tone="danger"
      :data-testid="`whatsapp-inbox-autoreply-${which}-confirm-error`"
      :heading="t(`whatsapp_inbox.autoReplies.${which}.confirmError`)"
    />
  </div>
</template>

<style scoped>
.wa-rule {
  display: grid;
  gap: var(--ep-space-2, 8px);
}

.wa-rule__list {
  padding: 0;
  background: transparent;
}

.wa-rule__item {
  --background: transparent;
  --padding-start: 0;
  --inner-padding-end: 0;
}

/* The choice's words wrap on a phone instead of ending in «…» (whatsapp_inbox#285). */
.wa-rule__item ion-radio::part(label) {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
}

.wa-rule__hint {
  margin: 0;
  color: var(--ep-text-muted, var(--ion-color-medium));
  font-size: 0.875rem;
}
</style>
