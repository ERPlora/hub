<script setup lang="ts">
// The editor of an automation (WORKBOOK «Editor de automatización»; FLOW-F09 to F16, F18; the old
// module's `erp-flows-editor`). Its head: the name, Active/Paused (or Unfinished: on without the
// permissions it asks for), the switch, «Try it», «Run now» (saved and on) and «Save», which sends the
// whole document (`flow.flow.create`, with the draft it comes from, or `flow.flow.update`). Four tabs:
// Steps — the trigger card, the column of steps (ordered with the finger, `ion-reorder-group`) and the
// four buttons to add —, Try it, Permissions and History. The server's refusals show next to their
// step, which opens. «Insert data» opens the one picker with what the last real event brought and
// what the earlier steps leave. The page holds the route: this component says when it is dirty.
import { InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonInput, IonLabel, IonReorderGroup, IonSegment, IonSegmentButton, IonToggle } from '@ionic/vue';
import { computed, effectScope, type EffectScope, onScopeDispose, ref, shallowRef, watch } from 'vue';

import { useCatalog } from '../composables/useCatalog';
import { usePhrasing } from '../composables/usePhrasing';
import { wording } from '../lib/refusal';
import {
  addMessageStep,
  addStep,
  callChoices,
  type DataChoice,
  dataChoices,
  fieldErrors,
  type FlowDocument,
  fromFlow,
  missingGrants,
  moveStep,
  NOTIFY_OPERATION,
  patchStep,
  removeStep,
  requiredGrants,
  toPayload,
} from '../lib/document';
import { statePill } from '../lib/phrasing';
import type { DraftOut, FlowOut, Step, StepKind, Trigger } from '../operations';
import FieldPicker from './FieldPicker.vue';
import HistoryPanel from './HistoryPanel.vue';
import PermissionsPanel from './PermissionsPanel.vue';
import StepNode from './StepNode.vue';
import TestPanel from './TestPanel.vue';
import TriggerCard from './TriggerCard.vue';

type Tab = 'steps' | 'test' | 'permissions' | 'history';

const props = defineProps<{
  /** The saved automation (live), or `null` for one that does not exist yet. */
  flow: FlowOut | null;
  /** What the editor starts from: the saved one, a blank one or the assistant's draft. */
  initial: FlowDocument;
  draft: DraftOut | null;
  tab: string;
  /** Opened right after it was created: it starts saying «Saved.». */
  savedNow?: boolean;
}>();
const emit = defineEmits<{ saved: [flow: FlowOut]; back: []; dirty: [dirty: boolean] }>();

const client = useLiveClient();
const phrasing = usePhrasing();
const { confirm } = useConfirm();
const { catalog, error: catalogError, reload: reloadCatalog } = useCatalog();
const create = useCommand('flow.flow.create');
const update = useCommand('flow.flow.update');
const runNow = useCommand('flow.flow.run');
const switching = useCommand('flow.flow.set_enabled');

const TABS: readonly Tab[] = ['steps', 'test', 'permissions', 'history'];
/** What «Run now» says of a run that did not end at once. */
const RAN_NOTICE: Partial<Record<string, string>> = {
  waiting: 'flow.editor.ranWaiting',
  calling: 'flow.editor.ranCalling',
  asking: 'flow.editor.ranAsking',
};
type Adder = StepKind | 'message';
const ADDERS: readonly Adder[] = ['command', 'query', 'condition', 'delay', 'message', 'http', 'ask'];
/** «Send a message» only where the WhatsApp inbox is (its narrow send is in the catalog, FLOW-F31). */
const adders = computed(() => ADDERS.filter((kind) => kind !== 'message' || !!catalog.value?.actions.some((action) => action.name === NOTIFY_OPERATION)));

