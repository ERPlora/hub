<script setup lang="ts">
// «Waiting for your answer» (WORKBOOK FLOW-F29; the old module's flows-f24; `flow.question.list`, live): every
// question an automation asked and waits on that this person may answer — their role's, or all of them for
// whoever runs the business —, the soonest to expire first. Each card says the question as it was asked,
// who it was asked of, what silence and a no do, and takes an optional note and «Approve» or «No»; it leaves
// when answered. A refusal (too late, already answered, the automation paused) stays on its card. With no
// question the section hides, unless it is all the page shows (`alone`). The change the assistant wants
// (FLOW-F38) lists each datum it would send as its card in the chat says it (BASE-F97 step 2, base's
// `fieldLines`): in words, an amount in the business's currency, the empty ones left out.
import { InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';

import { fieldLines } from '../../../../base/frontend/lib/assistant-card';
import { useBusinessMoney } from '../../../../base/frontend/lib/money';
import { useLocale, useT } from '../composables/useT';
import { formatDate } from '../lib/phrasing';
import { wording } from '../lib/refusal';
import type { QuestionOut } from '../operations';

const props = defineProps<{ /** It is all the page shows: it says when there is nothing. */ alone?: boolean }>();

const t = useT();
const locale = useLocale();
const questions = useLive('flow.question.list', {});
const answer = useCommand('flow.question.answer');
const rows = computed(() => questions.data.value?.rows ?? []);
const loadError = computed(() => (questions.error.value ? wording(questions.error.value, t('flow.errors.read')) : ''));
const shown = computed(() => props.alone || rows.value.length > 0 || !!loadError.value);
const money = useBusinessMoney();
/** Each question's data, one line each, by its id: none for a question with no change of the assistant. */
const data = computed(() => {
  const format = { locale: locale.value, money: money.value, t };
  return Object.fromEntries(
    rows.value.map((question) => [question.id, fieldLines((question.fields ?? []).filter((field) => field.kind !== 'empty'), format)]),
  );
});
const notes = ref<Record<string, string>>({});
const problems = ref<Record<string, string>>({});
const busy = ref<string | null>(null);

function who(question: QuestionOut): string {
  return question.role ? t('flow.inbox.askedOf', { who: t(`flow.ask.roles.${question.role}`) }) : t('flow.inbox.askedOfAdmin');
}

function silence(question: QuestionOut): string {
  const date = formatDate(question.expires_at, locale.value);
  if (question.on_timeout === 'no') return t('flow.inbox.silenceNo', { date });
  return t(question.on_timeout === 'stop' ? 'flow.inbox.silenceStop' : 'flow.inbox.silenceContinue', { date });
}

async function decide(question: QuestionOut, approve: boolean): Promise<void> {
  problems.value = { ...problems.value, [question.id]: '' };
  busy.value = question.id;
  try {
    await answer.run({ id: question.id, approve, note: notes.value[question.id] ?? '' });
    void toastSuccess(t(approve ? 'flow.inbox.approved' : 'flow.inbox.rejected'));
  } catch (failure) {
    problems.value = { ...problems.value, [question.id]: wording(failure as ApiError, t('flow.errors.action')) };
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <section
    v-if="shown"
    class="flow-inbox"
    data-testid="flow-inbox"
  >
    <h2 class="flow-section">
      {{ $t('flow.inbox.heading') }}
    </h2>
    <InlineFeedback
      v-if="loadError"
      tone="danger"
      data-testid="flow-inbox-error"
    >
      {{ loadError }}
    </InlineFeedback>
    <p
      v-else-if="!questions.data.value"
      class="flow-inbox__muted"
      data-testid="flow-inbox-loading"
    >
      <IonSpinner name="dots" /> {{ $t('flow.inbox.loading') }}
    </p>
    <p
      v-else-if="!rows.length"
      class="flow-inbox__muted"
      data-testid="flow-inbox-empty"
    >
      {{ $t('flow.inbox.empty') }}
    </p>
    <article
      v-for="question in rows"
      :key="question.id"
      class="flow-inbox__card"
      :data-testid="`flow-question-${question.id}`"
    >
      <span class="flow-inbox__from">{{ $t('flow.inbox.from', { name: question.flow_name }) }}</span>
      <strong
        class="flow-inbox__title"
        :data-testid="`flow-question-title-${question.id}`"
      >{{ question.title }}</strong>
      <p
        v-if="question.details"
        class="flow-inbox__details"
      >
        {{ question.details }}
      </p>
      <ul
        v-if="data[question.id]?.length"
        class="flow-inbox__data"
        :data-testid="`flow-question-data-${question.id}`"
      >
        <li
          v-for="(line, index) in data[question.id]"
          :key="index"
        >
          {{ line }}
        </li>
      </ul>
      <span
        class="flow-inbox__muted"
        :data-testid="`flow-question-who-${question.id}`"
      >{{ who(question) }}</span>
      <span
        class="flow-inbox__muted"
        :data-testid="`flow-question-silence-${question.id}`"
      >{{ silence(question) }}</span>
      <span
        class="flow-inbox__muted"
        :data-testid="`flow-question-no-${question.id}`"
      >{{ $t(question.on_no === 'continue' ? 'flow.inbox.noContinues' : 'flow.inbox.noStops') }}</span>
      <IonInput
        :data-testid="`flow-question-note-${question.id}`"
        :value="notes[question.id] ?? ''"
        :label="$t('flow.inbox.note')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="500"
        @ion-input="notes = { ...notes, [question.id]: String($event.detail.value ?? '') }"
      />
      <InlineFeedback
        v-if="problems[question.id]"
        tone="danger"
        :data-testid="`flow-question-problem-${question.id}`"
      >
        {{ problems[question.id] }}
      </InlineFeedback>
      <div class="flow-inbox__actions">
        <IonButton
          size="small"
          :disabled="busy === question.id"
          :data-testid="`flow-question-yes-${question.id}`"
          @click="decide(question, true)"
        >
          {{ $t('flow.inbox.approve') }}
        </IonButton>
        <IonButton
          size="small"
          fill="outline"
          mode="md"
          color="medium"
          :disabled="busy === question.id"
          :data-testid="`flow-question-reject-${question.id}`"
          @click="decide(question, false)"
        >
          {{ $t('flow.inbox.reject') }}
        </IonButton>
      </div>
    </article>
  </section>
</template>

<style scoped>
.flow-inbox {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-section {
  margin: 0.5rem 0 0;
  font-size: 1.05rem;
  font-weight: 600;
}
.flow-inbox__card {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.75rem;
  border: 1px solid var(--ep-border, #d7d5cc);
  border-radius: 10px;
  min-width: 0;
}
.flow-inbox__from {
  font-size: 0.8rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-inbox__title {
  overflow-wrap: anywhere;
}
.flow-inbox__details {
  margin: 0;
  white-space: pre-line;
  overflow-wrap: anywhere;
}
.flow-inbox__data {
  margin: 0;
  padding-left: 1.1rem;
  overflow-wrap: anywhere;
}
.flow-inbox__muted {
  margin: 0;
  font-size: 0.88rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-inbox__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
