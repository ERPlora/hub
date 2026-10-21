<script setup lang="ts">
// The form of «Call another system» (WORKBOOK FLOW-F27; the old module's flows-f16): the method, the
// address — saying which permission the step will ask for, the origin written by hand —, the headers,
// what it sends and how long it waits. Every value is text with data, secrets or the call's no-repeat key
// inserted (`{{…}}`); a datum alone is inserted as text too, since a call only sends text. Below, the
// business's «Secrets» (FLOW-F26). The server's refusals show by field.
import { HubIcon } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { asCallText, callOrigin } from '../lib/document';
import type { CatalogOut, HttpStep, Step } from '../operations';
import SecretsBox from './SecretsBox.vue';
import ValueBox from './ValueBox.vue';

const METHODS: readonly HttpStep['method'][] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
/** The server's limits (apps/flow/schemas.py `HttpStep`). */
const MAX_HEADERS = 20;
const MAX_TIMEOUT = 30;

const props = defineProps<{
  step: HttpStep;
  index: number;
  steps: readonly Step[];
  catalog: CatalogOut | null;
  /** The server's refusals by field (`steps.<index>.<field>`). */
  errors: Readonly<Record<string, string>>;
  /** Opens the editor's picker for this step (data, secrets and the key); the chosen path, or `null`. */
  pick: () => Promise<string | null>;
}>();
const emit = defineEmits<{ 'update:step': [step: Step] }>();

const id = computed(() => props.step.id);
const error = (field: string): string | undefined => props.errors[`steps.${props.index}.${field}`];
const host = computed(() => callOrigin(props.step.url)?.slice('https://'.length) ?? null);
const headers = computed(() => Object.entries(props.step.headers ?? {}));
/** A refusal of the headers, whole or of one of them. */
const headersError = computed(() => {
  const prefix = `steps.${props.index}.headers`;
  return props.errors[prefix] ?? Object.entries(props.errors).find(([key]) => key.startsWith(`${prefix}.`))?.[1];
});
const canAddHeader = computed(() => headers.value.length < MAX_HEADERS && !('' in (props.step.headers ?? {})));

function change(patch: Partial<HttpStep>): void {
  emit('update:step', { ...props.step, ...patch });
}

function setTimeoutSeconds(text: string | null | undefined): void {
  const seconds = Math.round(Number(text));
  if (!Number.isFinite(seconds) || seconds < 1) return;
  change({ timeout: Math.min(MAX_TIMEOUT, seconds) });
}

/** Rebuilt from the rows, in their order; a name already used by another row keeps the other one. */
function setHeaders(rows: readonly (readonly [string, string])[]): void {
  change({ headers: Object.fromEntries(rows) });
}

function renameHeader(index: number, name: string | null | undefined): void {
  const next = (name ?? '').trim();
  if (headers.value.some(([other], i) => i !== index && other === next)) return;
  setHeaders(headers.value.map(([key, value], i) => (i === index ? [next, value] : [key, value])));
}

function setHeaderValue(index: number, value: unknown): void {
  setHeaders(headers.value.map(([key, current], i) => (i === index ? [key, asCallText(value)] : [key, current])));
}

function removeHeader(index: number): void {
  setHeaders(headers.value.filter((_, i) => i !== index));
}

function addHeader(): void {
  if (canAddHeader.value) setHeaders([...headers.value, ['', '']]);
}
</script>

