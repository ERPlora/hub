<script setup lang="ts">
// Settings › Data › Export (BASE-G101, BASE-G102; the old hub's ExportPanel): only for who administers the hub. The
// file's name (the business's, or the hub's address without one: the old hub's «hub» was a defect) and language, with the final file name under
// them; «Backup of this business» (its customers too) or «Template to share» (never personal data); the apps on, each
// with «App» (the file registers it) and «Data» (its data travels) and, under a marked «Data», one box per table with
// its rows. While no table is unmarked, «all» is sent, so a new table never stays out unseen. «Export» asks the server
// for the file (`base.blueprint.export`) and saves it.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useLiveClient } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import {
  IonButton,
  IonCheckbox,
  IonInput,
  IonRadio,
  IonRadioGroup,
  IonSelect,
  IonSelectOption,
  IonSkeletonText,
} from '@ionic/vue';
import { computed, onMounted, ref } from 'vue';

import {
  base64ToBlob,
  defaultExportName,
  type ExportChoice,
  exportFileName,
  exportInput,
  freshExportChoice,
  saveFile,
  selectAll,
  toggleApp,
  toggleData,
  toggleDataset,
  travels,
} from '../../lib/data';
import { type HubHome, readJsonBlock } from '../../lib/home';
import { useBaseI18n } from '../../lib/i18n';
import type { AppDatasets, BlueprintPurpose } from '../../operations';
import '../../data.css';

/** The languages a file can be written in: the ones the Hub speaks. */
const LANGUAGES = ['en', 'es'] as const;

const { t, locale } = useBaseI18n();
const session = useSession();
const admin = session.can('base.administer_hub');
const client = useLiveClient();

const apps = ref<AppDatasets[] | undefined>();
const loadFailed = ref(false);
const choice = ref<ExportChoice>({ apps: new Set(), data: new Set(), excluded: new Set() });
const name = ref(defaultExportName(readJsonBlock<HubHome>('hub-home')?.name, window.location.hostname));
const language = ref<string>(LANGUAGES.find((code) => locale.value.startsWith(code)) ?? 'en');
const purpose = ref<BlueprintPurpose>('backup');
const pending = ref(false);
const done = ref('');
const failure = ref('');

const fileName = computed(() => exportFileName(name.value, language.value));
const input = computed(() =>
  exportInput(choice.value, apps.value ?? [], { name: name.value.trim(), language: language.value, purpose: purpose.value }),
);
const canExport = computed(() => !pending.value && name.value.trim() !== '' && input.value.apps.length > 0);
const withData = computed(() => (apps.value ?? []).filter((app) => choice.value.apps.has(app.id) && choice.value.data.has(app.id)));

async function readApps(): Promise<void> {
  loadFailed.value = false;
  try {
    const answer = await client.api.call('base.dataset.list', {});
    apps.value = answer.apps;
    choice.value = freshExportChoice(answer.apps);
  } catch {
    loadFailed.value = true;
  }
}

onMounted(() => {
  if (admin) void readApps();
});

async function run(): Promise<void> {
  if (!canExport.value) return;
  pending.value = true;
  done.value = '';
  failure.value = '';
  try {
    const file = await client.api.call('base.blueprint.export', input.value);
    saveFile(file.filename, base64ToBlob(file.content_base64, file.content_type));
    done.value = t('base.data.export.done', { file: file.filename });
  } catch (error) {
    failure.value = t('base.data.export.error', { reason: (error as ApiError).message ?? String(error) });
  } finally {
    pending.value = false;
  }
}

const checked = (event: CustomEvent) => Boolean((event.detail as { checked?: boolean }).checked);
</script>

