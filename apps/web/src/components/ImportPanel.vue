<template>
  <section>
    <p class="page-lead" data-testid="import-lead">{{ t('importPage.lead') }}</p>
    <p v-if="!isAdmin" class="page-lead admin-note">{{ t('importPage.adminOnly') }}</p>

    <!-- ── Paso 1: elegir fuente (zip local; nube = próximamente) ── -->
    <template v-if="step === 'pick'">
      <ion-card>
        <ion-card-content>
          <ion-label>
            <h2>{{ t('importPage.pickTitle') }}</h2>
            <p>{{ t('importPage.pickDesc') }}</p>
          </ion-label>

          <!-- Selector de fichero oculto disparado por un ion-button (patrón CSP-safe del cert). -->
          <input
            ref="fileInput"
            data-testid="import-file-input"
            type="file"
            accept=".zip,application/zip"
            style="display: none"
            @change="onFileChange"
          />

          <ion-button
            data-testid="import-pick-file"
            expand="block"
            class="mt-3"
            :disabled="!isAdmin || inspecting"
            @click="triggerFilePicker"
          >
            <ion-spinner v-if="inspecting" slot="start" name="crescent" />
            <HubIcon v-else slot="start" name="document-attach-outline" />
            {{ inspecting ? t('importPage.inspecting') : t('importPage.pickFile') }}
          </ion-button>

          <!-- «Desde la nube» (ADR-0121): catálogo de blueprints publicados en el vendor portal
               del SaaS. El runtime proxya con su X-Hub-Token y VERIFICA el sha256 del zip antes
               de dárnoslo; a partir de ahí el flujo es idéntico al de un fichero local. -->
          <ion-button
            data-testid="import-cloud"
            expand="block"
            fill="outline"
            class="mt-2"
            :disabled="!isAdmin || inspecting || loadingCatalog"
            @click="openCloudCatalog"
          >
            <ion-spinner v-if="loadingCatalog" slot="start" name="crescent" />
            <HubIcon v-else slot="start" name="cloud-download-outline" />
            {{ loadingCatalog ? t('importPage.loadingCatalog') : t('importPage.fromCloud') }}
          </ion-button>
        </ion-card-content>
      </ion-card>

      <!-- Catálogo de la nube -->
      <ion-card v-if="showCatalog" data-testid="import-cloud-catalog">
        <ion-card-content class="p-0">
          <ion-list v-if="catalog.length" lines="full">
            <ion-item
              v-for="bp in catalog"
              :key="bp.slug"
              button
              :disabled="inspecting"
              :data-testid="`import-cloud-item-${bp.slug}`"
              @click="pickFromCloud(bp)"
            >
              <HubIcon slot="start" name="cube-outline" />
              <ion-label>
                <h3>{{ bp.name }}</h3>
                <p>{{ bp.description || bp.slug }}</p>
              </ion-label>
              <ion-note slot="end">{{ bp.locale }} · v{{ bp.latest_version }}</ion-note>
            </ion-item>
          </ion-list>
          <ion-note v-else data-testid="import-cloud-empty" class="soon-note">
            {{ t('importPage.catalogEmpty') }}
          </ion-note>
        </ion-card-content>
      </ion-card>

      <ion-note v-if="error" data-testid="import-error" color="danger" class="error-note">
        {{ t('importPage.inspectErrorTitle') }}: {{ error }}
      </ion-note>
    </template>

    <!-- ── Paso 2: resumen del manifest + secciones DETECTADAS ── -->
    <template v-else-if="step === 'review' && manifest">
      <ion-card data-testid="import-manifest">
        <ion-card-content class="p-0">
          <ion-list lines="none">
            <ion-item>
              <HubIcon slot="start" name="cube-outline" />
              <ion-label>{{ t('importPage.manifestName') }}</ion-label>
              <ion-note slot="end">{{ manifest.name }}</ion-note>
            </ion-item>
            <ion-item>
              <HubIcon slot="start" name="language-outline" />
              <ion-label>{{ t('importPage.manifestLanguage') }}</ion-label>
              <ion-note slot="end">{{ manifest.locale }}</ion-note>
            </ion-item>
            <ion-item v-if="manifest.hub?.country">
              <HubIcon slot="start" name="business-outline" />
              <ion-label>{{ t('importPage.manifestCountry') }}</ion-label>
              <ion-note slot="end">{{ manifest.hub.country }}</ion-note>
            </ion-item>
            <ion-item>
              <HubIcon slot="start" name="apps-outline" />
              <ion-label>{{ t('importPage.manifestModules') }}</ion-label>
              <ion-note slot="end">{{ manifest.modules.length }}</ion-note>
            </ion-item>
            <ion-item v-if="createdLabel">
              <HubIcon slot="start" name="time-outline" />
              <ion-label>{{ t('importPage.manifestCreated') }}</ion-label>
              <ion-note slot="end">{{ createdLabel }}</ion-note>
            </ion-item>
          </ion-list>
        </ion-card-content>
      </ion-card>

      <!-- Solo las secciones PRESENTES en el bundle (manifest.sections); todas ON por defecto. -->
      <h2 class="section-title">{{ t('importPage.sections') }}</h2>
      <ion-card>
        <ion-card-content class="p-0">
          <!-- Ionic 8: la label la pone el PROPIO checkbox (label-placement/justify), no un
               ion-label hermano — texto clicable y nombre accesible sin aria-label duplicado. -->
          <ion-list lines="none">
            <ion-item v-if="hasUsers">
              <ion-checkbox
                data-testid="import-section-users"
                v-model="selUsers"
                justify="start"
                label-placement="end"
                alignment="start"
              >
                <h2 class="cb-title">{{ t('importPage.sectionUsers') }}</h2>
              </ion-checkbox>
            </ion-item>
            <ion-item v-if="hasSettings">
              <ion-checkbox
                data-testid="import-section-settings"
                v-model="selSettings"
                justify="start"
                label-placement="end"
                alignment="start"
              >
                <h2 class="cb-title">{{ t('importPage.sectionSettings') }}</h2>
              </ion-checkbox>
            </ion-item>
            <ion-item v-if="hasFiscal">
              <ion-checkbox
                data-testid="import-section-fiscal"
                v-model="selFiscal"
                justify="start"
                label-placement="end"
                alignment="start"
              >
                <h2 class="cb-title">{{ t('importPage.sectionFiscal') }}</h2>
                <p class="cb-desc">{{ t('importPage.sectionFiscalDesc') }}</p>
              </ion-checkbox>
            </ion-item>
            <ion-item v-if="hasMedia">
              <ion-checkbox
                data-testid="import-section-media"
                v-model="selMedia"
                justify="start"
                label-placement="end"
                alignment="start"
              >
                <h2 class="cb-title">{{ t('importPage.sectionMedia') }}</h2>
              </ion-checkbox>
            </ion-item>
          </ion-list>
        </ion-card-content>
      </ion-card>

      <!-- Módulos del manifest: instalar (si falta) + aplicar sus datos si el bundle los trae
           (with_data). La selección del contrato es por id: desmarcar excluye módulo Y datos. -->
      <template v-if="manifest.modules.length">
        <h2 class="section-title">{{ t('importPage.modulesTitle') }}</h2>
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <ion-item v-for="m in moduleRows" :key="m.id">
                <ion-checkbox
                  :checked="m.include"
                  justify="start"
                  label-placement="end"
                  alignment="start"
                  @ion-change="onModuleToggle(m.id, $event)"
                >
                  <h2 class="cb-title">{{ m.id }}</h2>
                  <p class="cb-desc">
                    v{{ m.version }}
                    <template v-if="m.withData"> · {{ t('importPage.withData') }}</template>
                  </p>
                </ion-checkbox>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>
      </template>

      <ion-note v-if="error" data-testid="import-error" color="danger" class="error-note">
        {{ t('importPage.importErrorTitle') }}: {{ error }}
      </ion-note>

      <ion-button
        data-testid="import-submit"
        class="mt-3"
        expand="block"
        :disabled="!isAdmin"
        @click="doImport"
      >
        <HubIcon slot="start" name="cloud-upload-outline" />
        {{ t('importPage.import') }}
      </ion-button>
      <ion-button expand="block" fill="clear" color="medium" @click="resetToPick">
        {{ t('importPage.back') }}
      </ion-button>
    </template>

    <!-- ── Paso 3a: progreso ── -->
    <template v-else-if="step === 'importing'">
      <ion-item lines="none">
        <ion-spinner slot="start" name="crescent" />
        <ion-label>{{ t('importPage.importing') }}</ion-label>
      </ion-item>
    </template>

    <!-- ── Paso 3b: INFORME final por sección (best-effort: Applied/Skipped/Failed) ── -->
    <template v-else-if="step === 'report' && report">
      <h2 class="section-title">{{ t('importPage.reportTitle') }}</h2>
      <ion-card data-testid="import-report">
        <ion-card-content class="p-0">
          <ion-list lines="none">
            <ion-item v-for="row in reportRows" :key="row.section">
              <HubIcon slot="start" :name="row.icon" :style="{ color: `var(--ion-color-${row.color})` }" />
              <ion-label class="ion-text-wrap">
                <h2>{{ row.label }}</h2>
                <!-- Motivo del fallo tal cual lo reportó el motor (informe honesto). -->
                <p v-if="row.reason" class="fail-reason">{{ row.reason }}</p>
              </ion-label>
              <ion-note slot="end" :color="row.color">{{ row.statusLabel }}</ion-note>
            </ion-item>
          </ion-list>
        </ion-card-content>
      </ion-card>

      <ion-button data-testid="import-done" class="mt-3" expand="block" @click="finish">
        <HubIcon slot="start" name="home-outline" />
        {{ t('importPage.done') }}
      </ion-button>
    </template>
  </section>
