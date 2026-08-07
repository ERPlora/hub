<template>
  <section>
    <p class="page-lead" data-testid="import-lead">{{ t('importPage.lead') }}</p>
    <p v-if="!isAdmin" class="page-lead admin-note">{{ t('importPage.adminOnly') }}</p>

    <!-- ── Paso 1: elegir fuente — catálogo visible con tarjetas por defecto ──
         `ok-data-table` aporta búsqueda, tabla y tarjetas sin duplicar otro selector. Subir un
         archivo sigue siendo una acción distinta: no fingimos que un fichero local es una fila. -->
    <template v-if="step === 'pick'">
      <div class="source-heading">
        <ion-label class="page-lead-block">
          <h2>{{ t('importPage.pickTitle') }}</h2>
          <p>{{ t('importPage.pickDesc') }}</p>
        </ion-label>

        <ion-button
          fill="outline"
          size="small"
          :disabled="!isAdmin || inspecting"
          data-testid="import-upload-local"
          @click="triggerFilePicker"
        >
          <ion-spinner
            v-if="inspecting && activeSource === 'local'"
            slot="start"
            name="crescent"
          />
          <HubIcon v-else slot="start" name="cloud-upload-outline" />
          {{ t('importPage.fromLocal') }}
        </ion-button>
      </div>

      <!-- Selector de fichero oculto disparado por el botón (patrón CSP-safe del cert). -->
      <input
        ref="fileInput"
        data-testid="import-file-input"
        type="file"
        accept=".zip,application/zip"
        style="display: none"
        @change="onFileChange"
      />

      <div v-if="loadingCatalog" class="cloud-loading" data-testid="import-cloud-loading">
        <ion-spinner name="crescent" />
        <span>{{ t('importPage.loadingCatalog') }}</span>
      </div>

      <!-- OutfitKit centraliza búsqueda, paginación y conmutador tabla/tarjetas. Tarjetas es la
           vista inicial; la tabla queda disponible cuando el catálogo crezca. -->
      <ok-data-table
        v-else
        ref="blueprintTable"
        data-testid="import-blueprint-table"
        row-key-field="slug"
        :columns="blueprintColumns"
        :rows="blueprintRows"
        :views="['cards', 'table']"
        default-view="cards"
        :searchKeys="['name', 'description', 'locale', 'country']"
        :actions="blueprintActions"
        :cardTitle="blueprintCardTitle"
        :renderCard="renderBlueprintCard"
        :labels="tableLabels"
        :search-placeholder="t('importPage.searchTemplates')"
        :empty-message="catalogEmptyMessage"
        page-size="24"
      ></ok-data-table>

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

            <!-- Los módulos que el import instaló (o no pudo instalar). La pantalla los promete;
                 el informe tiene que responder por ellos. -->
            <ion-item-divider v-if="moduleInstallRows.length">
              <ion-label>{{ t('importPage.reportModules') }}</ion-label>
            </ion-item-divider>
            <ion-item v-for="row in moduleInstallRows" :key="row.section">
              <HubIcon slot="start" :name="row.icon" :style="{ color: `var(--ion-color-${row.color})` }" />
              <ion-label class="ion-text-wrap">
                <h2>{{ row.label }}</h2>
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
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
import { dataTableLabels } from '../lib/data-table-labels';
import { isAdmin } from '../lib/session';
import { refreshModuleNav } from '../lib/nav';
import {
  inspectBlueprint,
  importBlueprint,
  sectionStatusInfo,
  sectionDiscardCode,
  moduleInstallStatusInfo,
  fetchBlueprintCatalog,
  downloadBlueprint,
  type BlueprintManifest,
  type CatalogBlueprint,
  type ImportReport,
  type ModuleInstallPurchase,
  type SectionDiscardCode,
} from '../lib/runtime';
import { formatAmount } from '../lib/money';

const { t, locale } = useI18n();
const router = useRouter();

type Step = 'pick' | 'review' | 'importing' | 'report';
const step = ref<Step>('pick');
const error = ref<string>('');

// ── Paso 1: fichero local → inspect ──
const fileInput = ref<HTMLInputElement | null>(null);
const inspecting = ref<boolean>(false);
const activeSource = ref<string>('');
const uploadId = ref<string>('');
const manifest = ref<BlueprintManifest | null>(null);

type BlueprintRow = CatalogBlueprint & Record<string, unknown>;
type TableRow = Record<string, unknown>;

interface DataTableColumn {
  key: string;
  header: string;
  width?: string;
  sortable?: boolean;
  format?: (row: TableRow) => string;
}

interface DataTableAction {
  id: string;
  label: string;
  color?: string;
  disabled?: (row: TableRow) => boolean;
  loading?: (row: TableRow) => boolean;
}