<template>
  <div
    class="flow-http"
    :data-testid="`flow-http-${id}`"
  >
    <IonSelect
      :data-testid="`flow-http-method-${id}`"
      :value="step.method"
      :label="$t('flow.http.method')"
      label-placement="floating"
      fill="outline"
      mode="md"
      interface="popover"
      @ion-change="change({ method: $event.detail.value as HttpStep['method'] })"
    >
      <IonSelectOption
        v-for="method in METHODS"
        :key="method"
        :value="method"
      >
        {{ method }}
      </IonSelectOption>
    </IonSelect>
    <ValueBox
      :testid="`flow-http-url-${id}`"
      :model-value="step.url"
      :label="$t('flow.http.url')"
      :required="true"
      :error-text="error('url')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="change({ url: asCallText($event) })"
    />
    <span
      class="flow-card__hint"
      :data-testid="`flow-http-host-${id}`"
    >{{ host ? $t('flow.http.willAsk', { host }) : $t('flow.http.byHand') }}</span>

    <div class="flow-card__field">
      <span class="flow-card__label">{{ $t('flow.http.headers') }}</span>
      <div
        v-for="([name, value], i) in headers"
        :key="i"
        class="flow-http__header"
      >
        <IonInput
          :data-testid="`flow-http-header-name-${id}-${i}`"
          :value="name"
          :label="$t('flow.http.headerName')"
          label-placement="floating"
          fill="outline"
          mode="md"
          autocapitalize="off"
          :spellcheck="false"
          @ion-input="renameHeader(i, $event.detail.value)"
        />
        <ValueBox
          :testid="`flow-http-header-value-${id}-${i}`"
          :model-value="value"
          :label="$t('flow.http.headerValue')"
          :steps="steps"
          :catalog="catalog"
          :pick="pick"
          @update:model-value="setHeaderValue(i, $event)"
        />
        <button
          type="button"
          class="flow-icon-btn"
          :aria-label="$t('flow.http.removeHeader')"
          :data-testid="`flow-http-unheader-${id}-${i}`"
          @click="removeHeader(i)"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </div>
      <span
        v-if="headersError"
        class="flow-card__error"
        :data-testid="`flow-http-headers-error-${id}`"
      >{{ headersError }}</span>
      <button
        type="button"
        class="flow-http__add"
        :disabled="!canAddHeader"
        :data-testid="`flow-http-addheader-${id}`"
        @click="addHeader"
      >
        <HubIcon name="ion:add-outline" /> {{ $t('flow.http.addHeader') }}
      </button>
    </div>

    <ValueBox
      :testid="`flow-http-body-${id}`"
      :model-value="step.body"
      :label="$t('flow.http.body')"
      :helper="$t('flow.http.bodyHint')"
      :error-text="error('body')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="change({ body: asCallText($event) })"
    />
    <span
      class="flow-card__hint"
      :data-testid="`flow-http-keyhint-${id}`"
    >{{ $t('flow.http.keyHint') }}</span>
    <IonInput
      :data-testid="`flow-http-timeout-${id}`"
      type="number"
      :min="1"
      :max="MAX_TIMEOUT"
      :value="step.timeout"
      :label="$t('flow.http.timeout')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :error-text="error('timeout')"
      :class="{ 'ion-invalid ion-touched': !!error('timeout') }"
      @ion-input="setTimeoutSeconds($event.detail.value)"
    />
    <SecretsBox :testid="`flow-http-secrets-${id}`" />
  </div>
</template>

<style scoped src="./spine.css"></style>
<style scoped>
.flow-http {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-http__header {
  display: grid;
  grid-template-areas: 'name value remove';
  grid-template-columns: minmax(7rem, 1fr) minmax(0, 2fr) auto;
  align-items: flex-start;
  gap: 0.3rem;
}
.flow-http__header > ion-input {
  grid-area: name;
}
.flow-http__header > .flow-value {
  grid-area: value;
}
.flow-http__header > .flow-icon-btn {
  grid-area: remove;
}
@media (max-width: 480px) {
  .flow-http__header {
    grid-template-areas: 'name remove' 'value value';
    grid-template-columns: minmax(0, 1fr) auto;
  }
}
.flow-http__add {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  min-height: 2.6rem;
  padding: 0 0.25rem;
  border: 0;
  background: transparent;
  color: var(--ion-color-primary);
  font: inherit;
  cursor: pointer;
}
.flow-http__add:disabled {
  color: var(--ion-color-medium);
  cursor: default;
}
</style>