</template>

<script setup lang="ts">
// Panel CORE «Importar configuración» (ADR-0113 §4, architecture/hub/export-import.md).
// Vive en la pestaña Datos de Ajustes (/settings?tab=data) junto al panel de export — decisión
// del humano 2026-07-12 (antes era la página /import).
// Tres pasos: (1) zip local (nube = próximamente, el registro SaaS no existe) → (2) inspect:
// resumen del manifest + checkboxes de las secciones DETECTADAS → (3) import en orden «migrate»
// con INFORME final por sección (Applied ✓ / Skipped — / Failed ✗ con motivo, best-effort).
// El gate real es del runtime (solo owner/admin); el `:disabled` de aquí es cosmético.
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonCard,
  IonCardContent,
  IonList,
  IonItem,
  IonLabel,
  IonNote,
  IonCheckbox,
  IonButton,
  IonSpinner,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { isAdmin } from '../lib/session';
import { refreshModuleNav } from '../lib/nav';
import {
  inspectBlueprint,
  importBlueprint,
  sectionStatusInfo,
  fetchBlueprintCatalog,
  downloadBlueprint,
  type BlueprintManifest,
  type CatalogBlueprint,
  type ImportReport,
} from '../lib/runtime';

const { t } = useI18n();
const router = useRouter();