<template>
  <EmptyState
    v-if="!admin"
    icon="ion:file-tray-outline"
    :message="t('base.data.export.adminOnly')"
    data-testid="export-admin-only"
  />

  <div
    v-else
    class="data-stack"
  >
    <p class="data-hint">
      {{ t('base.data.export.intro') }}
    </p>

    <section class="data-card export-file">
      <ion-input
        data-testid="export-name"
        :value="name"
        :label="t('base.data.export.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="120"
        :error-text="t('base.data.export.nameRequired')"
        :class="{ 'ion-invalid ion-touched': name.trim() === '' }"
        @ion-input="name = String($event.detail.value ?? '')"
      />
      <ion-select
        data-testid="export-language"
        :value="language"
        :label="t('base.data.export.language')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="language = String($event.detail.value)"
      >
        <ion-select-option
          v-for="code in LANGUAGES"
          :key="code"
          :value="code"
        >
          {{ code === 'es' ? t('base.data.export.languages.es') : t('base.data.export.languages.en') }}
        </ion-select-option>
      </ion-select>
      <p
        class="data-hint"
        data-testid="export-file-name"
      >
        {{ t('base.data.export.fileName', { file: fileName }) }}
      </p>
      <p
        v-if="name.trim() === ''"
        class="data-hint export-warning"
      >
        {{ t('base.data.export.nameRequired') }}
      </p>
    </section>

    <section class="data-card">
      <h3 class="data-title">
        {{ t('base.data.export.purpose') }}
      </h3>
      <ion-radio-group
        data-testid="export-purpose"
        :value="purpose"
        @ion-change="purpose = $event.detail.value === 'template' ? 'template' : 'backup'"
      >
        <div class="export-purpose">
          <ion-radio
            value="backup"
            label-placement="end"
            justify="start"
          >
            <span class="data-row-name">{{ t('base.data.export.backup') }}</span>
          </ion-radio>
          <p class="data-row-detail">
            {{ t('base.data.export.backupHint') }}
          </p>
        </div>
        <div class="export-purpose">
          <ion-radio
            value="template"
            label-placement="end"
            justify="start"
          >
            <span class="data-row-name">{{ t('base.data.export.template') }}</span>
          </ion-radio>
          <p class="data-row-detail">
            {{ t('base.data.export.templateHint') }}
          </p>
        </div>
      </ion-radio-group>
    </section>

    <section class="data-card">
      <div class="data-head">
        <div>
          <h3 class="data-title">
            {{ t('base.data.export.appsTitle') }}
          </h3>
          <p class="data-hint">
            {{ t('base.data.export.appsHint') }}
          </p>
        </div>
        <div
          v-if="apps?.length"
          class="export-bulk"
        >
          <ion-button
            size="small"
            fill="clear"
            data-testid="export-select-all"
            @click="choice = selectAll(apps, true)"
          >
            {{ t('base.data.export.selectAll') }}
          </ion-button>
          <ion-button
            size="small"
            fill="clear"
            data-testid="export-deselect-all"
            @click="choice = selectAll(apps, false)"
          >
            {{ t('base.data.export.deselectAll') }}
          </ion-button>
        </div>
      </div>

      <InlineFeedback
        v-if="loadFailed"
        tone="warning"
        class="export-feedback"
        :heading="t('base.data.export.loadError')"
      >
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="export-retry"
            @click="readApps"
          >
            {{ t('base.data.retry.label') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <div
        v-else-if="apps === undefined"
        aria-busy="true"
        :aria-label="t('base.data.export.loading')"
      >
        <ion-skeleton-text
          v-for="n in 3"
          :key="n"
          animated
          class="export-skeleton"
        />
      </div>
      <p
        v-else-if="!apps.length"
        class="data-hint"
      >
        {{ t('base.data.export.noApps') }}
      </p>
      <ul
        v-else
        class="data-rows"
      >
        <li class="data-row export-columns">
          <span class="data-row-main">{{ t('base.data.export.colApp') }}</span>
          <span class="export-col">{{ t('base.data.export.colApp') }}</span>
          <span class="export-col">{{ t('base.data.export.colData') }}</span>
        </li>
        <li
          v-for="app in apps"
          :key="app.id"
          class="data-row"
          data-testid="export-app"
          :data-id="app.id"
        >
          <div class="data-row-main">
            <span class="data-row-name">{{ app.label }}</span>
            <p
              v-if="!app.datasets.length"
              class="data-row-detail"
            >
              {{ t('base.data.export.nothingToCopy') }}
            </p>
          </div>
          <ion-checkbox
            class="export-col"
            :data-testid="`export-app-${app.id}`"
            :checked="choice.apps.has(app.id)"
            :aria-label="`${t('base.data.export.colApp')} · ${app.label}`"
            @ion-change="choice = toggleApp(choice, app.id, checked($event))"
          />
          <ion-checkbox
            class="export-col"
            :data-testid="`export-data-${app.id}`"
            :checked="choice.data.has(app.id)"
            :disabled="!choice.apps.has(app.id) || !app.datasets.length"
            :aria-label="`${t('base.data.export.colData')} · ${app.label}`"
            @ion-change="choice = toggleData(choice, app.id, checked($event))"
          />
        </li>
      </ul>
    </section>

    <section
      v-for="app in withData"
      :key="app.id"
      class="data-card"
      :data-testid="`export-tables-${app.id}`"
    >
      <h3 class="data-title">
        {{ t('base.data.export.tablesOf', { app: app.label }) }}
      </h3>
      <ul class="data-rows">
        <li
          v-for="dataset in app.datasets"
          :key="dataset.key"
          class="data-row"
        >
          <ion-checkbox
            :data-testid="`export-table-${dataset.key}`"
            :checked="travels(dataset, purpose) && !choice.excluded.has(dataset.key)"
            :disabled="!travels(dataset, purpose)"
            label-placement="end"
            justify="start"
            @ion-change="choice = toggleDataset(choice, dataset.key, checked($event))"
          >
            {{ dataset.label }} · {{ dataset.rows }}
          </ion-checkbox>
          <span
            v-if="!travels(dataset, purpose)"
            class="data-row-detail"
          >{{ t('base.data.export.onlyBackup') }}</span>
        </li>
      </ul>
    </section>

    <InlineFeedback
      v-if="failure"
      tone="danger"
      data-testid="export-error"
    >
      {{ failure }}
    </InlineFeedback>
    <InlineFeedback
      v-if="done"
      tone="success"
      data-testid="export-done"
    >
      {{ done }}
    </InlineFeedback>

    <div class="data-actions">
      <ion-button
        data-testid="export-submit"
        :disabled="!canExport"
        @click="run"
      >
        {{ pending ? t('base.data.export.pending') : t('base.data.export.submit') }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.export-file {
  display: grid;
  gap: 12px;
}

.export-warning {
  color: var(--ion-color-danger-shade, #b42318);
}

.export-purpose {
  padding: 8px 0;
}

.export-purpose .data-row-detail {
  margin-left: 32px;
}

.export-bulk {
  display: flex;
  flex-wrap: wrap;
}

.export-columns {
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
}

.export-col {
  flex: 0 0 56px;
  text-align: center;
}

.export-feedback {
  margin-top: 12px;
}

.export-skeleton {
  height: 20px;
  margin: 12px 0;
}
</style>
