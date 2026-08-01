<!--
  PublicPresencePanel — toggle "Presencia web pública" de Ajustes (ADR-0177).

  Activa/desactiva la PARTE PÚBLICA del hub (landing + páginas públicas) escribiendo la clave core
  `public.landing.visible` (bool, default false) por la API de settings del hub ya existente
  (`PUT /api/settings`, hub-settings.ts). Con OFF, el hub no tiene presencia web pública.

  Mismo patrón que el toggle "Mostrar documentación de la API" de SettingsPage: refleja el valor
  server-side de la cache reactiva `hubSettings`, persiste al instante (optimista con revert + toast)
  y solo lo cambia un admin (el `:disabled` es cosmético; el runtime revalida owner/admin).
-->
<template>
  <ion-card>
    <ion-card-content class="p-0">
      <ion-item lines="none">
        <HubIcon slot="start" name="globe-outline" />
        <ion-label>
          <h2>{{ t('settings.publicPresence') }}</h2>
          <p>{{ t('settings.publicPresenceDesc') }}</p>
          <ion-note data-testid="public-presence-restart-note">
            {{ t('settings.publicPresenceRestartRequired') }}
          </ion-note>
        </ion-label>
        <ion-toggle
          :checked="landingVisible"
          :disabled="!isAdmin"
          :aria-label="t('settings.publicPresence')"
          data-testid="public-presence-toggle"
          slot="end"
          @ion-change="onToggle($event)"
        />
      </ion-item>
      <ion-item v-if="isAdmin" lines="none">
        <HubIcon slot="start" name="create-outline" />
        <ion-label>
          <h2>{{ t('settings.publicPageEditor') }}</h2>
          <p>{{ t('settings.publicPageEditorDesc') }}</p>
        </ion-label>
        <ion-button slot="end" fill="outline" data-testid="public-page-open" @click="openEditor">
          {{ t('settings.publicPageEdit') }}
        </ion-button>
      </ion-item>
    </ion-card-content>
  </ion-card>

  <ion-modal :is-open="editorOpen" data-testid="public-page-modal" @did-dismiss="closeEditor">
    <ion-header>
      <ion-toolbar>
        <ion-title>{{ t('settings.publicPageEditor') }}</ion-title>
        <ion-buttons slot="end">
          <ion-button
            :aria-label="t('settings.publicPageClose')"
            data-testid="public-page-close"
            @click="closeEditor"
          >
            <HubIcon name="close-outline" />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <div class="editor-path">
        <ion-select
          v-model="pagePath"
          interface="popover"
          :label="t('settings.publicPagePath')"
          label-placement="stacked"
          data-testid="public-page-path"
        >
          <ion-select-option
            v-for="page in pageDefinitions"
            :key="`${page.module_id}:${page.path}`"
            :value="page.path"
          >
            {{ page.title }} · /{{ page.path }}
          </ion-select-option>
        </ion-select>
        <ion-button
          fill="outline"
          :disabled="loadingPage || savingPage"
          data-testid="public-page-load"
          @click="loadPage"
        >
          {{ t('settings.publicPageLoad') }}
        </ion-button>
      </div>
      <ok-inline-feedback v-if="!loadingPage && pageDefinitions.length === 0" tone="info">
        {{ t('settings.publicPageNone') }}
      </ok-inline-feedback>
      <div v-if="loadingPage" class="editor-loading"><ion-spinner name="dots" /></div>
      <PageEditor
        v-else-if="pageDocument"
        ref="pageEditor"
        :key="editorKey"
        :initial-data="pageDocument"
        :media-folder="`pages/${pagePath}`"
      />
    </ion-content>
    <ion-footer>
      <ion-toolbar>
        <ion-button
          slot="end"
          :disabled="savingPage || loadingPage || !pageDocument"
          data-testid="public-page-save"
          @click="savePage"
        >
          <ion-spinner v-if="savingPage" slot="start" name="dots" />
          {{ t('settings.publicPageSave') }}
        </ion-button>
      </ion-toolbar>
    </ion-footer>
  </ion-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import type { OutputData } from '@editorjs/editorjs';