type Step = 'pick' | 'review' | 'importing' | 'report';
const step = ref<Step>('pick');
const error = ref<string>('');

// ── Paso 1: fichero local → inspect ──
const fileInput = ref<HTMLInputElement | null>(null);
const inspecting = ref<boolean>(false);
const uploadId = ref<string>('');
const manifest = ref<BlueprintManifest | null>(null);

function triggerFilePicker(): void {
  fileInput.value?.click();
}

async function onFileChange(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  await inspectAndReview(file);
  input.value = ''; // permite re-elegir el mismo fichero tras un error
}

/** Paso común: un zip (local o de la nube) → inspect → pantalla de revisión. */
async function inspectAndReview(zip: Blob): Promise<void> {
  error.value = '';
  inspecting.value = true;
  try {
    // Integridad dura en el server (SHA256/manifest/zip-slip): un zip malo se rechaza SIN efectos.
    const res = await inspectBlueprint(zip);
    uploadId.value = res.upload_id;
    manifest.value = res.manifest;
    seedSelection(res.manifest);
    step.value = 'review';
  } catch (err) {
    // Mensaje HONESTO del server (inspectBlueprint ya extrajo el envelope/texto).
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    inspecting.value = false;
  }
}

// ── Paso 1 (bis): fuente NUBE — catálogo de blueprints del SaaS (ADR-0121) ──
const loadingCatalog = ref<boolean>(false);
const showCatalog = ref<boolean>(false);
const catalog = ref<CatalogBlueprint[]>([]);