/** What is compared to know whether something is unsaved: the document and its switch. */
const snapshot = (value: FlowDocument): string => JSON.stringify({ ...toPayload(value), enabled: value.enabled });
const doc = ref<FlowDocument>(JSON.parse(JSON.stringify(props.initial)) as FlowDocument);
const saved = ref(snapshot(props.initial));
const dirty = computed(() => snapshot(doc.value) !== saved.value);
watch(dirty, (now) => emit('dirty', now));

// The live automation changes elsewhere (another tab, the switch of the list): taken when nothing here is unsaved.
watch(
  () => props.flow,
  (now) => {
    if (!now || dirty.value) return;
    doc.value = fromFlow(now);
    saved.value = snapshot(doc.value);
  },
);

const tab = ref<Tab>((TABS as readonly string[]).includes(props.tab) ? (props.tab as Tab) : 'steps');
const tested = ref(tab.value === 'test');
watch(tab, (now) => {
  if (now === 'test') tested.value = true;
});
const openStep = ref<string | null>(null);
const errors = ref<Record<string, string>>({});
/** The refusal or failure said above the tab. */
const problem = ref('');
const notice = ref(props.savedNow ? phrasing.value.t('flow.editor.saved') : '');

// ── The last real event, for the picker and «Only when…» ──
const sample = shallowRef<Record<string, unknown> | null>(null);
watch(
  () => (doc.value.trigger.kind === 'event' ? doc.value.trigger.event : ''),
  async (event) => {
    sample.value = null;
    if (!event) return;
    try {
      const answer = await client.api.call('flow.event.sample', { event });
      if ((doc.value.trigger.kind === 'event' ? doc.value.trigger.event : '') === event) sample.value = answer.found ? answer.payload : null;
    } catch {
      // Without an example the picker still offers the earlier steps' data; nothing to say here.
    }
  },
  { immediate: true },
);

const triggerChoices = computed(() => dataChoices([], 0, sample.value, catalog.value));
const choicesFor = (index: number): DataChoice[] => dataChoices(doc.value.steps, index, sample.value, catalog.value);

// ── The secrets a call can insert (FLOW-F27): followed only while the column has a call ──
const secretNames = shallowRef<string[]>([]);
let secretsScope: EffectScope | null = null;
watch(
  () => doc.value.steps.some((step) => step.kind === 'http'),
  (hasCall) => {
    if (hasCall && !secretsScope) {
      secretsScope = effectScope();
      secretsScope.run(() => {
        const secrets = useLive('flow.secret.list', {}, { client });
        watch(() => secrets.data.value?.rows, (rows) => (secretNames.value = (rows ?? []).map((row) => row.name)), { immediate: true });
      });
    } else if (!hasCall && secretsScope) {
      secretsScope.stop();
      secretsScope = null;
      secretNames.value = [];
    }
  },
  { immediate: true },
);
onScopeDispose(() => secretsScope?.stop());

// ── The picker: one for the whole editor ──
const pickerOpen = ref(false);
const pickerChoices = ref<DataChoice[]>([]);
let answerPick: ((path: string | null) => void) | null = null;

/** The picker of step `index`; a call's values (`call`) may insert the secrets and the call's key too. */
function pickFor(index: number, call = false): () => Promise<string | null> {
  return () =>
    new Promise((resolve) => {
      answerPick?.(null);
      answerPick = resolve;
      pickerChoices.value = call ? [...choicesFor(index), ...callChoices(secretNames.value)] : choicesFor(index);
      pickerOpen.value = true;
    });
}

function onPick(path: string): void {
  answerPick?.(path);
  answerPick = null;
}

function onPickerOpen(open: boolean): void {
  pickerOpen.value = open;
  if (!open) {
    answerPick?.(null);
    answerPick = null;
  }
}

// ── Editing ──
function setTrigger(trigger: Trigger): void {
  doc.value = { ...doc.value, trigger };
}

function add(kind: Adder): void {
  doc.value = kind === 'message' ? addMessageStep(doc.value) : addStep(doc.value, kind);
  openStep.value = doc.value.steps.at(-1)?.id ?? null;
}

