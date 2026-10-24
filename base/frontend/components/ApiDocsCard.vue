<script setup lang="ts">
// «API documentation» in Settings › General (BASE-G100; the old hub's HUB_SHELL-F161): «Show the API documentation»,
// off by default and saved at once (live `base.api_doc.settings`); on, «Open the API documentation» (its page). The
// side menu's «API» entry of the old hub needs a menu item shown on a condition, which the shell does not have yet: the
// way in is here and from Employees › API keys. Whoever does not run the business sees it disabled, and why; a change
// that cannot be saved says so and the switch goes back to the saved value.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton, IonToggle } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import '../settings.css';

const { t } = useBaseI18n();
const { data, status, refresh } = useLive('base.api_doc.settings', {});
const { run, pending } = useCommand('base.api_doc.settings_update');

const loaded = computed(() => data.value !== undefined);
const failed = computed(() => status.value === 'error' && !loaded.value);
const enabled = computed(() => data.value?.docs_enabled === true);
const canChange = computed(() => data.value?.can_change === true);
const saveFailed = ref(false);
// Repaints the switch on the saved value when a change could not be saved.
const repaint = ref(0);

async function onToggle(checked: boolean): Promise<void> {
  if (checked === enabled.value) return;
  saveFailed.value = false;
  try {
    await run({ docs_enabled: checked });
  } catch {
    saveFailed.value = true;
    repaint.value += 1;
  }
}
</script>

<template>
  <section
    class="settings-card"
    data-testid="api-docs-card"
  >
    <h2 class="settings-card__title">
      {{ t('base.apiDocs.card.title') }}
    </h2>
    <InlineFeedback
      v-if="failed"
      tone="danger"
      :heading="t('base.apiDocs.card.loadFailed')"
    >
      <template #actions>
        <IonButton
          size="small"
          fill="outline"
          data-testid="api-docs-retry"
          @click="refresh()"
        >
          {{ t('base.apiDocs.card.retry') }}
        </IonButton>
      </template>
    </InlineFeedback>
    <template v-else-if="loaded">
      <ion-toggle
        :key="`api-docs-${repaint}`"
        data-testid="api-docs-toggle"
        :checked="enabled"
        :disabled="!canChange || pending"
        label-placement="start"
        justify="space-between"
        @ion-change="onToggle($event.detail.checked)"
      >
        {{ t('base.apiDocs.card.toggle') }}
      </ion-toggle>
      <p class="settings-card__intro">
        {{ t('base.apiDocs.card.note') }}
      </p>
      <p
        v-if="!canChange"
        class="settings-card__note"
      >
        {{ t('base.apiDocs.card.adminOnly') }}
      </p>
      <InlineFeedback
        v-if="saveFailed"
        tone="danger"
        data-testid="api-docs-save-failed"
        :heading="t('base.apiDocs.card.saveFailed')"
      />
      <RouterLink
        v-if="enabled"
        to="/api-docs"
        class="api-docs-card__link"
        data-testid="api-docs-open"
      >
        {{ t('base.apiDocs.card.open') }}
      </RouterLink>
    </template>
  </section>
</template>

<style scoped>
.api-docs-card__link {
  display: inline-block;
  margin-top: 8px;
  color: var(--ion-color-primary);
  font-weight: 600;
  text-decoration: none;
}

.api-docs-card__link:hover,
.api-docs-card__link:focus-visible {
  text-decoration: underline;
}
</style>