async function openCloudCatalog(): Promise<void> {
  error.value = '';
  loadingCatalog.value = true;
  try {
    catalog.value = await fetchBlueprintCatalog();
    showCatalog.value = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingCatalog.value = false;
  }
}

/**
 * Elegir un blueprint de la nube. El runtime lo descarga de Object Storage y **verifica su
 * sha256** antes de entregárnoslo; si no casa, `downloadBlueprint` lanza y no se importa nada.
 * A partir de ahí es el MISMO flujo que un zip local.
 */
async function pickFromCloud(bp: CatalogBlueprint): Promise<void> {
  error.value = '';
  inspecting.value = true;
  try {
    const zip = await downloadBlueprint(bp.slug);
    showCatalog.value = false;
    await inspectAndReview(zip);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    inspecting.value = false;
  }
}

// ── Paso 2: secciones detectadas + módulos del manifest ──
const selUsers = ref<boolean>(true);
const selSettings = ref<boolean>(true);
const selFiscal = ref<boolean>(true);
const selMedia = ref<boolean>(true);

interface ModuleRow {
  id: string;
  version: string;
  withData: boolean;
  include: boolean;
}
const moduleRows = ref<ModuleRow[]>([]);

/** ¿El bundle trae la sección? Tolerante con el alias corto (`hub_users` | `users`). */
function hasSection(...keys: string[]): boolean {
  const sections = manifest.value?.sections ?? [];
  return keys.some((k) => sections.includes(k));
}
const hasUsers = computed<boolean>(() => hasSection('hub_users', 'users'));
const hasSettings = computed<boolean>(() => hasSection('hub_settings', 'settings'));
const hasFiscal = computed<boolean>(() => hasSection('fiscal'));
const hasMedia = computed<boolean>(() => hasSection('media'));

const createdLabel = computed<string>(() => {
  const raw = manifest.value?.created_at;
  if (!raw) return '';
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? raw : d.toLocaleString();
});

/** Siembra la selección a partir del manifest recién inspeccionado (todo ON por defecto). */
function seedSelection(m: BlueprintManifest): void {
  selUsers.value = true;
  selSettings.value = true;
  selFiscal.value = true;
  selMedia.value = true;
  moduleRows.value = (m.modules ?? []).map((mod) => ({
    id: mod.id,
    version: mod.version,
    withData: Boolean(mod.with_data),
    include: true,
  }));
}

function onModuleToggle(id: string, e: Event): void {
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  moduleRows.value = moduleRows.value.map((m) => (m.id === id ? { ...m, include: checked } : m));
}

function resetToPick(): void {
  step.value = 'pick';
  error.value = '';
  manifest.value = null;
  uploadId.value = '';
  moduleRows.value = [];
}

// ── Paso 3: importar → informe ──
const report = ref<ImportReport | null>(null);

async function doImport(): Promise<void> {
  if (!isAdmin.value) return; // defensa: el botón ya está disabled
  error.value = '';
  step.value = 'importing';
  try {
    report.value = await importBlueprint(uploadId.value, {
      users: hasUsers.value && selUsers.value,
      settings: hasSettings.value && selSettings.value,
      fiscal: hasFiscal.value && selFiscal.value,
      media: hasMedia.value && selMedia.value,
      modules: moduleRows.value.filter((m) => m.include).map((m) => m.id),
    });
    step.value = 'report';
    // El import pudo instalar módulos: refresca el menú del shell.
    await refreshModuleNav();
  } catch (err) {
    // Rechazo ENTERO (integridad dura / server caído): vuelve al resumen con el motivo del server.
    error.value = err instanceof Error ? err.message : String(err);
    step.value = 'review';
  }
}