function updateStep(index: number, step: Step): void {
  doc.value = patchStep(doc.value, index, step);
}

function remove(index: number): void {
  doc.value = removeStep(doc.value, index);
}

function toggleStep(id: string): void {
  openStep.value = openStep.value === id ? null : id;
}

function onReorder(event: CustomEvent<{ from: number; to: number; complete: (data?: boolean) => void }>): void {
  doc.value = moveStep(doc.value, event.detail.from, event.detail.to);
  // The list is drawn from the document: Ionic puts its items back and Vue moves them.
  event.detail.complete(false);
}

const missing = computed(() => (props.flow ? missingGrants(doc.value.steps, props.flow.grants) : requiredGrants(doc.value.steps)));
const pill = computed(() => statePill({ enabled: doc.value.enabled, missing_grants: missing.value }, phrasing.value));

const warnings = computed(() => {
  if (!doc.value.enabled) return [];
  const out: string[] = [];
  if (missing.value.length) out.push(phrasing.value.t('flow.list.enabledMissing'));
  if (!tested.value) out.push(phrasing.value.t('flow.editor.notTested'));
  return out;
});

/** The step of a refusal opens, so the person sees what to fix. */
function openFirstError(fields: Record<string, string>): void {
  const first = Object.keys(fields)[0] ?? '';
  const match = /^steps\.(\d+)\./.exec(first);
  if (match) openStep.value = doc.value.steps[Number(match[1])]?.id ?? null;
  else if (first.startsWith('trigger')) openStep.value = 'trigger';
  tab.value = 'steps';
}

async function save(): Promise<void> {
  problem.value = '';
  errors.value = {};
  notice.value = '';
  const payload = toPayload(doc.value);
  const enabled = doc.value.enabled;
  try {
    let flow = props.flow
      ? await update.run({ id: props.flow.id, ...payload })
      : await create.run({ ...payload, ...(props.draft ? { draft_id: props.draft.id } : {}) });
    // The switch goes on its own: turning on is `flow.flow.set_enabled`'s, which the assistant confirms.
    if (flow.enabled !== enabled) flow = await switching.run({ id: flow.id, enabled });
    saved.value = snapshot({ ...doc.value, enabled: flow.enabled });
    notice.value = phrasing.value.t('flow.editor.saved');
    emit('saved', flow);
  } catch (failure) {
    const refused = failure as ApiError;
    problem.value = wording(refused, phrasing.value.t('flow.errors.action'));
    errors.value = fieldErrors(refused.fields);
    openFirstError(errors.value);
  }
}

async function run(): Promise<void> {
  if (!props.flow || dirty.value) return;
  const t = phrasing.value.t;
  const yes = await confirm({
    title: t('flow.editor.runTitle'),
    message: t('flow.editor.runMessage'),
    tone: 'warning',
    confirmLabel: t('flow.editor.runYes'),
    cancelLabel: t('flow.editor.runNo'),
  });
  if (!yes) return;
  problem.value = '';
  try {
    const ran = await runNow.run({ id: props.flow.id });
    if (ran.status === 'failed') problem.value = t('flow.editor.ranFailed', { message: ran.error_message });
    else void toastSuccess(t(RAN_NOTICE[ran.status] ?? 'flow.editor.ran'));
  } catch (failure) {
    problem.value = wording(failure, phrasing.value.t('flow.errors.action'));
  }
}

const saving = computed(() => create.pending.value || update.pending.value || switching.pending.value);
</script>

