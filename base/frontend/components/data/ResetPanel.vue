<script setup lang="ts">
// Settings › Data › Reset (BASE-G108, BASE-G109; the old hub's ResetPanel): only for who administers the hub.
// «Undo an import»: one row per import that can be undone (live `base.import.list`), confirmed without typing (it can
// be imported again), then what was removed per app; a refusal stays in the dialog with its reason (hub#2720: the old
// screen said nothing). «Reset the business»: the plan per section (`base.hub.reset` with `dry_run`), what never goes,
// and — when the business has its own database — the sections ticked and, after typing its name, asked: the worker
// copies the business's data first and only then empties them (round 2026-10-30 of PLAN-DB, decision 2). The live
// `base.hub.dumps` tells each step — copying, emptying, done with what went (the plan read again), or failed with
// nothing emptied, why, and «Try again» with the same sections — and lists the copies below («Copies», DumpsCard);
// while one runs, no second one is offered. In phase 1 the business shares its database with others: the screen says
// so and offers no red button (the server refuses too).
import { ConfirmDialog, EmptyState, type FormModalError, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useLive, useLiveClient } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonCheckbox, IonSkeletonText } from '@ionic/vue';
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useBaseI18n } from '../../lib/i18n';
import type { BlueprintApp, HubReset, ImportRow, Removal, ResetProgress } from '../../operations';
import DumpsCard from './DumpsCard.vue';
import '../../data.css';

const { t, locale } = useBaseI18n();
const session = useSession();
const route = useRoute();
const router = useRouter();
const admin = session.can('base.administer_hub');
const client = useLiveClient();
const imports = admin ? useLive('base.import.list', {}) : undefined;
const copies = admin ? useLive('base.hub.dumps', {}) : undefined;
const copiesFailed = computed(() => copies?.status.value === 'error' && copies.data.value === undefined);

const undoable = computed(() => (imports?.data.value?.imports ?? []).filter((row) => row.undoable));

const asError = (error: unknown): FormModalError => {
  const failure = error as ApiError;
  return { message: failure.message ?? String(error), code: failure.code, status: failure.status };
};

