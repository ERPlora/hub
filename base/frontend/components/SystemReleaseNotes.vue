<script setup lang="ts">
// «What's new» under the version: the notes the running hub ships, newest first, in one request with the hub's own
// page size. Anyone in the business may read them, since they say nothing about it. The hub answers in the person's
// language, so a change of language asks again. Laid out with Settings › Data's summary-list classes.
import { EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { shallowRef, useId, watch } from 'vue';

import '../data.css';
import { useBaseI18n } from '../lib/i18n';
import { KIND_TONE, releaseDay } from '../lib/release-notes';
import type { ReleaseNote } from '../operations/system';

const { t, locale } = useBaseI18n();
const client = useLiveClient();
const headingId = useId();

const notes = shallowRef<ReleaseNote[]>();
const failed = shallowRef(false);

async function load(): Promise<void> {
  failed.value = false;
  try {
    notes.value = (await client.api.call('base.release_note.list', {})).items;
  } catch {
    failed.value = true;
  }
}
watch(locale, load, { immediate: true });
</script>

<template>
  <section
    class="data-card"
    data-testid="system-release-notes"
    :aria-labelledby="headingId"
  >
    <h3
      :id="headingId"
      class="data-title"
    >
      {{ t('base.system.releaseNotes.heading') }}
    </h3>
    <InlineFeedback
      v-if="failed"
      class="ion-margin-top"
      tone="danger"
      data-testid="system-release-notes-error"
      :heading="t('base.system.releaseNotes.error')"
    >
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="system-release-notes-retry"
          @click="load()"
        >
          {{ t('base.system.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <p
      v-else-if="notes === undefined"
      class="data-hint"
      data-testid="system-release-notes-loading"
      role="status"
    >
      {{ t('base.system.releaseNotes.loading') }}
    </p>
    <EmptyState
      v-else-if="notes.length === 0"
      icon="ion:sparkles-outline"
      data-testid="system-release-notes-empty"
      :message="t('base.system.releaseNotes.empty')"
    />
    <ul
      v-else
      class="data-rows"
    >
      <li
        v-for="note in notes"
        :key="note.id"
        class="data-row"
        data-testid="system-release-note"
        :data-id="note.id"
      >
        <div class="data-row-main">
          <p class="data-row-detail">
            <StatusPill
              class="ion-margin-end"
              size="sm"
              :dot="false"
              :tone="KIND_TONE[note.kind]"
              data-testid="system-release-note-kind"
              :label="t(`base.system.releaseNotes.kinds.${note.kind}`)"
            />
            <time
              :datetime="note.date"
              data-testid="system-release-note-day"
            >{{ releaseDay(note.date, locale) }}</time>
          </p>
          <span
            class="data-row-name"
            data-testid="system-release-note-title"
          >{{ note.title }}</span>
          <p
            class="data-row-detail"
            data-testid="system-release-note-body"
          >
            {{ note.body }}
          </p>
        </div>
      </li>
    </ul>
  </section>
</template>
