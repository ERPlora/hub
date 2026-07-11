<template>
  <section>
    <p class="page-lead" data-testid="export-lead">{{ t('exportPage.lead') }}</p>
    <p v-if="!isAdmin" class="page-lead admin-note">{{ t('exportPage.adminOnly') }}</p>

    <!-- ── Nombre + idioma del blueprint ── -->
    <!-- El nombre pre-rellena el default editable del fichero: `<nombre>_<idioma>.blueprint.zip`.
         El manifest es la fuente de verdad (a prueba de renombres del zip). -->
    <ion-card>
      <ion-card-content>
        <ion-input
          data-testid="export-name"
          fill="outline"
          label-placement="floating"
          :label="t('exportPage.name')"
          v-model="name"
        />
        <ion-item lines="none" class="mt-2">
          <HubIcon slot="start" name="language-outline" />
          <ion-label>{{ t('exportPage.language') }}</ion-label>
          <ion-select
            data-testid="export-locale"
            v-model="exportLocale"
            interface="popover"
            :aria-label="t('exportPage.language')"
            slot="end"
          >
            <ion-select-option v-for="l in availableLocales" :key="l.code" :value="l.code">
              {{ l.name }}
            </ion-select-option>
          </ion-select>
        </ion-item>
        <ion-note class="filename-preview">{{ filenamePreview }}</ion-note>
      </ion-card-content>
    </ion-card>

    <!-- ── Secciones del hub ── -->
    <h2 class="section-title">{{ t('exportPage.sections') }}</h2>
    <ion-card>
      <ion-card-content class="p-0">
        <ion-list lines="none">
          <!-- Usuarios: empleados + roles + permisos (data/hub_users.sql). -->
          <ion-item>
            <ion-checkbox
              data-testid="export-section-users"
              slot="start"
              v-model="selUsers"
              :aria-label="t('exportPage.sectionUsers')"
            />
            <ion-label>
              <h2>{{ t('exportPage.sectionUsers') }}</h2>
              <p>{{ t('exportPage.sectionUsersDesc') }}</p>
            </ion-label>
          </ion-item>

          <!-- Ajustes del hub (data/hub_settings.sql). La subselección ítem a ítem
               (ExportSelection.settings_items) requiere un endpoint que enumere los settings
               presentes — aún no existe. TODO(ADR-0113): desglosar ítem a ítem cuando el runtime
               exponga la lista; hasta entonces checkbox simple = todos (settings_items: null). -->
          <ion-item>
            <ion-checkbox
              data-testid="export-section-settings"
              slot="start"
              v-model="selSettings"
              :aria-label="t('exportPage.sectionSettings')"
            />
            <ion-label>
              <h2>{{ t('exportPage.sectionSettings') }}</h2>
              <p>{{ t('exportPage.sectionSettingsDesc') }}</p>
            </ion-label>
          </ion-item>

          <!-- Fiscal: OFF por defecto. Incluye config VeriFactu + certificado .p12 (viaja tal
               cual, protegido solo por su propia contraseña — decisión (d) del doc). -->
          <ion-item>
            <ion-checkbox
              data-testid="export-section-fiscal"
              slot="start"
              v-model="selFiscal"
              :aria-label="t('exportPage.sectionFiscal')"
            />
            <ion-label class="ion-text-wrap">
              <h2>{{ t('exportPage.sectionFiscal') }}</h2>
              <p>{{ t('exportPage.sectionFiscalDesc') }}</p>
              <ion-note data-testid="export-fiscal-note" color="warning" class="fiscal-note">
                <HubIcon name="warning-outline" class="fiscal-note-icon" />
                {{ t('exportPage.fiscalWarning') }}
              </ion-note>
            </ion-label>
          </ion-item>

          <!-- Imágenes/media (carpeta media del hub, dentro del zip — sin depender del S3). -->
          <ion-item>
            <ion-checkbox
              data-testid="export-section-media"
              slot="start"
              v-model="selMedia"
              :aria-label="t('exportPage.sectionMedia')"
            />
            <ion-label>
              <h2>{{ t('exportPage.sectionMedia') }}</h2>
              <p>{{ t('exportPage.sectionMediaDesc') }}</p>
            </ion-label>
          </ion-item>
        </ion-list>
      </ion-card-content>
    </ion-card>

    <!-- ── Módulos instalados: fila por módulo con checkbox «módulo» + checkbox «datos» ── -->
    <div class="modules-head">
      <h2 class="section-title">{{ t('exportPage.modules') }}</h2>
      <ion-button
        data-testid="export-select-all"
        size="small"
        fill="outline"
        :disabled="rows.length === 0"
        @click="toggleAll"
      >
        {{ allSelected ? t('exportPage.deselectAll') : t('exportPage.selectAll') }}
      </ion-button>
    </div>
    <p class="page-lead">{{ t('exportPage.modulesLead') }}</p>

    <ion-item v-if="loadingModules" lines="none">
      <ion-spinner slot="start" name="crescent" />
      <ion-label>{{ t('exportPage.loadingModules') }}</ion-label>
    </ion-item>
    <!-- Checkbox «datos» deshabilitado si «módulo» está desmarcado: un módulo fuera del blueprint
         no puede llevar datos. Módulo marcado sin datos → solo se registra para instalar. -->
    <ok-data-table
      v-show="!loadingModules"
      ref="modulesTable"
      data-testid="export-modules-table"
      :columns="moduleColumns"
      :rows="rows"
      row-key="id"
    ></ok-data-table>

    <!-- ── Exportar ── -->
    <!-- Error HONESTO del server (readErrorMessage), nunca un genérico si el runtime dijo algo. -->
    <ion-note v-if="error" data-testid="export-error" color="danger" class="error-note">
      {{ t('exportPage.errorTitle') }}: {{ error }}
    </ion-note>

    <ion-button
      data-testid="export-submit"
      class="mt-3"
      expand="block"
      :disabled="!isAdmin || exporting"
      @click="doExport"
    >
      <ion-spinner v-if="exporting" slot="start" name="crescent" />
      <HubIcon v-else slot="start" name="download-outline" />
      {{ exporting ? t('exportPage.exporting') : t('exportPage.export') }}
    </ion-button>
  </section>