<template>
  <div class="flow-editor">
    <div class="flow-editor__head">
      <button
        type="button"
        class="flow-editor__icon"
        :aria-label="$t('flow.editor.back')"
        data-testid="flow-editor-back"
        @click="emit('back')"
      >
        <HubIcon name="ion:arrow-back-outline" />
      </button>
      <IonInput
        class="flow-editor__name"
        data-testid="flow-editor-name"
        :value="doc.name"
        :placeholder="$t('flow.unnamed')"
        :aria-label="$t('flow.editor.name')"
        :maxlength="120"
        @ion-input="doc = { ...doc, name: String($event.detail.value ?? '') }"
      />
      <span data-testid="flow-editor-state"><StatusPill v-bind="pill" /></span>
      <IonToggle
        data-testid="flow-editor-enabled"
        :checked="doc.enabled"
        :aria-label="$t('flow.editor.enable')"
        @ion-change="doc = { ...doc, enabled: $event.detail.checked }"
      />
      <IonButton
        size="small"
        fill="outline"
        mode="md"
        data-testid="flow-editor-test"
        @click="tab = 'test'"
      >
        {{ $t('flow.editor.test') }}
      </IonButton>
      <IonButton
        v-if="flow && flow.enabled"
        size="small"
        fill="outline"
        mode="md"
        :disabled="runNow.pending.value || dirty"
        data-testid="flow-editor-run"
        @click="run"
      >
        {{ $t('flow.editor.run') }}
      </IonButton>
      <IonButton
        size="small"
        mode="md"
        :disabled="saving"
        data-testid="flow-editor-save"
        @click="save"
      >
        {{ saving ? $t('flow.editor.saving') : $t('flow.editor.save') }}
      </IonButton>
    </div>

    <IonSegment
      class="flow-editor__tabs"
      data-testid="flow-editor-tabs"
      :value="tab"
      :aria-label="$t('flow.editor.tabs.label')"
      scrollable
      @ion-change="tab = $event.detail.value as Tab"
    >
      <IonSegmentButton
        v-for="name in TABS"
        :key="name"
        :value="name"
        :data-testid="`flow-editor-tab-${name}`"
      >
        <IonLabel>{{ $t(`flow.editor.tabs.${name}`) }}</IonLabel>
      </IonSegmentButton>
    </IonSegment>

    <div class="flow-editor__body">
      <InlineFeedback
        v-if="catalogError"
        tone="danger"
        data-testid="flow-catalog-error"
      >
        {{ $t('flow.catalogError') }} {{ wording(catalogError, '') }}
        <IonButton
          size="small"
          fill="clear"
          data-testid="flow-catalog-retry"
          @click="reloadCatalog()"
        >
          {{ $t('flow.live.retry') }}
        </IonButton>
      </InlineFeedback>
      <InlineFeedback
        v-if="problem"
        tone="danger"
        data-testid="flow-editor-error"
      >
        {{ problem }}
      </InlineFeedback>
      <p
        v-if="flow && flow.enabled && dirty"
        class="flow-editor__hint"
        data-testid="flow-editor-run-hint"
      >
        {{ $t('flow.editor.runSaveFirst') }}
      </p>
      <InlineFeedback
        v-if="notice && !dirty"
        tone="success"
        data-testid="flow-editor-notice"
      >
        {{ notice }}
      </InlineFeedback>
      <InlineFeedback
        v-if="warnings.length"
        tone="warning"
        data-testid="flow-editor-warning"
      >
        <span
          v-for="(line, index) in warnings"
          :key="index"
          class="flow-editor__line"
        >{{ line }}</span>
      </InlineFeedback>
      <div
        v-if="draft"
        class="flow-editor__draft"
        data-testid="flow-editor-draft"
      >
        <InlineFeedback tone="warning">
          {{ $t('flow.editor.draftBanner') }}
        </InlineFeedback>
        <template v-if="draft.notes.length">
          <span class="flow-editor__eyebrow">{{ $t('flow.editor.draftNotes') }}</span>
          <ul>
            <li
              v-for="(note, index) in draft.notes"
              :key="index"
            >
              {{ note }}
            </li>
          </ul>
        </template>
      </div>

      <div
        v-if="tab === 'steps'"
        class="flow-editor__spine"
      >
        <TriggerCard
          :model-value="doc.trigger"
          :open="openStep === 'trigger'"
          :catalog="catalog"
          :choices="triggerChoices"
          :steps="doc.steps"
          :errors="errors"
          :pick="pickFor(0)"
          @update:model-value="setTrigger"
          @toggle="toggleStep('trigger')"
        />
        <IonReorderGroup
          :disabled="false"
          data-testid="flow-editor-steps"
          @ion-item-reorder="onReorder"
        >
          <StepNode
            v-for="(step, index) in doc.steps"
            :key="step.id"
            :step="step"
            :index="index"
            :steps="doc.steps"
            :catalog="catalog"
            :open="openStep === step.id"
            :errors="errors"
            :choices="choicesFor(index)"
            :pick="pickFor(index)"
            :pick-call="step.kind === 'http' ? pickFor(index, true) : undefined"
            @update:step="updateStep(index, $event)"
            @remove="remove(index)"
            @toggle="toggleStep(step.id)"
          />
        </IonReorderGroup>
        <p
          v-if="!doc.steps.length"
          class="flow-editor__none"
          data-testid="flow-editor-nosteps"
        >
          {{ $t('flow.steps.none') }}
        </p>
        <span
          v-if="errors.steps"
          class="flow-editor__bad"
        >{{ errors.steps }}</span>
        <div class="flow-editor__adders">
          <button
            v-for="kind in adders"
            :key="kind"
            type="button"
            :data-testid="`flow-editor-add-${kind}`"
            @click="add(kind)"
          >
            {{ $t(`flow.steps.add.${kind}`) }}
          </button>
        </div>
      </div>
      <TestPanel
        v-else-if="tab === 'test'"
        :document="doc"
        :flow-id="flow?.id ?? null"
        :catalog="catalog"
      />
      <PermissionsPanel
        v-else-if="tab === 'permissions'"
        :flow="flow"
        :dirty="dirty"
        :catalog="catalog"
      />
      <template v-else>
        <HistoryPanel
          v-if="flow"
          :flow-id="flow.id"
          :steps="doc.steps"
          :catalog="catalog"
        />
        <p
          v-else
          class="flow-editor__none"
        >
          {{ $t('flow.history.empty') }}
        </p>
      </template>
    </div>

    <FieldPicker
      :open="pickerOpen"
      :choices="pickerChoices"
      :steps="doc.steps"
      :catalog="catalog"
      @pick="onPick"
      @update:open="onPickerOpen"
    />
  </div>
