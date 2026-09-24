<template>
  <div class="reset-panel">
    <!-- Aviso de contexto: esto no es «limpiar caché», es borrar el negocio. -->
    <ion-note class="reset-intro">{{ t('settings.resetIntro') }}</ion-note>

    <!-- Red de seguridad de UN clic: el export ya existe y funciona, así que lo irreversible
         deja de serlo si el usuario se lleva un blueprint antes. Va ARRIBA, no escondido. -->
    <ion-button
      fill="outline"
      size="small"
      class="reset-export-first"
      data-testid="reset-export-first"
      @click="$emit('go-export')"
    >
      {{ t('settings.resetExportFirst') }}
    </ion-button>

    <!-- Deshacer una importación: el camino PREFERIDO cuando existe, porque es quirúrgico
         (borra lo que trajo el blueprint y nada más). Va ANTES del reset por secciones. -->
    <template v-if="batches.length">
      <h3 class="reset-subtitle">{{ t('settings.resetImportsTitle') }}</h3>
      <ion-note class="reset-intro">{{ t('settings.resetImportsHint') }}</ion-note>
      <ion-list>
        <ion-item v-for="b in batches" :key="b.id" :data-testid="`reset-batch-${b.id}`">
          <ion-label>
            <strong>{{ b.name }}</strong>
            <div class="reset-row-rows">{{ t('settings.resetRows', { n: b.rows }) }}</div>
          </ion-label>
          <ion-button
            slot="end"
            fill="outline"
            size="small"
            :data-testid="`reset-undo-${b.id}`"
            @click="undo(b.id)"
          >
            {{ t('settings.resetUndo') }}
          </ion-button>
        </ion-item>
      </ion-list>
      <h3 class="reset-subtitle">{{ t('settings.resetSectionsTitle') }}</h3>
    </template>

    <ion-spinner v-if="loading" />

    <ion-list v-else>
      <ion-item v-for="s in visibleSections" :key="s.section" :disabled="!!s.blocked_by">
        <ion-checkbox
          :data-testid="`reset-section-${s.section}`"
          :disabled="!!s.blocked_by"
          :checked="selected.has(s.section)"
          justify="start"
          label-placement="end"
          @ionChange="toggle(s.section)"
        >
          <div class="reset-row">
            <span class="reset-row-name">{{ label(s.section) }}</span>
            <!-- La CIFRA, siempre: un aviso que no dice cuánto se lleva no informa. -->
            <span class="reset-row-rows">{{ t('settings.resetRows', { n: s.rows }) }}</span>
          </div>
        </ion-checkbox>
        <!-- El motivo del bloqueo se lee en pantalla; si no, parece un fallo del producto.
             hub#1291: `color="warning"` rendered Ionic's raw yellow (~1.6:1 on white, under
             WCAG AA); the row is already disabled and the checkbox communicates the block, so
             the note reads `medium` with no separate accent needed. -->
        <ion-note v-if="s.blocked_by" slot="end" color="medium" class="reset-blocked">
          {{ s.blocked_by }}
        </ion-note>
      </ion-item>
    </ion-list>

    <ion-button
      color="danger"
      expand="block"
      class="reset-submit"
      data-testid="reset-submit"
      :disabled="selectable.length === 0"
      @click="submit()"
    >
      {{ t('settings.resetSubmit') }}
    </ion-button>

    <!-- hub#1556: after an undo, the data that kept ONLY the business's own changes (what the
         import replaced did not come back) is said, not left for the business to discover. -->
    <ion-note
      v-if="report?.not_restored?.length"
      class="reset-intro"
      data-testid="reset-undo-not-restored"
    >
      {{ t('settings.resetUndoNotRestored', { areas: tableModules(report.not_restored) }) }}
    </ion-note>

    <!-- Informe final: qué se borró de verdad, por sección. -->
    <ion-list v-if="report" class="reset-report" data-testid="reset-report">
      <ion-item v-for="r in report.sections" :key="r.section">
        <ion-label>
          {{ label(r.section) }} — {{ t('settings.resetDeleted', { n: r.rows_deleted }) }}
        </ion-label>
      </ion-item>
    </ion-list>
  </div>
</template>

