<script setup lang="ts">
// The API's documentation (BASE-G150, G04; the old hub's ApiDocsPage). Not Swagger UI: production enforces Trusted
// Types, which it does not support; the same document, read here and downloadable for Postman or any other tool. Live
// `base.api_doc.get`: how to call it (a key from Employees › API keys, as a bearer; said too when this business cannot
// make keys yet), then one section per app with its routes — method, path, what it does — and, on opening one, its
// parameters and its body. Hidden, it says so and who runs the business is sent to Settings › General; a document
// that cannot be read says so with «Retry»; none published, says so.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, type OutputOf, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, onMounted, shallowRef, watch } from 'vue';

import { apiDocFileName, apiDocSections } from '../lib/api-docs';
import { saveFile } from '../lib/data';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const session = useSession();
const admin = computed(() => session.can('base.administer_hub'));
const client = useLiveClient();
const data = shallowRef<OutputOf<'base.api_doc.get'>>();
const failure = shallowRef<'hidden' | 'failed' | null>(null);

async function refresh(): Promise<void> {
  failure.value = null;
  try {
    data.value = await client.api.call('base.api_doc.get', {});
  } catch (error) {
    failure.value = error instanceof ApiError && error.code === 'base.api_docs_hidden' ? 'hidden' : 'failed';
  }
}
onMounted(() => void refresh());
// The page stays alive in the navigation stack: shown or hidden again in Settings, it asks for the document again.
const settings = useLive('base.api_doc.settings', {});
watch(
  () => settings.data.value?.docs_enabled,
  (now, before) => {
    if (before !== undefined && now !== before) void refresh();
  },
);

const failed = computed(() => failure.value !== null && data.value === undefined);
const hidden = computed(() => failure.value === 'hidden');
const sections = computed(() => (data.value ? apiDocSections(data.value.document, data.value.apps) : []));

function download(): void {
  if (!data.value) return;
  const blob = new Blob([JSON.stringify(data.value.document, null, 2)], { type: 'application/json' });
  saveFile(apiDocFileName(window.location.hostname.split('.')[0] ?? ''), blob);
}
</script>

<template>
  <AppPage
    :title="t('base.apiDocs.title')"
    back-href="/settings"
    content-layout="detail"
  >
    <div class="api-docs">
      <template v-if="hidden">
        <InlineFeedback
          tone="info"
          data-testid="api-docs-hidden"
          :heading="t('base.apiDocs.hidden')"
        >
          <template
            v-if="admin"
            #actions
          >
            <RouterLink
              to="/settings"
              class="api-docs__link"
              data-testid="api-docs-show"
            >
              {{ t('base.apiDocs.showIt') }}
            </RouterLink>
          </template>
        </InlineFeedback>
      </template>
      <InlineFeedback
        v-else-if="failed"
        tone="danger"
        :heading="t('base.apiDocs.error')"
      >
        <template #actions>
          <IonButton
            size="small"
            fill="outline"
            data-testid="api-docs-retry"
            @click="refresh()"
          >
            {{ t('base.apiDocs.retry') }}
          </IonButton>
        </template>
      </InlineFeedback>
      <p
        v-else-if="!data"
        class="api-docs__loading"
      >
        <IonSpinner name="crescent" />
        {{ t('base.apiDocs.loading') }}
      </p>
      <template v-else>
        <p class="api-docs__intro">
          {{ t('base.apiDocs.intro') }}
        </p>
        <InlineFeedback
          v-if="!data.keys_available"
          tone="warning"
          data-testid="api-docs-keys-soon"
        >
          {{ t('base.apiDocs.keysSoon') }}
        </InlineFeedback>
        <div class="api-docs__actions">
          <IonButton
            fill="outline"
            size="small"
            data-testid="api-docs-download"
            @click="download"
          >
            {{ t('base.apiDocs.download') }}
          </IonButton>
        </div>
        <p
          v-if="sections.length === 0"
          class="api-docs__empty"
        >
          {{ t('base.apiDocs.empty') }}
        </p>
        <section
          v-for="section in sections"
          :key="section.id"
          class="api-docs__section"
          data-testid="api-docs-section"
        >
          <h2 class="api-docs__app">
            {{ section.name }}
          </h2>
          <details
            v-for="route in section.routes"
            :key="route.id"
            class="api-docs__route"
            data-testid="api-docs-route"
          >
            <summary class="api-docs__summary">
              <span
                class="api-docs__method"
                :class="`api-docs__method--${route.method.toLowerCase()}`"
              >{{ route.method }}</span>
              <code class="api-docs__path">{{ route.path }}</code>
              <span class="api-docs__what">{{ route.description || route.summary }}</span>
            </summary>
            <div class="api-docs__detail">
              <template v-if="route.parameters.length > 0">
                <h3 class="api-docs__heading">
                  {{ t('base.apiDocs.parameters') }}
                </h3>
                <ul class="api-docs__parameters">
                  <li
                    v-for="parameter in route.parameters"
                    :key="`${parameter.where}-${parameter.name}`"
                  >
                    <code>{{ parameter.name }}</code>
                    <span class="api-docs__type">{{ parameter.where }} · {{ parameter.type }}</span>
                    <span
                      v-if="parameter.required"
                      class="api-docs__required"
                    >{{ t('base.apiDocs.required') }}</span>
                    <span
                      v-if="parameter.description"
                      class="api-docs__type"
                    >{{ parameter.description }}</span>
                  </li>
                </ul>
              </template>
              <template v-if="route.body">
                <h3 class="api-docs__heading">
                  {{ t('base.apiDocs.body') }} · <code>{{ route.body.name }}</code>
                </h3>
                <pre class="api-docs__schema">{{ JSON.stringify(route.body.schema, null, 2) }}</pre>
              </template>
            </div>
          </details>
        </section>
      </template>
    </div>
  </AppPage>
