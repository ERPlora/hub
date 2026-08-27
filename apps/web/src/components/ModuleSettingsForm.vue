<template>
  <div v-if="status === 'loading'" class="flex items-center gap-2 py-8 opacity-70">
    <ion-spinner name="crescent" /> {{ t('moduleSettings.loading') }}
  </div>
  <p v-else-if="status === 'error'" class="text-[color:var(--ion-color-danger)]">
    {{ t('moduleSettings.loadError') }}
  </p>

  <template v-else>
    <!-- Cabecera de la pantalla: `settings.title`, TRADUCIDO (module-system.md §3quater lo
         documentaba como cabecera del formulario; nunca se pintó, y menos aún en el idioma del
         hub). Sin título declarado no se pinta nada: un encabezado inventado por el shell diría
         menos que la propia pestaña. -->
    <h2 v-if="heading" class="settings-heading">{{ heading }}</h2>

    <ion-card>
      <ion-card-content class="p-0">
        <ion-list lines="none">
          <ion-item v-for="field in fields" :key="field.key">
            <HubIcon v-if="settings.icon && field === fields[0]" slot="start" :name="settings.icon" />
            <ion-label>
              <h2>{{ field.label }}</h2>
              <p v-if="field.description">{{ field.description }}</p>
              <!-- El motivo POR CAMPO. El runtime nombra los campos que rechazó (`error.fields`,
                   hub#1094); la frase de cada violación viaja en el mensaje y se pinta arriba. -->
              <p v-if="invalidFields.has(field.key)" class="field-invalid">
                {{ t('moduleSettings.fieldInvalid') }}
              </p>
            </ion-label>

            <!-- boolean → ion-toggle -->
            <ion-toggle
              v-if="field.control === 'toggle'"
              slot="end"
              :aria-label="field.label"
              :aria-invalid="ariaInvalid(field.key)"
              :checked="model[field.key] === true"
              :disabled="!canEdit"
              @ion-change="onToggle(field.key, $event)"
            />

            <!-- string con enum → ion-select -->
            <ion-select
              v-else-if="field.control === 'select'"
              slot="end"
              interface="popover"
              :aria-label="field.label"
              :aria-invalid="ariaInvalid(field.key)"
              :disabled="!canEdit"
              :value="model[field.key]"
              @ion-change="model[field.key] = $event.detail.value"
            >
              <ion-select-option v-for="opt in field.options" :key="String(opt)" :value="opt">
                {{ opt }}
              </ion-select-option>
            </ion-select>

            <!-- integer/number → ion-input type=number -->
            <ion-input
              v-else-if="field.control === 'number'"
              slot="end"
              class="text-right"
              type="number"
              :aria-label="field.label"
              :aria-invalid="ariaInvalid(field.key)"
              :readonly="!canEdit"
              :value="model[field.key] as number | null"
              @ion-input="model[field.key] = toNumber($event.detail.value)"
            />

            <!-- string → ion-input. The placeholder is what makes an EMPTY field visible: without
                 it a bare `slot="end"` input paints nothing (hub#959 — "the fields do not exist"). -->
            <ion-input
              v-else
              slot="end"
              :aria-label="field.label"
              :aria-invalid="ariaInvalid(field.key)"
              :placeholder="t('moduleSettings.textPlaceholder')"
              :readonly="!canEdit"
              :maxlength="field.maxLength"
              :value="(model[field.key] as string | null) ?? ''"
              @ion-input="model[field.key] = $event.detail.value ?? ''"
            />
          </ion-item>
        </ion-list>
      </ion-card-content>
    </ion-card>

    <!-- Por qué NO se pudo guardar. Banner y no (solo) toast: es accionable —hay campos que
         corregir— y tiene que sobrevivir lo bastante para leerse. Antes el `catch` mandaba
         cualquier fallo a un toast genérico y la pantalla se quedaba idéntica tras un 422
         (hub#1094). -->
    <ok-inline-feedback
      v-if="saveRefusal"
      class="save-refusal"
      tone="danger"
      icon="alert-circle-outline"
      :heading="t('moduleSettings.saveError')"
    >
      {{ saveRefusal }}
    </ok-inline-feedback>

    <p v-if="!canEdit" class="text-sm opacity-70 mt-2 px-1">{{ t('moduleSettings.adminOnly') }}</p>

    <ion-button v-if="canEdit" class="mt-3" expand="block" :disabled="saving" @click="save">
      <HubIcon slot="start" name="save-outline" />
      {{ t('moduleSettings.save') }}
    </ion-button>
  </template>
</template>

<script setup lang="ts">
// Renderer GENÉRICO de la pantalla de ajustes de un módulo (settings declarativos estilo widgets).
// Lee el bloque `settings` del module.json: fetchea su JSON Schema, carga la fila singleton con la
// query `get` (mezclando defaults del schema para las claves ausentes) y persiste el snapshot COMPLETO
// con el command `set` (upsert). El shell no conoce módulos concretos: pinta un control por propiedad
// (boolean→toggle, string+enum→select, string→input, integer/number→number input). El escape-hatch
// `settings.component` se maneja en ModuleView (aquí solo llega el caso del form genérico).
//
// hub#1094 — las DOS cosas que esta pantalla no hacía, y que la dejaban inservible en español:
//
//  1. Los rótulos salían del JSON Schema, que es un artefacto en INGLÉS canónico (ADR-0055), y sin
//     `title` caían al nombre de la columna (`warning_time_minutes` → «Warning Time Minutes»). Los
//     módulos llevaban semanas publicando `settings.title` y `settings.fields.<key>.label` en sus
//     `locales/<lang>.json` y el shell no los miraba: la pantalla NO PODÍA estar en español hiciera
//     lo que hiciera el módulo. Ahora manda el locale (ver `lib/module-settings.ts`).
//  2. El guardado se tragaba el 422: el `catch` mandaba cualquier fallo a un toast genérico, así
//     que tras un `invalid_payload` la pantalla se quedaba EXACTAMENTE igual. Ahora el motivo se
//     queda en pantalla y los campos que el runtime nombró (`error.fields`) salen marcados.
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonCard,
  IonCardContent,
  IonList,
  IonItem,
  IonLabel,
  IonToggle,
  IonSelect,
  IonSelectOption,
  IonInput,
  IonButton,
  IonSpinner,
} from '@ionic/vue';
import type { ModuleSettingsDef, SettingsSchema, SettingsSchemaProperty } from '@erplora/module-types';
import { ErploraError, type ErploraClient } from '@erplora/module-sdk';
import HubIcon from './HubIcon.vue';
import { getClient } from '../lib/runtime';
import { isAdmin } from '../lib/session';
import { loadModuleLocale } from '../lib/module-loader';
import { moduleBase } from '../lib/module-url';
import { toastSuccess, toastError } from '../lib/toast';
import {
  settingControl,
  settingValueForControl,
  settingValueForStorage,
  settingsFieldDescription,
  settingsFieldLabel,
  settingsHeading,
  type ModuleSettingControl,
  type ModuleSettingsLocale,
} from '../lib/module-settings';

const props = defineProps<{
  moduleId: string;
  settings: ModuleSettingsDef;
  /** Lo que la barra de la pantalla YA dice (nombre del módulo, localizado). Ver `settingsHeading`. */
  pageTitle?: string;
}>();

const { t, locale } = useI18n();
const client: ErploraClient = getClient();

const status = ref<'loading' | 'ready' | 'error'>('loading');
const saving = ref(false);
// Snapshot editable de los ajustes (clave → valor). Se construye de defaults + fila singleton.
const model = reactive<Record<string, unknown>>({});

// El form solo edita si el usuario es admin (el runtime revalida el command en server; aquí el gate
// es cosmético). Los módulos cuyo command `set` no exija admin seguirían funcionando para todos.
const canEdit = computed(() => isAdmin.value);

/** Un control resuelto a partir de una propiedad del JSON Schema. */
interface Field {
  key: string;
  label: string;
  description?: string;
  control: ModuleSettingControl;
  options?: (string | number)[];
  maxLength?: number;
}

const properties = ref<Record<string, SettingsSchemaProperty>>({});
/** Bloque `settings` de `locales/<lang>.json` del módulo. `undefined` = el módulo no traduce. */
const moduleLocale = ref<ModuleSettingsLocale | undefined>(undefined);

/** Lo que el runtime contestó al último guardado fallido. `null` = no hay negativa pendiente. */
const saveRefusal = ref<string | null>(null);
/** Claves que el runtime nombró en ese rechazo (`error.fields`, hub#1094). */
const invalidFields = ref<Set<string>>(new Set());

/** `aria-invalid` solo cuando de verdad lo está: un `"false"` constante es ruido para el lector. */
function ariaInvalid(key: string): 'true' | undefined {
  return invalidFields.value.has(key) ? 'true' : undefined;
}

/**
 * Cabecera DENTRO del formulario (locale → manifest). `undefined` cuando el módulo no declara
 * título o cuando ese título es el mismo que ya dice la barra: repetirlo no informa de nada.
 */
const heading = computed(() =>
  settingsHeading(moduleLocale.value, props.settings, props.pageTitle),
);

/** Campos a renderizar, en el orden de `properties` del schema. */
const fields = computed<Field[]>(() =>
  Object.entries(properties.value).map(([key, prop]) => ({
    key,
    label: settingsFieldLabel(moduleLocale.value, key, prop),
    description: settingsFieldDescription(moduleLocale.value, key, prop),
    control: settingControl(prop),
    options: prop.enum,
    maxLength: prop.maxLength,
  })),
);

function toNumber(v: string | null | undefined): number | null {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

function onToggle(key: string, e: Event): void {
  model[key] = (e as CustomEvent<{ checked: boolean }>).detail.checked;
}

/** Carga el JSON Schema del paquete del módulo (`/modules/<id>/<settings.schema>`). */
async function loadSchema(): Promise<SettingsSchema> {
  const url = `/modules/${props.moduleId}/${props.settings.schema}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`schema ${res.status}`);
  return (await res.json()) as SettingsSchema;
}

/** Toma la primera fila del resultado de la query `get` (singleton). `null` si no hay fila. */
function firstRow(data: unknown): Record<string, unknown> | null {
  if (Array.isArray(data)) return (data[0] as Record<string, unknown>) ?? null;
  if (data && typeof data === 'object') return data as Record<string, unknown>;
  return null;
}

/**
 * Traducciones del módulo para el idioma ACTIVO. Best-effort: un módulo sin `locales/` (o con el
 * fichero roto) cae a los `title` del schema, que es exactamente el comportamiento anterior — no
 * puede dejar la pantalla sin pintar.
 *
 * También para `en`: el inglés del locale es prosa REDACTADA y el del schema un artefacto técnico,
 * así que el locale gana igual (`kitchen` publica los 16 rótulos en `en` y en `es`).
 *
 * Base SIN versionar, igual que el `loadSchema` de aquí al lado y a diferencia del bundle
 * (hub#935): los dos ficheros que pinta esta pantalla son del mismo paquete y tienen que venir de
 * la misma versión — direccionar uno por versión y el otro no es precisamente cómo se pinta un
 * formulario con los rótulos de una versión y los campos de otra. El runtime marca los assets sin
 * versionar «revalida siempre», y actualizar un módulo recarga la página entera
 * (`reloadForModuleUpdate`), que se lleva esta caché por delante.
 */
async function refreshLocale(): Promise<void> {
  const file = await loadModuleLocale(moduleBase(props.moduleId), locale.value);
  moduleLocale.value = file?.settings;
}

async function boot(): Promise<void> {
  status.value = 'loading';
  saveRefusal.value = null;
  invalidFields.value = new Set();
  try {
    const schema = await loadSchema();
    properties.value = schema.properties ?? {};
    await refreshLocale();

    // Valores actuales (1 fila); si no existe aún, la UI cae a los defaults del schema.
    const current = firstRow(await client.query(props.settings.get).catch(() => null));

    // Construye el snapshot: para cada propiedad, valor de la fila > default del schema > vacío.
    for (const [key, prop] of Object.entries(properties.value)) {
      const fromRow = current ? current[key] : undefined;
      if (fromRow !== undefined && fromRow !== null) {
        model[key] = settingValueForControl(prop, fromRow);
      } else if (prop.default !== undefined) {
        model[key] = settingValueForControl(prop, prop.default);
      } else {
        model[key] = settingControl(prop) === 'toggle' ? false : '';
      }
    }
    status.value = 'ready';
  } catch {
    status.value = 'error';
  }
}

/** Persiste el snapshot COMPLETO (upsert) vía el command `set`. Solo admin (el runtime revalida). */
async function save(): Promise<void> {
  if (!canEdit.value) return;
  saving.value = true;
  saveRefusal.value = null;
  invalidFields.value = new Set();
  try {
    // Snapshot completo: una clave por propiedad del schema (es un upsert, no un patch parcial).
    const snapshot: Record<string, unknown> = {};
    for (const [key, prop] of Object.entries(properties.value)) {
      snapshot[key] = settingValueForStorage(prop, model[key]);
    }
    await client.command(props.settings.set, snapshot);
    await toastSuccess(t('moduleSettings.saved'));
  } catch (e) {
    // Los campos viajan como CAMPO del sobre (`error.fields`), nunca sacados del mensaje a
    // mordiscos: el mensaje es prosa traducible, la lista no. Cuando el runtime nombra campos, la
    // pantalla apunta a ellos; cuando no (permiso, hub caído, un rechazo escrito a mano), se dice
    // lo que contestó el server — que es infinitamente mejor que el genérico de antes.
    const named = e instanceof ErploraError ? (e.fields ?? []) : [];
    invalidFields.value = new Set(named);
    saveRefusal.value = named.length
      ? t('moduleSettings.invalidFields')
      : (e instanceof Error && e.message) || t('moduleSettings.saveError');
    await toastError(t('moduleSettings.saveError'));
  } finally {
    saving.value = false;
  }
}

// El idioma efectivo cambia sin recargar (ADR-0055, hub#781): la pantalla ya montada tiene que
// re-rotularse, o se queda en el idioma que hubiera al abrirla.
watch(locale, () => void refreshLocale());

onMounted(() => void boot());
</script>

<style scoped>
.settings-heading {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0 0 0.5rem;
  padding-inline: 0.25rem;
}

.field-invalid {
  color: var(--ion-color-danger);
}

.save-refusal {
  display: block;
  margin-top: 0.75rem;
}
</style>
