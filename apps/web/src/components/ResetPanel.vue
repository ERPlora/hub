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

    <ion-spinner v-if="loading" />

    <ion-list v-else>
      <ion-item v-for="s in sections" :key="s.section" :disabled="!!s.blocked_by">
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
        <!-- El motivo del bloqueo se lee en pantalla; si no, parece un fallo del producto. -->
        <ion-note v-if="s.blocked_by" slot="end" color="warning" class="reset-blocked">
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
  fetchResetPlan,
  resetHub,
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

/** Solo lo que de verdad se puede borrar: lo bloqueado nunca entra en la selección efectiva. */
const selectable = computed(() =>
  sections.value.filter((s) => !s.blocked_by && selected.value.has(s.section)),
);

onMounted(async () => {
  try {
    const plan: ResetPlan = await fetchResetPlan();
    sections.value = plan.sections;
  } finally {
    loading.value = false;
  }
});

/** Nombre legible de una sección (`modules/inventory` → «inventory»). */
function label(section: string): string {
  return section.startsWith('modules/') ? section.slice('modules/'.length) : t(`settings.reset_${section}`);
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
defineExpose({ toggle, submit });
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
.reset-submit {
  margin-top: 1rem;
}
</style>