<script setup lang="ts">
/**
 * Panel «Restablecer» (Ajustes › Datos, ADR-0170) — el espejo destructivo del export.
 *
 * Reglas de diseño que sostienen los tests (`ResetPanel.test.ts`):
 *  - las cifras salen del PLAN real (dry-run del runtime), nunca de un texto genérico;
 *  - una sección bloqueada (facturas remitidas a la AEAT) no es seleccionable NI se envía;
 *  - confirmar exige teclear el nombre del hub — patrón GitHub, no un «Aceptar» de trámite;
 *  - «exportar antes de borrar» está a un clic: convierte lo irreversible en reversible.
 *
 * La autoridad es SIEMPRE el runtime: revalida el rol owner/admin y vuelve a aplicar el límite
 * fiscal aunque el cliente venga manipulado. Esta UI solo evita el accidente honesto.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonButton,
  IonCheckbox,
  IonItem,
  IonLabel,
  IonList,
  IonNote,
  IonSpinner,
  alertController,
} from '@ionic/vue';
import {
  fetchImportBatches,
  fetchResetPlan,
  listInstalledModules,
  resetHub,
  undoImport,
  type ImportBatch,
  type InstalledModule,
  type ResetPlan,
  type ResetReport,
  type ResetSectionPlan,
} from '../lib/runtime';
import { hubSettings } from '../lib/hub-settings';

defineEmits<{ (e: 'go-export'): void }>();

const { t } = useI18n();

const loading = ref(true);
const sections = ref<ResetSectionPlan[]>([]);
const selected = ref<Set<string>>(new Set());
const report = ref<ResetReport | null>(null);
const batches = ref<ImportBatch[]>([]);
// Id → nombre legible de cada módulo instalado (hub#765): para que `modules/inventory` se lea
// «Inventario» y no el slug interno. Best-effort: si la lista no carga, `label()` cae al slug.
const moduleNames = ref<Map<string, string>>(new Map());

/**
 * Lo que se pinta: secciones CON filas, más las bloqueadas (aunque estén a cero, explican por
 * qué no se pueden tocar). Un hub con muchos módulos instalados devuelve casi todas a cero
 * —en QA real, 23 de 25— y listarlas sería ruido puro: no hay nada que borrar en ellas.
 */
const visibleSections = computed(() =>
  sections.value.filter((s) => s.rows > 0 || s.blocked_by),
);

/** Solo lo que de verdad se puede borrar: lo bloqueado nunca entra en la selección efectiva. */
const selectable = computed(() =>
  sections.value.filter((s) => !s.blocked_by && selected.value.has(s.section)),
);

onMounted(async () => {
  try {
    const plan: ResetPlan = await fetchResetPlan();
    sections.value = plan.sections;
    // Las importaciones son informativas: si fallan, el reset por secciones sigue disponible.
    batches.value = await fetchImportBatches().catch(() => []);
    // Nombres legibles de los módulos (hub#765): para traducir `modules/<id>` en `label()`.
    // Best-effort: si la lista no carga, el slug sigue siendo legible como fallback.
    const installed = await listInstalledModules().catch(() => [] as InstalledModule[]);
    moduleNames.value = new Map(installed.map((m) => [m.id, m.name]));
  } finally {
    loading.value = false;
  }
});

/**
 * Deshace una importación. La fricción es DELIBERADAMENTE menor que la del reset por secciones:
 * esto solo quita lo que trajo ese blueprint y se puede volver a importar, así que pedir el
 * nombre del hub sería desproporcionado. Sí se avisa de cuántas filas se van.
 */
async function undo(batchId: string): Promise<void> {
  const batch = batches.value.find((b) => b.id === batchId);
  if (!batch) return;
  // hub#1556: if the business edited what this import brought (one day of the hours, say), what
  // the import replaced cannot come back on top of its changes — undoing leaves ONLY its own rows
  // there. That is said here, before confirming, not discovered afterwards.
  const edited = batch.edited_after_import ?? [];
  const message = edited.length
    ? `${t('settings.resetUndoBody', { n: batch.rows })}\n${t('settings.resetUndoEdited', { areas: tableModules(edited) })}`
    : t('settings.resetUndoBody', { n: batch.rows });
  const alert = await alertController.create({
    header: t('settings.resetUndoTitle', { name: batch.name }),
    message,
    buttons: [
      { text: t('settings.resetCancel'), role: 'cancel' },
      { text: t('settings.resetUndo'), role: 'confirm', cssClass: 'alert-button-danger' },
    ],
  });
  await alert.present();
  const { role } = await alert.onDidDismiss();
  if (role !== 'confirm') return;

  report.value = await undoImport(batchId);
  // Refrescar ambos: el lote desaparece y las cifras del plan cambian.
  batches.value = await fetchImportBatches().catch(() => []);
  sections.value = (await fetchResetPlan()).sections;
}

