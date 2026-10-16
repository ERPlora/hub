<script setup lang="ts">
// WHATSAPP_INBOX-F33 (send a template): the only way to write after Meta's 24-hour window, and the way
// to start a conversation. The templates Meta approved (the local copy erplora.com keeps in step) are
// offered with their language, category and text; the chosen one asks for its variables and previews
// the text as it will go out. «Send» goes through erplora.com (`whatsapp_inbox.message.send`) with a key
// of its own, so pressing it again never sends twice; the dialog closes only when it was sent, and a
// refusal (marketing without consent, erplora.com down) stays on top of it.
import { FormModal } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonInput, IonItem, IonLabel, IonRadio, IonRadioGroup } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { renderTemplate } from '../lib/thread';
import type { TemplateOut } from '../operations';

const props = defineProps<{ conversationId: string }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const { data: templates } = useLive('whatsapp_inbox.template.list', () => ({ status: 'APPROVED' as const, limit: 100 }));
const { run, error, pending } = useCommand('whatsapp_inbox.message.send');

const chosenId = ref('');
const values = ref<string[]>([]);
/** One key per template being sent: a retry after a silence never sends it twice. */
const key = ref(crypto.randomUUID());

const chosen = computed<TemplateOut | undefined>(() => templates.value?.rows.find((row) => row.id === chosenId.value));
const complete = computed(() => !!chosen.value && values.value.length === chosen.value.variables && values.value.every((v) => v.trim() !== ''));
const preview = computed(() => (chosen.value ? renderTemplate(chosen.value.body, values.value.map((v) => v.trim())) : ''));

function reset(): void {
  chosenId.value = '';
  values.value = [];
  key.value = crypto.randomUUID();
  error.value = null;
}

function choose(id: unknown): void {
  // The key stays until the hub takes the message: a failed send may have reached it.
  chosenId.value = String(id ?? '');
  values.value = Array.from({ length: chosen.value?.variables ?? 0 }, () => '');
}

function setValue(index: number, value: unknown): void {
  const next = [...values.value];
  next[index] = value == null ? '' : String(value);
  values.value = next;
}

async function send(): Promise<void> {
  const template = chosen.value;
  if (!template || !complete.value) return;
  try {
    await run({
      id: props.conversationId,
      template: { name: template.name, language: template.language, variables: values.value.map((v) => v.trim()) },
      client_message_id: key.value,
    });
  } catch {
    return; // `error` holds it and the dialog paints it.
  }
  reset();
  open.value = false;
}

watch(open, (isOpen) => {
  if (!isOpen) reset();
});
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="whatsapp-inbox-template-form"
    :title="t('whatsapp_inbox.templates.sendTitle')"
    :submit-label="t('whatsapp_inbox.templates.send')"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="send"
    @cancel="reset"
  >
    <div class="wa-template">
      <p
        v-if="templates && !templates.rows.length"
        class="wa-template__none"
        data-testid="whatsapp-inbox-template-none"
      >
        {{ $t('whatsapp_inbox.templates.none') }}
      </p>
      <ion-radio-group
        v-else
        :value="chosenId"
        :aria-label="$t('whatsapp_inbox.templates.pick')"
        data-testid="whatsapp-inbox-template-pick"
        @ion-change="choose($event.detail.value)"
      >
        <ion-item
          v-for="row in templates?.rows ?? []"
          :key="row.id"
          lines="full"
        >
          <ion-radio
            :value="row.id"
            justify="start"
            label-placement="end"
          >
            <ion-label class="ion-text-wrap">
              <div :data-testid="`whatsapp-inbox-template-option-${row.id}`">
                <strong>{{ row.name }}</strong>
                <span class="wa-template__meta"> · {{ row.language }} · {{ $t(`whatsapp_inbox.templates.categories.${row.category}`) }}</span>
                <p>{{ row.body }}</p>
              </div>
            </ion-label>
          </ion-radio>
        </ion-item>
      </ion-radio-group>
      <template v-if="chosen">
        <ion-input
          v-for="(value, index) in values"
          :key="`${chosen.id}-${index}`"
          :data-testid="`whatsapp-inbox-template-variable-${index + 1}`"
          :value="value"
          :label="t('whatsapp_inbox.templates.variable', { n: index + 1 })"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="1024"
          @ion-input="setValue(index, $event.detail.value)"
        />
        <section
          class="wa-template__preview"
          data-testid="whatsapp-inbox-template-preview"
        >
          <span class="wa-template__meta">{{ $t('whatsapp_inbox.templates.preview') }}</span>
          <p>{{ preview }}</p>
        </section>
      </template>
    </div>
  </FormModal>
</template>

<style scoped>
.wa-template {
  display: grid;
  gap: 12px;
}
.wa-template__none {
  margin: 0;
  color: var(--ion-color-medium-shade);
}
.wa-template__meta {
  font-size: 0.8rem;
  color: var(--ion-color-medium-shade);
}
.wa-template__preview {
  border-radius: 12px;
  padding: 0.5rem 0.75rem;
  background: var(--ion-color-primary-tint, #d0ebff);
}
.wa-template__preview p {
  margin: 0.2rem 0 0;
  white-space: pre-wrap;
}
</style>
