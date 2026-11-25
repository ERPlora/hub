<script setup lang="ts">
// The steps the apps on add to the charge (SALE-F39; today the «Tip» row of Tips), between the amount and the tenders.
// Sales follows `sale.checkout.steps` live — an app turned on brings its step, one turned off takes it away — and mounts
// each step's component of its app by its name (`lib/app-components.ts`), knowing it only by the contract of
// lib/checkout/steps.ts. What they add is added up for the charge (`update:added`). Once the sale is charged,
// `afterCharge` has each step record its part; when one cannot, its own words stay here with «Retry», which asks only
// that one again, and «Close», which leaves it so (the sale is charged: the app records it later). `done` comes when
// they are all recorded or closed. A step whose app lacks its component, or whose code does not arrive, is left out and
// logged, and the others stay; while the list loads there is none.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { type Component, computed, type ComponentPublicInstance, reactive, shallowRef, watch } from 'vue';

import { appComponent, loadedComponent } from '../../../../../base/frontend/lib/app-components';
import { type Added, allAdded, NOTHING_ADDED, type StepHandle, type StepProps } from '../../lib/checkout/steps';
import type { SaleOut } from '../../operations';
import type { CheckoutStepOut } from '../../operations/checkout-steps';

const props = defineProps<StepProps>();
const emit = defineEmits<{ 'update:added': [added: Added]; done: [] }>();

const read = useLive('sale.checkout.steps', {});

/** Each step's component, made once; `null`: its app has no such component. */
const made = new Map<string, Component | null>();
const unloaded = reactive(new Set<string>());

function componentOf(step: CheckoutStepOut): Component | null {
  if (!made.has(step.key)) {
    const component = loadedComponent(appComponent(step.app, step.component), (error) => {
      console.warn(`sale: the step ${step.key} of the charge could not load its component`, error);
      unloaded.add(step.key);
    });
    if (!component) console.warn(`sale: the step ${step.key} of the charge names ${step.component}, which its app does not have`);
    made.set(step.key, component);
  }
  return made.get(step.key) ?? null;
}

const steps = computed(() =>
  (read.data.value?.steps ?? []).flatMap((step) => {
    const component = componentOf(step);
    return component && !unloaded.has(step.key) ? [{ key: step.key, component }] : [];
  }),
);

const added = reactive(new Map<string, Added>());
watch(
  () => allAdded(steps.value.map((step) => added.get(step.key) ?? NOTHING_ADDED)),
  (now) => emit('update:added', now),
  { immediate: true },
);

const handles = new Map<string, StepHandle>();
function keep(key: string, instance: Element | ComponentPublicInstance | null): void {
  if (instance && 'afterCharge' in instance) handles.set(key, instance as unknown as StepHandle);
  else handles.delete(key);
}

// ── Once the sale is charged ───────────────────────────────────────────────────────────────────
let charged: { sale: SaleOut; attemptKey: string } | null = null;
const failures = shallowRef<{ key: string; message: string }[]>([]);
const recording = shallowRef(false);

/** The steps of `keys` record their part of the charged sale; what each could not, in its words. */
async function record(keys: readonly string[]): Promise<void> {
  if (!charged) return;
  const { sale, attemptKey } = charged;
  recording.value = true;
  const outcomes = await Promise.all(
    keys.map(async (key) => {
      try {
        await handles.get(key)?.afterCharge(sale, attemptKey);
        return null;
      } catch (error) {
        return { key, message: error instanceof Error ? error.message : String(error) };
      }
    }),
  );
  recording.value = false;
  failures.value = outcomes.filter((outcome) => outcome !== null);
  if (!failures.value.length) emit('done');
}

function afterCharge(sale: SaleOut, attemptKey: string): void {
  charged = { sale, attemptKey };
  void record(steps.value.map((step) => step.key));
}

function retry(): void {
  void record(failures.value.map((failure) => failure.key));
}

defineExpose({ afterCharge });
</script>

<template>
  <div
    v-if="steps.length || failures.length || (read.error.value && !read.data.value)"
    data-testid="sale-checkout-steps"
  >
    <InlineFeedback
      v-if="read.error.value && !read.data.value"
      tone="danger"
      data-testid="sale-checkout-steps-error"
    >
      {{ read.error.value.message }}
      <template #actions>
        <ion-button
          fill="clear"
          size="small"
          data-testid="sale-checkout-steps-reload"
          @click="read.refresh()"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <component
      :is="step.component"
      v-for="step in steps"
      :key="step.key"
      :ref="(instance: Element | ComponentPublicInstance | null) => keep(step.key, instance)"
      :total="props.total"
      :discount="props.discount"
      :method="props.method"
      :locked="props.locked"
      @update:added="(now: Added) => added.set(step.key, now)"
    />
    <InlineFeedback
      v-if="failures.length"
      tone="danger"
      role="alert"
      data-testid="sale-checkout-steps-failed"
    >
      {{ failures.map((failure) => failure.message).join(' ') }}
      <template #actions>
        <ion-button
          fill="clear"
          size="small"
          data-testid="sale-checkout-steps-retry"
          :disabled="recording"
          @click="retry"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
        <ion-button
          fill="clear"
          size="small"
          color="medium"
          data-testid="sale-checkout-steps-close"
          :disabled="recording"
          @click="emit('done')"
        >
          {{ $t('sale.checkout.close') }}
        </ion-button>
      </template>
    </InlineFeedback>
  </div>
</template>