/**
 * Nombre legible de una sección. Una sección de módulo (`modules/inventory`) prefiere el NOMBRE
 * humano del módulo (hub#765): el slug es un identificador de desarrollador y no le dice nada al
 * dueño que está decidiendo qué borrar. Si el módulo no está en la lista de instalados (datos
 * huérfanos tras desinstalar), cae al slug — algo legible, nunca en blanco.
 */
function label(section: string): string {
  if (section.startsWith('modules/')) {
    const id = section.slice('modules/'.length);
    return moduleNames.value.get(id) ?? id;
  }
  return t(`settings.reset_${section}`);
}

/**
 * Human names of the modules that own some tables (hub#1556). A module's tables are prefixed with
 * its id (`schedules_business_hours` → `schedules`); the longest matching installed id wins, and a
 * table no installed module claims falls back to its own name — readable, never blank.
 */
function tableModules(tables: string[]): string {
  const names = tables.map((table) => {
    let best = '';
    for (const id of moduleNames.value.keys()) {
      if ((table === id || table.startsWith(`${id}_`)) && id.length > best.length) best = id;
    }
    return best ? (moduleNames.value.get(best) ?? best) : table;
  });
  return [...new Set(names)].join(', ');
}

function toggle(section: string): void {
  const next = new Set(selected.value);
  if (next.has(section)) next.delete(section);
  else next.add(section);
  selected.value = next;
}

/** Traduce la selección de la UI al contrato del runtime. */
function buildSelection() {
  const ids = selectable.value.map((s) => s.section);
  return {
    settings: ids.includes('hub_settings'),
    users: ids.includes('hub_users'),
    media: ids.includes('media'),
    fiscal: ids.includes('fiscal'),
    // hub#417 — el juego de roles del hub (`hub_role_activation`): sección propia, nunca un efecto
    // colateral de otra. Encender un rol lo hace asignable a una persona, así que apagarlo se marca
    // a la vista de su cifra, igual que el resto.
    roles: ids.includes('roles'),
    modules: ids.filter((s) => s.startsWith('modules/')).map((s) => s.slice('modules/'.length)),
  };
}

/**
 * Confirma y ejecuta. La confirmación es DELIBERADAMENTE incómoda: enseña el desglose con cifras
 * y pide teclear el nombre del hub. Es la última puerta antes de algo que no se deshace.
 */
async function submit(): Promise<void> {
  const targets = selectable.value;
  if (!targets.length) return; // nada seleccionable → ni se pregunta

  const hubName = hubSettings.value?.business_legal_name?.trim() || '';
  const desglose = targets.map((s) => `· ${label(s.section)}: ${s.rows}`).join('\n');
  const total = targets.reduce((acc, s) => acc + s.rows, 0);

  const alert = await alertController.create({
    header: t('settings.resetConfirmTitle'),
    message: `${t('settings.resetConfirmBody', { total })}\n${desglose}`,
    inputs: [
      {
        name: 'name',
        type: 'text',
        // El placeholder LLEVA el nombre: hay que copiarlo a conciencia, no adivinarlo.
        placeholder: hubName || t('settings.resetConfirmPlaceholder'),
      },
    ],
    buttons: [
      { text: t('settings.resetCancel'), role: 'cancel' },
      { text: t('settings.resetConfirm'), role: 'confirm', cssClass: 'alert-button-danger' },
    ],
  });
  await alert.present();
  const { role, data } = await alert.onDidDismiss();
  if (role !== 'confirm') return;

  // El nombre tecleado debe coincidir: un «Aceptar» de trámite no basta para esto.
  const typed = String(data?.values?.name ?? '').trim();
  if (!hubName || typed !== hubName) return;

  report.value = await resetHub(buildSelection());
  // Re-leer el plan: las cifras que quedan tras borrar son las nuevas, no las de antes.
  sections.value = (await fetchResetPlan()).sections;
  selected.value = new Set();
}

// Superficie que los tests ejercen directamente (el DOM de ion-* va stubeado en shallow mount).
defineExpose({ toggle, submit, undo });
</script>

<style scoped>
.reset-intro {
  display: block;
  margin-bottom: 0.75rem;
}
.reset-export-first {
  margin-bottom: 1rem;
}
.reset-row {
  display: flex;
  flex-direction: column;
}
.reset-row-rows {
  font-size: 0.85em;
  opacity: 0.7;
}
.reset-blocked {
  font-size: 0.75em;
  max-width: 45%;
  white-space: normal;
  text-align: right;
}
.reset-subtitle {
  margin: 1.25rem 0 0.35rem;
  font-size: 0.95rem;
  font-weight: 600;
}
.reset-submit {
  margin-top: 1rem;
}
</style>