</template>

<style scoped>
.flow-editor {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-editor__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--ep-border-soft, rgba(0, 0, 0, 0.08));
}
.flow-editor__name {
  flex: 1 1 12rem;
  min-width: 8rem;
  font-size: 1.05rem;
  font-weight: 600;
}
.flow-editor__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.6rem;
  min-height: 2.6rem;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.flow-editor__tabs {
  max-width: 44rem;
}
.flow-editor__body {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.flow-editor__hint {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-editor__line {
  display: block;
}
.flow-editor__draft ul {
  margin: 0.25rem 0 0;
}
.flow-editor__eyebrow {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-editor__spine {
  width: 100%;
  max-width: 44rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
}
.flow-editor__none {
  margin: 0.4rem 0 0 1.6rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-editor__bad {
  margin-left: 1.6rem;
  font-size: 0.85rem;
  color: var(--ion-color-danger);
}
.flow-editor__adders {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.6rem 0 0 1.6rem;
}
.flow-editor__adders button {
  min-height: 2.5rem;
  padding: 0 0.9rem;
  border: 1px solid var(--ep-border, #d7d5cc);
  border-radius: 999px;
  background: var(--ep-surface, #fff);
  color: inherit;
  font: inherit;
  font-size: 0.85rem;
  cursor: pointer;
}
</style>
