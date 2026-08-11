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
          mode="md"
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

    <!-- ── Para qué es este bundle (ADR-0195) ──
         No es un detalle: decide si el zip puede llevar identidades y datos fiscales. Una
         plantilla se publica y la descarga cualquiera; una copia es privada y del mismo dueño. -->
    <h2 class="section-title">{{ t('exportPage.purposeTitle') }}</h2>
    <ion-card>
      <ion-card-content class="p-0">
        <ion-list lines="none">
          <ion-item>
            <ion-radio-group v-model="purpose" data-testid="export-purpose">
              <ion-item>
                <ion-radio value="backup" justify="start" label-placement="end" alignment="start">
                  <h2 class="cb-title">{{ t('exportPage.purposeBackup') }}</h2>
                  <p class="cb-desc">{{ t('exportPage.purposeBackupDesc') }}</p>
                </ion-radio>
              </ion-item>
              <ion-item>
                <ion-radio value="template" justify="start" label-placement="end" alignment="start">
                  <h2 class="cb-title">{{ t('exportPage.purposeTemplate') }}</h2>
                  <p class="cb-desc">{{ t('exportPage.purposeTemplateDesc') }}</p>
                </ion-radio>
              </ion-item>
            </ion-radio-group>
          </ion-item>
        </ion-list>
      </ion-card-content>
    </ion-card>

    <!-- ── Secciones del hub ── -->
    <h2 class="section-title">{{ t('exportPage.sections') }}</h2>
    <ion-card>
      <ion-card-content class="p-0">
        <ion-list lines="none">
          <!-- Ionic 8: la label la pone el PROPIO checkbox (label-placement/justify), no un
               ion-label hermano — así el texto es clicable y ES el nombre accesible del input
               (sin aria-label duplicado que mantener en sync con el i18n).
               alignment=start alinea la casilla con la 1ª línea cuando la label es multilínea. -->

          <!-- Usuarios: empleados + roles + permisos (data/hub_users.sql). -->
          <ion-item v-if="!esPlantilla">
            <ion-checkbox
              data-testid="export-section-users"
              v-model="selUsers"
              justify="start"
              label-placement="end"
              alignment="start"
            >
              <h2 class="cb-title">{{ t('exportPage.sectionUsers') }}</h2>
              <p class="cb-desc">{{ t('exportPage.sectionUsersDesc') }}</p>
            </ion-checkbox>
          </ion-item>

          <!-- Ajustes del hub (data/hub_settings.sql). La subselección ítem a ítem
               (ExportSelection.settings_items) requiere un endpoint que enumere los settings
               presentes — aún no existe. TODO(ADR-0113): desglosar ítem a ítem cuando el runtime
               exponga la lista; hasta entonces checkbox simple = `settings_items: null`.
               ⚠️ `null` NO significa «todos pase lo que pase» (ADR-0195 §4, hub#405): con
               `purpose: template` el RUNTIME filtra a las claves de configuración
               (`export::PORTABLE_SETTING_KEYS`) y el NIF, la razón social y la dirección no entran
               en el zip. El control está en el motor a propósito — una casilla no es un control, y
               este `null` sale del formulario. -->
          <ion-item>
            <ion-checkbox
              data-testid="export-section-settings"
              v-model="selSettings"
              justify="start"
              label-placement="end"
              alignment="start"
            >
              <h2 class="cb-title">{{ t('exportPage.sectionSettings') }}</h2>
              <!-- La descripción NO puede prometer lo mismo en los dos casos: en una plantilla la
                   identidad de negocio se queda fuera (hub#405), y decir «incluye la identidad»
                   sería exactamente la promesa que el motor incumple. -->
              <p class="cb-desc">
                {{ esPlantilla ? t('exportPage.sectionSettingsDescTemplate') : t('exportPage.sectionSettingsDesc') }}
              </p>
            </ion-checkbox>
          </ion-item>

          <!-- Fiscal: OFF por defecto. Incluye config VeriFactu + certificado .p12 (viaja tal
               cual, protegido solo por su propia contraseña — decisión (d) del doc). -->
          <ion-item v-if="!esPlantilla">
            <ion-checkbox
              data-testid="export-section-fiscal"
              v-model="selFiscal"
              justify="start"
              label-placement="end"
              alignment="start"
            >
              <h2 class="cb-title">{{ t('exportPage.sectionFiscal') }}</h2>
              <p class="cb-desc">{{ t('exportPage.sectionFiscalDesc') }}</p>
              <ion-note data-testid="export-fiscal-note" color="warning" class="fiscal-note">
                <HubIcon name="warning-outline" class="fiscal-note-icon" />
                {{ t('exportPage.fiscalWarning') }}
              </ion-note>
            </ion-checkbox>
          </ion-item>

          <!-- Imágenes/media (carpeta media del hub, dentro del zip — sin depender del S3). -->
          <ion-item>
            <ion-checkbox
              data-testid="export-section-media"
              v-model="selMedia"
              justify="start"
              label-placement="end"
              alignment="start"
            >
              <h2 class="cb-title">{{ t('exportPage.sectionMedia') }}</h2>
              <p class="cb-desc">{{ t('exportPage.sectionMediaDesc') }}</p>
            </ion-checkbox>
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

    <!-- ── Casillas por TABLA (hub#534): lo que el operador NO quiere publicar ──
         Con el recuento al lado, porque es lo que convierte la lista en una decisión: «Citas: 28»
         es lo que hace que se desmarquen. Solo de los módulos que van CON datos — de los demás no
         hay nada que elegir. Es herramienta del operador, no un control: la garantía de una
         plantilla oficial es la revisión con el contenido a la vista (saas#1257). -->
    <template v-for="row in rows" :key="`tables-${row.id}`">
      <ion-card v-if="row.include && row.withData && tablesOf(row.id).length" class="tables-card">
        <ion-card-content>
          <h3 class="font-semibold mb-1">{{ row.name }}</h3>
          <ion-list lines="none">
            <ion-item v-for="tc in tablesOf(row.id)" :key="tc.table">
              <ion-checkbox
                :checked="isTableSelected(row.id, tc.table)"
                :data-testid="`export-table-${tc.table}`"
                @ion-change="toggleTable(row.id, tc.table)"
              >
                {{ tc.table }} · {{ tc.rows }}
              </ion-checkbox>
            </ion-item>
          </ion-list>
        </ion-card-content>
      </ion-card>
    </template>

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
  IonRadio,
  IonRadioGroup,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import { isAdmin } from '../lib/session';
import { availableLocales } from '../i18n';
import { toastSuccess } from '../lib/toast';
import { SaveDownloadError, saveDownload, saveDownloadMessageKey } from '../lib/save-download';
import {
  listInstalledModules,
  fetchExportTables,
  type ExportModuleTables,
  type ExportTableCount,
  exportHub,
  type BundlePurpose,
  type ExportSelection,
} from '../lib/runtime';

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
// ADR-0195: para qué es este bundle. `backup` por defecto — es lo conservador: restaurar una
// copia SIN identidades perdería roles y PINs. Al pasar a `template`, el motor excluye
// identidades y fiscal del zip, así que la UI deja de ofrecer esas casillas (una casilla que el
// motor va a ignorar es una mentira).
const purpose = ref<BundlePurpose>('backup');
const esPlantilla = computed(() => purpose.value === 'template');

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

// Labels del locale activo por PROPIEDAD (gotcha OutfitKit: default inglés).
watch(modulesTable, (el) => {
  if (el) (el as HTMLElement & { labels: Record<string, string> }).labels = dataTableLabels(locale.value);
});
watch(locale, () => {
  if (modulesTable.value) {
    (modulesTable.value as HTMLElement & { labels: Record<string, string> }).labels =
      dataTableLabels(locale.value);
  }
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
  // Las tablas de cada módulo con su recuento (hub#534). Va aparte y DEGRADA EN SILENCIO: si el
  // runtime no lo sirve, el formulario sigue exportando todo, que es lo que hacía antes.
  moduleTables.value = await fetchExportTables();
});

// ── Casillas por TABLA (hub#534) ─────────────────────────────────────────────────────────────
//
// Herramienta del OPERADOR, no un control de seguridad: sirve para no publicar las 25-28 citas
// pasadas o los ajustes de agenda del salón de origen sin tocar código. La garantía de una
// plantilla oficial es que la hacemos nosotros y la revisamos VIENDO su contenido (saas#1257).
const moduleTables = ref<ExportModuleTables[]>([]);
/** Tablas que el operador ha DESMARCADO, por módulo. Vacío = todas (el default de siempre). */
const excluded = ref<Record<string, string[]>>({});

/** Las tablas de un módulo, con su recuento, en el orden que manda el runtime (por volumen). */
function tablesOf(moduleId: string): ExportTableCount[] {
  return moduleTables.value.find((m) => m.module_id === moduleId)?.tables ?? [];
}

function isTableSelected(moduleId: string, table: string): boolean {
  return !(excluded.value[moduleId] ?? []).includes(table);
}

function toggleTable(moduleId: string, table: string): void {
  const off = excluded.value[moduleId] ?? [];
  excluded.value = {
    ...excluded.value,
    [moduleId]: off.includes(table) ? off.filter((t) => t !== table) : [...off, table],
  };
}

/**
 * Qué tablas se mandan para un módulo. `null` = todas — y es importante que sea `null` y no la
 * lista entera: el campo es una ADICIÓN, y mandar la lista completa convertiría cada tabla nueva de
 * un módulo en una tabla que el formulario deja fuera sin que nadie lo haya decidido.
 */
function tablesFor(moduleId: string): string[] | null {
  const off = excluded.value[moduleId] ?? [];
  if (!off.length) return null;
  return tablesOf(moduleId)
    .map((t) => t.table)
    .filter((t) => !off.includes(t));
}

// ── Exportar: POST → blob → descarga con el filename del Content-Disposition (o el default) ──
const exporting = ref<boolean>(false);
const error = ref<string>('');

async function doExport(): Promise<void> {
  if (!isAdmin.value || exporting.value) return; // defensa: el botón ya está disabled
  error.value = '';
  exporting.value = true;
  try {
    const selection: ExportSelection = {
      users: esPlantilla.value ? false : selUsers.value,
      settings: selSettings.value,
      // TODO(ADR-0113): subselección ítem a ítem cuando el runtime enumere los settings.
      settings_items: null,
      // En una plantilla no se mandan aunque el estado local los tuviera a true: el motor los
      // ignora igualmente (ADR-0195), y mandar `true` daría a entender que viajan.
      fiscal: esPlantilla.value ? false : selFiscal.value,
      media: selMedia.value,
      modules: rows.value
        .filter((r) => r.include)
        .map((r) => ({
          module_id: r.id,
          with_data: r.withData,
          tables: r.withData ? tablesFor(r.id) : null,
        })),
      purpose: purpose.value,
    };
    const { blob, filename } = await exportHub(
      name.value.trim() || 'hub',
      exportLocale.value,
      selection,
    );
    // Dónde acaba el zip NO es igual en las tres superficies (hub#480): en un navegador lo coge su
    // gestor de descargas; dentro de la app instalada no hay gestor ninguno, así que lo guarda el
    // shell y devuelve la RUTA — que es lo único que le dice al usuario que su copia existe.
    const savedTo = await saveDownload(filename, blob);
    await toastSuccess(
      savedTo ? t('download.savedTo', { path: savedTo }) : t('exportPage.done', { filename }),
    );
  } catch (e) {
    // Dos fallos distintos con la misma salida. El del EXPORT trae el mensaje HONESTO del server
    // (exportHub ya extrajo el envelope/texto) y se conserva tal cual. El de la DESCARGA no es una
    // frase — `save_download_failed: hub.zip` no le dice nada a nadie —, así que se traduce.
    //
    // El TIMEOUT va aparte (hub#765): sin deadline, un runtime colgado dejaba el spinner infinito.
    // Ahora el fetch aborta, pero «export → timeout» no es una frase que el usuario pueda accionar:
    // hay que decirle que el servidor no respondió a tiempo y que puede reintentar.
    if (e instanceof SaveDownloadError) {
      error.value = t(saveDownloadMessageKey(e));
    } else if (e instanceof Error && e.message === 'export → timeout') {
      error.value = t('exportPage.timeout');
    } else {
      error.value = e instanceof Error ? e.message : String(e);
    }
  } finally {
    exporting.value = false;
  }
}

// Expuesto para los tests del panel (misma superficie que `doExport`).
defineExpose({ doExport, tablesOf, toggleTable, rows });
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