/** Nombre legible de una sección del informe (`modules/<id>` → «Módulo <id>»). */
function sectionLabel(section: string): string {
  if (section.startsWith('modules/')) {
    return t('importPage.sectionModule', { id: section.slice('modules/'.length) });
  }
  const map: Record<string, string> = {
    hub_users: t('importPage.sectionUsers'),
    users: t('importPage.sectionUsers'),
    hub_settings: t('importPage.sectionSettings'),
    settings: t('importPage.sectionSettings'),
    fiscal: t('importPage.sectionFiscal'),
    media: t('importPage.sectionMedia'),
  };
  return map[section] ?? section;
}

interface ReportRow {
  section: string;
  label: string;
  icon: string;
  color: 'success' | 'medium' | 'danger';
  statusLabel: string;
  reason?: string;
}

// Informe pintado tal cual llega (contrato JSON del motor): Applied ✓ verde · Skipped — gris ·
// Failed ✗ rojo con su motivo. sectionStatusInfo tolera las dos formas serde del enum.
const visual = {
  applied: { icon: 'checkmark-circle-outline', color: 'success', label: () => t('importPage.statusApplied') },
  skipped: { icon: 'remove-circle-outline', color: 'medium', label: () => t('importPage.statusSkipped') },
  failed: { icon: 'close-circle-outline', color: 'danger', label: () => t('importPage.statusFailed') },
} as const;

// El motor del runtime NO copia media (lo hace la capa server) y la reporta `Skipped`; su
// resultado REAL viene en `report.media`. Traducimos ese contador al estado verdadero de la fila
// para no mentir con un «Saltado» cuando las imágenes sí se copiaron (informe de review, hallazgo #1).
function mediaStatus(m: NonNullable<ImportReport['media']>): { kind: 'applied' | 'skipped' | 'failed'; reason?: string } {
  const reason = m.failed > 0 ? t('importPage.mediaFailed', { n: m.failed }) : undefined;
  if (m.copied > 0) return { kind: 'applied', reason };
  if (m.failed > 0) return { kind: 'failed', reason };
  return { kind: 'skipped' }; // seleccionada pero sin ficheros que copiar
}

const reportRows = computed<ReportRow[]>(() =>
  (report.value?.sections ?? []).map((s) => {
    const media = report.value?.media;
    const info =
      s.section === 'media' && media ? mediaStatus(media) : sectionStatusInfo(s.status);
    const v = visual[info.kind];
    return {
      section: s.section,
      label: sectionLabel(s.section),
      icon: v.icon,
      color: v.color,
      statusLabel: v.label(),
      reason: info.reason,
    };
  }),
);

async function finish(): Promise<void> {
  await router.replace('/dashboard');
}
</script>

<style scoped>
.page-lead {
  color: var(--ion-color-medium);
  margin: 0 0 0.5rem;
}
.admin-note {
  color: var(--ion-color-warning-shade, var(--ion-color-warning));
}
.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 1rem 0 0.5rem;
}
/* Ionic pinta `.label-text-wrapper` DENTRO del shadow con `white-space:nowrap` + ellipsis, así
   que la clase `ion-text-wrap` (que actúa sobre el host) NO la vence y el texto se trunca en
   móvil. La única vía desde fuera es el shadow part `label`. */
ion-checkbox::part(label) {
  white-space: normal;
}
/* Tipografía de la label del checkbox (antes la daba ion-label con sus h2/p). */
.cb-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 500;
}
.cb-desc {
  margin: 0.1rem 0 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
.soon-note {
  display: block;
  margin-top: 0.35rem;
  font-size: 0.8rem;
}
.error-note {
  display: block;
  margin-top: 0.75rem;
}
.fail-reason {
  color: var(--ion-color-danger);
}
</style>