import { useI18n } from 'vue-i18n';
import {
  IonButton, IonButtons, IonCard, IonCardContent, IonContent, IonFooter, IonHeader,
  IonItem, IonLabel, IonModal, IonNote, IonSelect, IonSelectOption, IonSpinner, IonTitle,
  IonToggle, IonToolbar,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import PageEditor from './PageEditor.vue';
import { isAdmin } from '../lib/session';
import { hubSettings, updateHubSettings } from '../lib/hub-settings';
import {
  getPublicPage,
  listPublicPages,
  normalizePublicPagePath,
  putPublicPage,
  type PublicPageDefinition,
} from '../lib/public-pages';
import { toastSuccess, toastError } from '../lib/toast';

// Clave core plana del store k/v (ADR-0177). `as const` para que el tipo del PUT sea exacto.
const KEY = 'public.landing.visible' as const;

const { t } = useI18n();

// Refleja el valor server-side actual (cache reactiva sembrada en el boot / al abrir Ajustes).
const landingVisible = ref<boolean>(hubSettings.value?.[KEY] ?? false);
const editorOpen = ref(false);
const loadingPage = ref(false);
const savingPage = ref(false);
const pagePath = ref('');
const pageDefinitions = ref<PublicPageDefinition[]>([]);
const pageDocument = ref<OutputData | null>(null);
const pageEditor = ref<InstanceType<typeof PageEditor> | null>(null);
const editorKey = ref(0);
watch(hubSettings, (s) => {
  if (s) landingVisible.value = s[KEY];
});

// Persiste al instante (solo admin). Optimista con revert: actualiza el toggle ya y lo revierte si
// el runtime rechaza (p. ej. 401 no-admin), con toast de éxito/fallo.
async function onToggle(e: Event): Promise<void> {
  if (!isAdmin.value) return; // defensa: el toggle ya está disabled para no-admin
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  if (checked === landingVisible.value) return; // evita re-disparo al re-sincronizar :checked
  const prev = landingVisible.value;
  landingVisible.value = checked;
  try {
    await updateHubSettings({ [KEY]: checked });
    await toastSuccess(t('settings.publicPresenceRestartRequired'));
  } catch {
    landingVisible.value = prev;
    await toastError(t('settings.saveError'));
  }
}

async function openEditor(): Promise<void> {
  if (!isAdmin.value) return;
  editorOpen.value = true;
  loadingPage.value = true;
  try {
    pageDefinitions.value = await listPublicPages();
    if (!pageDefinitions.value.some((page) => page.path === pagePath.value)) {
      pagePath.value = pageDefinitions.value[0]?.path ?? '';
    }
  } catch {
    pageDefinitions.value = [];
    await toastError(t('settings.publicPageLoadError'));
  } finally {
    loadingPage.value = false;
  }
  if (pagePath.value) await loadPage();
}

async function loadPage(): Promise<void> {
  if (loadingPage.value || savingPage.value) return;
  loadingPage.value = true;
  pageDocument.value = null;
  try {
    pagePath.value = normalizePublicPagePath(pagePath.value);
    pageDocument.value = await getPublicPage(pagePath.value);
    editorKey.value += 1;
  } catch {
    pageDocument.value = { blocks: [] };
    await toastError(t('settings.publicPageLoadError'));
  } finally {
    loadingPage.value = false;
  }
}

function closeEditor(): void {
  editorOpen.value = false;
  pageDocument.value = null;
  pageDefinitions.value = [];
}

async function savePage(): Promise<void> {
  if (!pageEditor.value || savingPage.value) return;
  savingPage.value = true;
  try {
    const document = await pageEditor.value.save();
    await putPublicPage(pagePath.value, document);
    pageDocument.value = document;
    await toastSuccess(t('settings.publicPageSaved'));
  } catch {
    await toastError(t('settings.publicPageSaveError'));
  } finally {
    savingPage.value = false;
  }
}
</script>

<style scoped>
.editor-loading {
  display: flex;
  justify-content: center;
  padding: 3rem;
}

.editor-path {
  display: flex;
  align-items: end;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.editor-path ion-select {
  flex: 1;
}
</style>