</template>

<script setup lang="ts">
// Panel CORE «Exportar configuración» (ADR-0113 §4, architecture/hub/export-import.md).
// Vive en la pestaña Datos de Ajustes (/settings?tab=data) junto al panel de import — decisión
// del humano 2026-07-12 (antes era la página /export). Empaqueta el estado del hub en un
// `<nombre>_<idioma>.blueprint.zip` descargable: secciones del hub (usuarios/ajustes/fiscal/media)
// + selección dinámica por módulo instalado (registrar el módulo y, opcionalmente, sus datos).
// El gate real es del runtime (solo owner/admin); aquí el `:disabled` es cosmético, como en
// el resto de SettingsPage.
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonCard,
  IonCardContent,
  IonList,
  IonItem,
  IonLabel,
  IonNote,
  IonInput,
  IonSelect,
  IonSelectOption,
  IonCheckbox,
  IonButton,
  IonSpinner,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { DT_LABELS_ES } from '../lib/data-table-labels';
import { isAdmin } from '../lib/session';
import { availableLocales } from '../i18n';
import { toastSuccess } from '../lib/toast';
import { listInstalledModules, exportHub, type ExportSelection } from '../lib/runtime';

const { t, locale } = useI18n();

// ── Nombre + idioma del blueprint ──
const name = ref<string>('hub');
// Default = locale actual del shell; el usuario puede exportar en otro idioma.
const exportLocale = ref<string>(String(locale.value));

/** Vista previa del nombre final del fichero (default editable, el manifest manda). */
const filenamePreview = computed<string>(
  () => `${(name.value.trim() || 'hub')}_${exportLocale.value}.blueprint.zip`,
);

// ── Secciones (usuarios/ajustes ON; fiscal OFF por defecto — incluye el .p12; media ON) ──
const selUsers = ref<boolean>(true);
const selSettings = ref<boolean>(true);
const selFiscal = ref<boolean>(false);
const selMedia = ref<boolean>(true);

// ── Módulos instalados (fila = módulo; checkbox «módulo» + checkbox «datos») ──
interface ModuleRow extends Record<string, unknown> {
  id: string;
  name: string;
  version: string;
  /** Registrar el módulo en el blueprint (se instalará al importar). */
  include: boolean;
  /** Volcar además sus datos (`data/<id>.sql`). Solo tiene sentido con `include`. */
  withData: boolean;
}

// ok-data-table: columnas con render() imperativo (OutfitKit no emite .d.ts — tipos locales,
// mismo patrón que DashboardPage).
type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  render?: (row: Row) => Node | string;
}

const rows = ref<ModuleRow[]>([]);
const loadingModules = ref<boolean>(true);
const modulesTable = ref<HTMLElement | null>(null);