function when(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function removalLines(apps: Removal[]): { text: string; problems: string[]; failed: boolean }[] {
  return apps.flatMap((app) => [
    { text: t('base.data.reset.removed', { app: app.label, n: app.removed }), problems: [], failed: false },
    ...(app.failed
      ? [{ text: t('base.data.reset.notRemoved', { app: app.label, n: app.failed }), problems: app.problems, failed: true }]
      : []),
  ]);
}

// ── Undo an import (BASE-G108) ──
const undoing = ref<ImportRow | null>(null);
const undoOpen = ref(false);
const undoPending = ref(false);
const undoError = ref<FormModalError | null>(null);
const undone = ref<{ text: string; problems: string[]; failed: boolean }[]>([]);

function askUndo(row: ImportRow): void {
  undoing.value = row;
  undoError.value = null;
  undoOpen.value = true;
}

async function undo(): Promise<void> {
  if (!undoing.value) return;
  undoPending.value = true;
  undoError.value = null;
  try {
    const answer = await client.api.call('base.import.undo', { id: undoing.value.id });
    undone.value = removalLines(answer.apps);
    undoOpen.value = false;
    // What each section has changed.
    void readPlan();
  } catch (error) {
    undoError.value = asError(error);
  } finally {
    undoPending.value = false;
  }
}

// ── Reset the business (BASE-G109) ──
const plan = ref<HubReset | undefined>();
const planFailed = ref(false);
const chosen = ref(new Set<string>());
const resetOpen = ref(false);
const resetPending = ref(false);
const resetError = ref<FormModalError | null>(null);
// The sections just asked, said at once as «copying» until the live copies tell the next step.
const asked = ref<BlueprintApp[] | null>(null);
const progress = computed<ResetProgress | null>(() =>
  asked.value
    ? { state: 'copying', sections: asked.value, requested_by: '', error: '', removed: [], finished_at: null }
    : (copies?.data.value?.reset ?? null),
);
const busy = computed(() => progress.value?.state === 'copying' || progress.value?.state === 'emptying');
const sectionNames = computed(() => (progress.value?.sections ?? []).map((section) => section.label).join(', '));
const reset = computed(() => (progress.value?.state === 'done' ? removalLines(progress.value.removed) : []));
const FAILURES = ['dumps_unavailable', 'dump_failed', 'emptying_failed', 'hub_not_ready'];
const failure = computed(() => {
  const error = progress.value?.state === 'failed' ? progress.value.error : '';
  return t(`base.data.reset.failed.${FAILURES.includes(error) ? error : 'dump_failed'}`);
});

watch(
  () => copies?.data.value,
  (now, before) => {
    if (now !== before) asked.value = null;
    // Done: what each section has now.
    if (now?.reset?.state === 'done' && before !== undefined && before.reset?.state !== 'done') void readPlan();
  },
);

async function readPlan(): Promise<void> {
  planFailed.value = false;
  try {
    plan.value = await client.api.call('base.hub.reset', { dry_run: true });
  } catch {
    planFailed.value = true;
  }
}

onMounted(() => {
  if (admin) void readPlan();
});

function tick(section: string, on: boolean): void {
  const next = new Set(chosen.value);
  if (on) next.add(section);
  else next.delete(section);
  chosen.value = next;
}

const picked = computed(() => (plan.value?.sections ?? []).filter((section) => chosen.value.has(section.id)));
const pickedRows = computed(() => picked.value.reduce((total, section) => total + section.rows, 0));
const consequences = computed(() =>
  picked.value.map((section) => `${section.label} — ${t('base.data.rows', { n: section.rows })}`),
);

async function runReset(): Promise<void> {
  if (!plan.value || !picked.value.length) return;
  resetPending.value = true;
  resetError.value = null;
  const sections = picked.value.map((section) => ({ id: section.id, label: section.label }));
  try {
    await client.api.call('base.hub.reset', {
      apps: sections.map((section) => section.id),
      confirm: plan.value.confirm_with,
    });
    asked.value = sections;
    chosen.value = new Set();
    resetOpen.value = false;
  } catch (error) {
    resetError.value = asError(error);
  } finally {
    resetPending.value = false;
  }
}

/** «Try again» of a reset that failed: the same sections (those that still have rows), confirmed again. */
function retryReset(): void {
  const offered = new Set((plan.value?.sections ?? []).map((section) => section.id));
  chosen.value = new Set((progress.value?.sections ?? []).map((section) => section.id).filter((id) => offered.has(id)));
  resetError.value = null;
  resetOpen.value = true;
}

function exportFirst(): void {
  void router.replace({ path: route.path, query: { ...route.query, data: 'export' }, hash: route.hash });
}
</script>

<template>
  <EmptyState
    v-if="!admin"
    icon="ion:file-tray-outline"
    :message="t('base.data.reset.adminOnly')"
    data-testid="reset-admin-only"
  />

  <div
    v-else
    class="data-stack"
  >
    <section
      v-if="undoable.length || undone.length"
      class="data-card"
      data-testid="undo-card"
    >
      <h3 class="data-title">
        {{ t('base.data.reset.undoTitle') }}
      </h3>
      <p class="data-hint">
        {{ t('base.data.reset.undoHint') }}
      </p>
      <ul class="data-rows">
        <li
          v-for="row in undoable"
          :key="row.id"
          class="data-row"
          data-testid="undo-row"
          :data-id="row.id"
        >
          <div class="data-row-main">
            <span class="data-row-name">{{ row.name }}</span>
            <p class="data-row-detail">
              {{ when(row.created_at) }} · {{ row.created_by }} · {{ t('base.data.rows', { n: row.rows }) }}
            </p>
          </div>
          <ion-button
            size="small"
            fill="outline"
            color="danger"
            :data-testid="`undo-${row.id}`"
            @click="askUndo(row)"
          >
            {{ t('base.data.reset.undo') }}
          </ion-button>
        </li>
      </ul>
      <InlineFeedback
        v-if="undone.length"
        tone="success"
        class="data-result"
        data-testid="undo-result"
        :heading="t('base.data.reset.undone')"
      >
        <ul class="data-result-lines">
          <li
            v-for="line in undone"
            :key="line.text"
          >
            {{ line.text }}
            <ul
              v-if="line.problems.length"
              class="data-problems"
            >
              <li
                v-for="problem in line.problems"
                :key="problem"
              >
                {{ problem }}
              </li>
            </ul>
          </li>
        </ul>
      </InlineFeedback>
    </section>

    <section class="data-card">
      <div class="data-head">
        <div>
          <h3 class="data-title">
            {{ t('base.data.reset.title') }}
          </h3>
          <p class="data-hint">
            {{ t('base.data.reset.intro') }}
          </p>
        </div>
        <ion-button
          fill="outline"
          data-testid="reset-export-first"
          @click="exportFirst"
        >
          {{ t('base.data.reset.exportFirst') }}
        </ion-button>
      </div>
      <p class="data-hint">
        {{ t('base.data.reset.keeps') }}
      </p>
      <p
        v-if="plan?.available"
        class="data-hint"
        data-testid="reset-copy-first"
      >
        {{ t('base.data.reset.copyFirst') }}
      </p>

      <InlineFeedback
        v-if="planFailed"
        tone="warning"
        class="data-result"
        :heading="t('base.data.reset.loadError')"
      >
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="reset-retry"
            @click="readPlan"
          >
            {{ t('base.data.retry.label') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <div
        v-else-if="plan === undefined"
        aria-busy="true"
        :aria-label="t('base.data.reset.loading')"
      >
        <ion-skeleton-text
          v-for="n in 3"
          :key="n"
          animated
          class="reset-skeleton"
        />
      </div>
      <template v-else>
        <InlineFeedback
          v-if="!plan.available"
          tone="info"
          class="data-result"
          data-testid="reset-shared"
        >
          {{ t('base.data.reset.shared') }}
        </InlineFeedback>
        <p
          v-if="!plan.sections.length"
          class="data-hint"
        >
          {{ t('base.data.reset.nothing') }}
        </p>
        <ul
          v-else
          class="data-rows"
        >
          <li
            v-for="section in plan.sections"
            :key="section.id"
            class="data-row"
            data-testid="reset-section"
            :data-id="section.id"
          >
            <ion-checkbox
              v-if="plan.available"
              :data-testid="`reset-section-${section.id}`"
              :checked="chosen.has(section.id)"
              :aria-label="section.label"
              @ion-change="tick(section.id, Boolean($event.detail.checked))"
            />
            <div class="data-row-main">
              <span class="data-row-name">{{ section.label }}</span>
              <p class="data-row-detail">
                {{ section.datasets.filter((part) => part.rows).map((part) => `${part.label} · ${part.rows}`).join(', ') }}
              </p>
            </div>
            <span class="data-row-detail">{{ t('base.data.rows', { n: section.rows }) }}</span>
          </li>
        </ul>
        <InlineFeedback
          v-if="busy && progress"
          tone="info"
          class="data-result"
          role="status"
          data-testid="reset-progress"
          :heading="
            progress.state === 'copying'
              ? t('base.data.reset.progress.copying')
              : t('base.data.reset.progress.emptying', { sections: sectionNames })
          "
        >
          <template v-if="progress.state === 'copying'">
            {{ t('base.data.reset.progress.copyingHint', { sections: sectionNames }) }}
          </template>
        </InlineFeedback>
        <InlineFeedback
          v-else-if="progress?.state === 'failed'"
          tone="danger"
          class="data-result"
          data-testid="reset-failed"
          :heading="t('base.data.reset.failed.heading')"
        >
          {{ failure }}
          <template #actions>
            <ion-button
              size="small"
              fill="outline"
              data-testid="reset-failed-retry"
              @click="retryReset"
            >
              {{ t('base.data.reset.failed.retry') }}
            </ion-button>
          </template>
        </InlineFeedback>
        <InlineFeedback
          v-if="reset.length"
          tone="success"
          class="data-result"
          data-testid="reset-result"
          :heading="t('base.data.reset.done')"
        >
          <ul class="data-result-lines">
            <li
              v-for="line in reset"
              :key="line.text"
            >
              {{ line.text }}
              <ul
                v-if="line.problems.length"
                class="data-problems"
              >
                <li
                  v-for="problem in line.problems"
                  :key="problem"
                >
                  {{ problem }}
                </li>
              </ul>
            </li>
          </ul>
          <p class="data-hint">
            {{ t('base.data.reset.keptCopy') }}
          </p>
        </InlineFeedback>
        <div
          v-if="plan.available && plan.sections.length"
          class="data-actions"
        >
          <span
            v-if="busy"
            class="data-hint"
          >{{ t('base.data.reset.busy') }}</span>
          <ion-button
            color="danger"
            data-testid="reset-submit"
            :disabled="!picked.length || busy"
            @click="resetError = null; resetOpen = true"
          >
            {{ t('base.data.reset.submit') }}
          </ion-button>
        </div>
      </template>
    </section>

    <DumpsCard
      :dumps="copies?.data.value"
      :failed="copiesFailed"
      @retry="copies?.refresh()"
    />

    <ConfirmDialog
      v-model:open="undoOpen"
      testid="undo-confirm"
      :title="t('base.data.reset.undoConfirmTitle', { name: undoing?.name ?? '' })"
      :message="t('base.data.reset.undoConfirmMessage', { n: undoing?.rows ?? 0 })"
      :confirm-label="t('base.data.reset.undo')"
      :pending="undoPending"
      :error="undoError"
      @confirm="undo"
    />
    <ConfirmDialog
      v-model:open="resetOpen"
      testid="reset-confirm"
      :title="t('base.data.reset.confirmTitle')"
      :message="t('base.data.reset.confirmMessage', { n: pickedRows })"
      :consequences="consequences"
      :require-text="plan?.confirm_with"
      :require-text-label="t('base.data.reset.typeName', { name: plan?.confirm_with ?? '' })"
      :confirm-label="t('base.data.reset.confirmLabel')"
      :pending="resetPending"
      :error="resetError"
      @confirm="runReset"
    />
  </div>
</template>

<style scoped>
.data-result {
  margin-top: 12px;
}

.data-result-lines {
  margin: 4px 0 0;
  padding-left: 18px;
}

.reset-skeleton {
  height: 20px;
  margin: 12px 0;
}
</style>