</template>

<style scoped>
.api-docs {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.api-docs__intro,
.api-docs__empty,
.api-docs__loading {
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
}

.api-docs__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.api-docs__actions {
  display: flex;
  justify-content: flex-end;
}

.api-docs__section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.api-docs__app {
  margin: 8px 0 0;
  font-size: 1rem;
  font-weight: 600;
}

.api-docs__route {
  border: 1px solid var(--ion-color-step-150, #d7d8da);
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-card-background, var(--ion-background-color));
  min-width: 0;
}

.api-docs__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  padding: 10px 12px;
  cursor: pointer;
}

.api-docs__method {
  min-width: 3.5rem;
  padding: 2px 6px;
  border-radius: 6px;
  background: var(--ion-color-step-100, #e6e7e9);
  font-size: 0.75rem;
  font-weight: 700;
  text-align: center;
}

.api-docs__method--get {
  background: rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.14);
  color: var(--ion-color-primary);
}

.api-docs__method--post {
  background: rgba(var(--ion-color-success-rgb, 45, 211, 111), 0.16);
  color: var(--ion-color-success-shade, #28ba62);
}

.api-docs__path {
  overflow-wrap: anywhere;
  font-size: 0.8125rem;
}

.api-docs__what {
  flex-basis: 100%;
  color: var(--ion-color-medium);
  font-size: 0.8125rem;
}

.api-docs__detail {
  padding: 0 12px 12px;
}

.api-docs__heading {
  margin: 8px 0 4px;
  font-size: 0.8125rem;
  font-weight: 600;
}

.api-docs__parameters {
  margin: 0;
  padding-left: 18px;
  font-size: 0.8125rem;
}

.api-docs__parameters li {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
}

.api-docs__type {
  color: var(--ion-color-medium);
}

.api-docs__required {
  color: var(--ion-color-danger);
}

.api-docs__schema {
  margin: 0;
  max-height: 20rem;
  overflow: auto;
  padding: 8px;
  border-radius: 8px;
  background: var(--ion-color-step-50, #f3f3f4);
  font-size: 0.75rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.api-docs__link {
  color: var(--ion-color-primary);
  font-weight: 600;
}
</style>