// Labels ES de la tabla por PROPIEDAD (gotcha OutfitKit: default inglés).
watch(modulesTable, (el) => {
  if (el) (el as HTMLElement & { labels: typeof DT_LABELS_ES }).labels = DT_LABELS_ES;
});

/** Sustituye una fila por id (array NUEVO: la prop `rows` de la tabla re-renderiza por asignación). */
function patchRow(id: string, patch: Partial<ModuleRow>): void {
  rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r));
}

/**
 * Celda checkbox (ion-checkbox imperativo: los render() de ok-data-table viven en su shadow, no
 * en el template Vue). Desmarcar «módulo» arrastra «datos» a off y lo deshabilita.
 */
function checkboxCell(row: Row, key: 'include' | 'withData'): Node {
  const cb = document.createElement('ion-checkbox') as HTMLElement & {
    checked: boolean;
    disabled: boolean;
  };
  cb.checked = Boolean(row[key]);
  cb.disabled = key === 'withData' && !row.include;
  cb.setAttribute(
    'aria-label',
    t(key === 'include' ? 'exportPage.includeOf' : 'exportPage.dataOf', {
      module: String(row.name),
    }),
  );
  cb.addEventListener('ionChange', (e) => {
    const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
    if (key === 'include') {
      patchRow(String(row.id), checked ? { include: true } : { include: false, withData: false });
    } else {
      patchRow(String(row.id), { withData: checked });
    }
  });
  return cb;
}

// Headers con t() → computed para que reaccionen al cambio de idioma del shell.
const moduleColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('exportPage.colModule') },
  { key: 'version', header: t('exportPage.colVersion') },
  { key: 'include', header: t('exportPage.colInclude'), align: 'center', render: (r) => checkboxCell(r, 'include') },
  { key: 'withData', header: t('exportPage.colData'), align: 'center', render: (r) => checkboxCell(r, 'withData') },
]);

/** «Seleccionar todo» ya aplicado: todas las filas con módulo + datos marcados. */
const allSelected = computed<boolean>(
  () => rows.value.length > 0 && rows.value.every((r) => r.include && r.withData),
);

/** Botón «Seleccionar todo»: marca módulo+datos de todas las filas (o lo deshace si ya está todo). */
function toggleAll(): void {
  const next = !allSelected.value;
  rows.value = rows.value.map((r) => ({ ...r, include: next, withData: next }));
}

onMounted(async () => {
  try {
    // Fuente de verdad local: lo instalado según el runtime (no el catálogo Cloud).
    const installed = await listInstalledModules();
    rows.value = installed.map((m) => ({
      id: m.id,
      name: m.name,
      version: m.version,
      include: true, // por defecto el blueprint registra todo lo instalado…
      withData: false, // …sin datos (los datos son opt-in por fila)
    }));
  } catch {
    rows.value = []; // runtime sin responder → tabla vacía (su empty-state lo dice)
  } finally {
    loadingModules.value = false;
  }
});

// ── Exportar: POST → blob → descarga con el filename del Content-Disposition (o el default) ──
const exporting = ref<boolean>(false);
const error = ref<string>('');

async function doExport(): Promise<void> {
  if (!isAdmin.value || exporting.value) return; // defensa: el botón ya está disabled
  error.value = '';
  exporting.value = true;
  try {
    const selection: ExportSelection = {
      users: selUsers.value,
      settings: selSettings.value,
      // TODO(ADR-0113): subselección ítem a ítem cuando el runtime enumere los settings.
      settings_items: null,
      fiscal: selFiscal.value,
      media: selMedia.value,
      modules: rows.value
        .filter((r) => r.include)
        .map((r) => ({ module_id: r.id, with_data: r.withData })),
    };
    const { blob, filename } = await exportHub(
      name.value.trim() || 'hub',
      exportLocale.value,
      selection,
    );
    // Descarga del zip como blob → link temporal con download=<filename>.
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    await toastSuccess(t('exportPage.done', { filename }));
  } catch (e) {
    // Mensaje HONESTO del server (exportHub ya extrajo el envelope/texto), no un genérico.
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    exporting.value = false;
  }
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
.filename-preview {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.8rem;
}
.modules-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.fiscal-note {
  display: flex;
  align-items: flex-start;
  gap: 0.35rem;
  margin-top: 0.25rem;
  font-size: 0.8rem;
}
.fiscal-note-icon {
  flex: none;
  margin-top: 0.1rem;
}
.error-note {
  display: block;
  margin-top: 0.75rem;
}
</style>