type BlueprintTableElement = HTMLElement & {
  labels: Record<string, string>;
  columnPicker: boolean;
  pageSizeOptions: number[];
};

const blueprintTable = ref<BlueprintTableElement | null>(null);
const tableLabels = computed(() => dataTableLabels(locale.value));

function triggerFilePicker(): void {
  fileInput.value?.click();
}

async function onFileChange(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  activeSource.value = 'local';
  try {
    await inspectAndReview(file);
  } finally {
    activeSource.value = '';
    input.value = ''; // permite re-elegir el mismo fichero tras un error
  }
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
// Se carga SOLO al entrar (ya no detrás de un botón): el usuario debe ver de un vistazo qué
// blueprints puede cargar. Solo admin puede importar, así que solo admin dispara la carga.
const loadingCatalog = ref<boolean>(false);
const catalog = ref<CatalogBlueprint[]>([]);
const blueprintRows = computed<BlueprintRow[]>(() =>
  catalog.value.map((blueprint) => ({ ...blueprint })),
);

function formatSize(sizeBytes: number): string {
  if (sizeBytes <= 0) return '—';
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${Math.round(sizeBytes / 1024)} KB`;
  const megabytes = sizeBytes / (1024 * 1024);
  return `${megabytes >= 10 ? Math.round(megabytes) : megabytes.toFixed(1)} MB`;
}

const blueprintColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('importPage.colTemplate'), width: '9rem' },
  {
    key: 'description',
    header: t('importPage.colDescription'),
    width: '22rem',
    sortable: false,
  },
  {
    key: 'locale',
    header: t('importPage.colLanguage'),
    width: '4.5rem',
    format: (row) => String(row.locale ?? '').toUpperCase(),
  },
  {
    key: 'latest_version',
    header: t('importPage.colVersion'),
    width: '5.5rem',
    format: (row) => `v${String(row.latest_version ?? '')}`,
  },
  {
    key: 'downloads',
    header: t('importPage.colDownloads'),
    width: '6rem',
    format: (row) => new Intl.NumberFormat(locale.value).format(Number(row.downloads ?? 0)),
  },
  {
    key: 'size_bytes',
    header: t('importPage.colSize'),
    width: '5rem',
    format: (row) => formatSize(Number(row.size_bytes ?? 0)),
  },
]);

const blueprintActions = computed<DataTableAction[]>(() => [
  {
    id: 'use',
    label: t('importPage.useTemplate'),
    color: 'primary',
    disabled: () => !isAdmin.value || inspecting.value,
    loading: (row) => inspecting.value && activeSource.value === String(row.slug),
  },
]);

function blueprintCardTitle(row: TableRow): Node {
  const title = document.createElement('span');
  title.textContent = String(row.name ?? row.slug ?? '');
  title.style.cssText = 'display:block;width:100%;text-align:left;font-size:1rem;color:var(--color)';
  return title;
}

function addCardRow(root: HTMLElement, label: string, value: string): void {
  const row = document.createElement('div');
  row.className = 'rrow';
  const key = document.createElement('span');
  key.className = 'rk';
  key.textContent = label;
  const content = document.createElement('span');
  content.className = 'rv';
  content.textContent = value;
  row.append(key, content);
  root.append(row);
}

/** Cuerpo de tarjeta para `ok-data-table`; usa sus clases internas `rrow/rk/rv`. */
function renderBlueprintCard(row: TableRow): Node {
  const root = document.createElement('div');
  const description = document.createElement('p');
  description.textContent = String(row.description || row.slug || '');
  description.style.cssText = [
    'display:-webkit-box',
    'min-height:3.8rem',
    'margin:0 0 .45rem',
    'overflow:hidden',
    'color:var(--color-muted)',
    'font-size:.82rem',
    'line-height:1.48',
    '-webkit-box-orient:vertical',
    '-webkit-line-clamp:3',
  ].join(';');
  root.append(description);

  const language = String(row.locale ?? '').toUpperCase() || '—';
  const country = String(row.country ?? '').toUpperCase();
  addCardRow(
    root,
    t('importPage.colLanguage'),
    country && country.toLowerCase() !== language.toLowerCase()
      ? `${language} · ${country}`
      : language,
  );
  addCardRow(root, t('importPage.colVersion'), `v${String(row.latest_version ?? '')}`);
  addCardRow(
    root,
    t('importPage.colDownloads'),
    new Intl.NumberFormat(locale.value).format(Number(row.downloads ?? 0)),
  );
  addCardRow(root, t('importPage.colSize'), formatSize(Number(row.size_bytes ?? 0)));
  return root;
}

function handleBlueprintAction(event: Event): void {
  const detail = (event as CustomEvent<{ actionId: string; row: BlueprintRow }>).detail;
  if (detail.actionId === 'use') void pickFromCloud(detail.row);
}

function wireBlueprintTable(element: BlueprintTableElement | null): void {
  if (!element) return;
  element.labels = dataTableLabels(locale.value);
  element.columnPicker = false;
  element.pageSizeOptions = [];
  element.removeEventListener('rowAction', handleBlueprintAction);
  element.addEventListener('rowAction', handleBlueprintAction);
}

watch(
  blueprintTable,
  (element, previous) => {
    previous?.removeEventListener('rowAction', handleBlueprintAction);
    void nextTick(() => wireBlueprintTable(element));
  },
  { immediate: true },
);

watch(locale, () => wireBlueprintTable(blueprintTable.value));

/**
 * Por qué la lista está vacía. `empty` es la ÚNICA que puede afirmar algo sobre el catálogo: las
 * otras dos hablan de nosotros, no de él.
 *
 * Sin esta distinción, un admin-de-org veía «Todavía no hay plantillas publicadas para tu hub»
 * mientras el owner listaba cuatro (2026-08-03). El empty-state afirmaba un hecho sobre el
 * catálogo que nadie había comprobado — el catálogo ni siquiera se había pedido.
 */
type CatalogState = 'empty' | 'forbidden' | 'unavailable';
const catalogState = ref<CatalogState>('empty');

const catalogEmptyMessage = computed<string>(() => {
  if (catalogState.value === 'forbidden') return t('importPage.catalogForbidden');
  if (catalogState.value === 'unavailable') return t('importPage.catalogUnavailable');
  return t('importPage.catalogEmpty');
});

async function loadCatalog(): Promise<void> {
  loadingCatalog.value = true;
  try {
    catalog.value = await fetchBlueprintCatalog();
    catalogState.value = 'empty'; // se pidió y se recibió: ahora sí podemos hablar del catálogo
  } catch {
    // El catálogo es BEST-EFFORT: un hub sin credencial cloud (Local no enrolado, dev) o un fallo
    // de red NO deben gritar un banner de error — la card «subir desde archivo» siempre es el
    // fallback. Degradamos en silencio a catálogo vacío (la nota «sin plantillas» ya lo cubre).
    // El `error.value` se reserva para fallos de INSPECCIÓN de un fichero elegido por el usuario.
    // Degradar NO es lo mismo que MENTIR: la lista queda vacía y el empty-state dice «no se pudo
    // cargar», no «no hay».
    catalog.value = [];
    catalogState.value = 'unavailable';
  } finally {
    loadingCatalog.value = false;
  }
}

onMounted(() => {
  if (isAdmin.value) {
    void loadCatalog();
  } else {
    // No se pide el catálogo (importar es admin-only), así que no sabemos si hay plantillas.
    catalogState.value = 'forbidden';
  }
});

onBeforeUnmount(() => {
  blueprintTable.value?.removeEventListener('rowAction', handleBlueprintAction);
});

/**
 * Elegir un blueprint de la nube. El runtime lo descarga de Object Storage y **verifica su
 * sha256** antes de entregárnoslo; si no casa, `downloadBlueprint` lanza y no se importa nada.
 * A partir de ahí es el MISMO flujo que un zip local.
 */
async function pickFromCloud(bp: CatalogBlueprint): Promise<void> {
  error.value = '';
  inspecting.value = true;
  activeSource.value = bp.slug;
  try {
    const zip = await downloadBlueprint(bp.slug);
    await inspectAndReview(zip);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    inspecting.value = false;
    activeSource.value = '';
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
    // #267 — avisa al dashboard (y a quien escuche) de que el conjunto de módulos/datos cambió.
    // DashboardPage solo cargaba en onMounted; al reutilizar la instancia, no refrescaba y mostraba
    // los KPIs y widgets PRE-import. Con este evento recarga widgets + actividad.
    window.dispatchEvent(new CustomEvent('erp:modules-changed'));
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
    roles: t('importPage.sectionRoles'),
  };
  return map[section] ?? section;
}

interface ReportRow {
  section: string;
  label: string;
  icon: string;
  color: 'success' | 'medium' | 'warning' | 'danger';
  statusLabel: string;
  reason?: string;
}

// Informe pintado tal cual llega (contrato JSON del motor): Applied ✓ verde · Skipped — gris ·
// Failed ✗ rojo con su motivo. sectionStatusInfo tolera las dos formas serde del enum.
const visual = {
  applied: { icon: 'checkmark-circle-outline', color: 'success', label: () => t('importPage.statusApplied') },
  skipped: { icon: 'remove-circle-outline', color: 'medium', label: () => t('importPage.statusSkipped') },
  // ADR-0195: descartada a propósito (identidades de una plantilla). `warning`, no `medium`: no es
  // un fallo, pero el usuario TIENE que verlo — es la diferencia entre «esta plantilla traía
  // usuarios ajenos y no los he metido» y un «Saltado» gris que nadie lee.
  ignored: { icon: 'shield-checkmark-outline', color: 'warning', label: () => t('importPage.statusIgnored') },
  // hub#405: entró, pero no entera. Mismo escudo y mismo `warning` que un descarte —porque parte
  // de la sección se descartó— con su propia etiqueta: un ✓ verde diría que entró todo, y lo que
  // se quedó fuera es justamente la identidad fiscal de otro negocio.
  partial: { icon: 'shield-checkmark-outline', color: 'warning', label: () => t('importPage.statusPartial') },
  failed: { icon: 'close-circle-outline', color: 'danger', label: () => t('importPage.statusFailed') },
  // hub#409 / ADR-0060: el módulo no se instaló porque el plan exige CONTRATAR una dependencia.
  // `warning` como un descarte —hay que verlo— y nunca el rojo de un fallo: no es una avería, es
  // una decisión de compra del usuario. El carrito lo dice sin leer.
  blocked: { icon: 'cart-outline', color: 'warning', label: () => t('importPage.statusBlocked') },
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

// Los módulos del manifest son la MITAD del trabajo que esta pantalla promete («instala los
// módulos que falten»), así que su resultado va en el informe como una fila más. Antes el motor
// los reportaba en `installed_modules` y el panel los tiraba: con los 13 módulos fallando, el
// informe salía en verde y el usuario volvía a un panel vacío sin saber por qué.
const moduleStatus = {
  installed: 'applied',
  already_installed: 'skipped',
  blocked: 'blocked',
  failed: 'failed',
} as const;

/** «invoice (9,00 €)» — el precio SOLO si el motor lo mandó; nunca se inventa. */
function blockedModuleLabel(id: string, purchase: ModuleInstallPurchase[]): string {
  const offer = purchase.find((p) => p.module_id === id);
  const price = Number(offer?.price);
  if (!offer?.currency || !Number.isFinite(price)) return id;
  return `${id} (${formatAmount(price, { currency: offer.currency })})`;
}

const moduleInstallRows = computed<ReportRow[]>(() =>
  (report.value?.installed_modules ?? []).map((m) => {
    const info = moduleInstallStatusInfo(m);
    const v = visual[moduleStatus[info.kind]];
    return {
      section: `installed_modules/${m.id}`,
      label: m.id,
      icon: v.icon,
      color: v.color,
      statusLabel: v.label(),
      // Un fallo lleva el motivo del motor tal cual —sin él es irreportable—; un bloqueo lleva su
      // frase traducida, que NOMBRA lo que hay que contratar (hub#409): decir «falló» a secas es
      // mandar a diagnosticar una avería que no existe.
      // Sin lista no hay frase: «necesita: .» no nombra nada — la etiqueta del estado ya lo dice.
      reason:
        info.kind === 'blocked'
          ? info.blockedOn.length
            ? t('importPage.reasonBlocked', {
                missing: info.blockedOn.map((id) => blockedModuleLabel(id, info.purchase)).join(', '),
              })
            : undefined
          : info.error,
    };
  }),
);

// hub#331 — el motivo de un descarte nuevo llega como CÓDIGO ESTABLE y la frase la pone aquí,
// traducida (inglés fuente + su `es`), con el número de filas que se quedaron fuera. Un motivo que
// no es un código es prosa de un runtime anterior: se pinta tal cual, nunca se borra.
const discardMessage: Record<SectionDiscardCode, (n: number) => string> = {
  identity_not_portable: (n) => t('importPage.reasonIdentityNotPortable', { n }),
  settings_not_portable: (n) => t('importPage.reasonSettingsNotPortable', { n }),
  roles_not_activatable: (n) => t('importPage.reasonRolesNotActivatable', { n }),
};

/** Frase que acompaña a la fila del informe: la traducción del código, o el motivo tal cual. */
function reportReason(status: { reason?: string }, discardedRows: number): string | undefined {
  const code = sectionDiscardCode(status.reason);
  return code ? discardMessage[code](discardedRows) : status.reason;
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
      reason: reportReason(info, s.discarded_rows ?? 0),
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
/* Encabezado del catálogo + acción secundaria de fichero local. */
.source-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.75rem;
}
.source-heading ion-button {
  flex: 0 0 auto;
  margin: 0;
}
.page-lead-block {
  display: block;
  min-width: 0;
}
.page-lead-block h2 {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0;
}
.page-lead-block p {
  color: var(--ion-color-medium);
  margin: 0.2rem 0 0;
}
ok-data-table {
  display: block;
}
.cloud-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ion-color-medium);
  padding: 1rem 0;
}
.error-note {
  display: block;
  margin-top: 0.75rem;
}
.fail-reason {
  color: var(--ion-color-danger);
}

@media (max-width: 36rem) {
  .source-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .source-heading ion-button {
    align-self: flex-start;
  }
}
</style>
