<template>
  <div v-if="status === 'loading'" class="flex items-center gap-2 py-8 opacity-70">
    <ion-spinner name="crescent" /> {{ t('moduleSettings.loading') }}
  </div>
  <p v-else-if="status === 'error'" class="text-[color:var(--ion-color-danger)]">
    {{ t('moduleSettings.loadError') }}
  </p>

  <template v-else>
    <ion-card>
      <ion-card-content class="p-0">
        <ion-list lines="none">
          <ion-item v-for="field in fields" :key="field.key">
            <HubIcon v-if="settings.icon && field === fields[0]" slot="start" :name="settings.icon" />
            <ion-label>
              <h2>{{ field.label }}</h2>
              <p v-if="field.description">{{ field.description }}</p>
            </ion-label>

            <!-- boolean → ion-toggle -->
            <ion-toggle
              v-if="field.control === 'toggle'"
              slot="end"
              :aria-label="field.label"
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
import { computed, onMounted, reactive, ref } from 'vue';
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
import type { ErploraClient } from '@erplora/module-sdk';
import HubIcon from './HubIcon.vue';
import { getClient } from '../lib/runtime';
import { isAdmin } from '../lib/session';
import { toastSuccess, toastError } from '../lib/toast';
import {
  settingControl,
  settingValueForControl,
  settingValueForStorage,
  type ModuleSettingControl,
} from '../lib/module-settings';

const props = defineProps<{ moduleId: string; settings: ModuleSettingsDef }>();

const { t } = useI18n();
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

/** "humaniza" una clave snake_case → "Title Case" para cuando falta `title` en el schema. */
function humanize(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Campos a renderizar, en el orden de `properties` del schema. */
const fields = computed<Field[]>(() =>
  Object.entries(properties.value).map(([key, prop]) => ({
    key,
    label: prop.title || humanize(key),
    description: prop.description,
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

async function boot(): Promise<void> {
  status.value = 'loading';
  try {
    const schema = await loadSchema();
    properties.value = schema.properties ?? {};

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
  try {
    // Snapshot completo: una clave por propiedad del schema (es un upsert, no un patch parcial).
    const snapshot: Record<string, unknown> = {};
    for (const [key, prop] of Object.entries(properties.value)) {
      snapshot[key] = settingValueForStorage(prop, model[key]);
    }
    await client.command(props.settings.set, snapshot);
    await toastSuccess(t('moduleSettings.saved'));
  } catch {
    await toastError(t('moduleSettings.saveError'));
  } finally {
    saving.value = false;
  }
}

onMounted(() => void boot());
</script>
