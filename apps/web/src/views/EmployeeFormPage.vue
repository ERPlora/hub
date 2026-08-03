<!--
  Ficha de un usuario del Hub (Personal → editar). CORE: edita `hub_user` vía /api/hub/users/{id},
  no el módulo `staff`. Campos = los que el core conoce de una identidad: nombre visible, email del
  perfil, rol (permisos), estado (alta/baja) y PIN local. El alta rápida vive en la tabla; esta
  pantalla es la edición detallada de /employees/:id.
-->
<template>
  <AppPage
    :title="isEdit ? t('employeeForm.titleEdit') : t('employeeForm.titleNew')"
    back-href="/employees"
  >
    <div v-if="loading" class="form-loading">
      <ion-spinner name="crescent" />
    </div>

    <ok-inline-feedback
      v-else-if="loadError"
      tone="danger"
      icon="alert-circle-outline"
      :heading="t('employeeForm.loadErrorTitle')"
    >
      {{ t('employeeForm.loadErrorBody') }}
      <ion-button slot="actions" size="small" fill="outline" @click="load">
        {{ t('employees.retry') }}
      </ion-button>
    </ok-inline-feedback>

    <ion-card v-else class="ion-no-margin employee-card">
      <ion-card-content>
        <form class="emp-form" @submit.prevent="onSave">
          <ok-inline-feedback v-if="saveError" tone="danger">
            {{ saveError }}
          </ok-inline-feedback>

          <div class="form-grid">
            <ion-input
              v-model="form.name"
              :label="t('employeeForm.fullName')"
              label-placement="floating"
              fill="outline"
              autocomplete="name"
              :maxlength="150"
              :error-text="submitted && !form.name.trim() ? t('employeeForm.required') : ''"
              required
            />
            <ion-input
              v-model="form.email"
              :label="t('employeeForm.email')"
              label-placement="floating"
              fill="outline"
              type="email"
              autocomplete="email"
              :maxlength="254"
              :error-text="submitted && !emailValid ? t('employeeForm.invalidEmail') : ''"
            />
            <ion-select
              v-model="form.role"
              :label="t('employeeForm.role')"
              label-placement="floating"
              fill="outline"
              interface="popover"
            >
              <ion-select-option v-for="role in roles" :key="role.name" :value="role.name">
                {{ roleLabel(role.name) }}
              </ion-select-option>
            </ion-select>
            <!-- PIN local: en blanco = no se toca. Escribirlo lo cambia; «retirar» lo deja sin
                 acceso por PIN (seguirá pudiendo entrar por Cloud si tiene cuenta). -->
            <ion-input
              v-model="form.pin"
              :label="t('employeeForm.pin')"
              label-placement="floating"
              fill="outline"
              inputmode="numeric"
              :maxlength="8"
              :helper-text="hasPin ? t('employeeForm.pinSetHelp') : t('employeeForm.pinHelp')"
            />
          </div>

          <ion-toggle
            :checked="form.isActive"
            label-placement="start"
            justify="space-between"
            class="active-toggle"
            @ion-change="form.isActive = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
          >
            {{ t('employeeForm.activeUser') }}
          </ion-toggle>

          <ion-button
            v-if="hasPin"
            type="button"
            fill="clear"
            size="small"
            class="clear-pin"
            :disabled="saving"
            @click="clearPin"
          >
            {{ t('employeeForm.clearPin') }}
          </ion-button>

          <div class="form-actions">
            <ion-button type="button" fill="outline" :disabled="saving" @click="onCancel">
              {{ t('employeeForm.cancel') }}
            </ion-button>
            <ion-button type="submit" :disabled="saving || !canSubmit">
              <ion-spinner v-if="saving" slot="start" name="crescent" />
              {{ saving ? t('employeeForm.saving') : isEdit ? t('employeeForm.save') : t('employeeForm.create') }}
            </ion-button>
          </div>
        </form>
      </ion-card-content>
    </ion-card>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonButton,
  IonCard,
  IonCardContent,
  IonInput,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonToggle,
  alertController,
} from '@ionic/vue';
import AppPage from '../components/AppPage.vue';
import {
  createHubUser,
  listHubRoles,
  listHubUsers,
  updateHubUser,
  type HubRole,
  type HubUserPatch,
} from '../lib/hub-users';
import { toast } from '../lib/toast';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const isEdit = computed(() => typeof route.params.id === 'string' && route.params.id.length > 0);

const form = reactive({
  name: '',
  email: '',
  role: 'employee',
  pin: '',
  isActive: true,
});

const roles = ref<HubRole[]>([]);
const hasPin = ref(false);
const loading = ref(true);
const saving = ref(false);
const loadError = ref(false);
const saveError = ref('');
const submitted = ref(false);
const dirty = ref(false);
let snapshot = '';
/** Estado guardado, para mandar en el PUT solo lo que cambia. */
let initial = { name: '', email: '', role: '', isActive: true };

const emailValid = computed(() =>
  !form.email.trim() || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim()),
);
const canSubmit = computed(() => Boolean(form.name.trim() && emailValid.value));

/** Etiqueta traducida de un rol conocido; los que aporta un módulo se muestran tal cual. */
function roleLabel(role: string): string {
  const key = `employees.roles.${role}`;
  const label = t(key);
  return label === key ? role : label;
}

function serializeForm(): string {
  return JSON.stringify(form);
}

function markClean(): void {
  snapshot = serializeForm();
  dirty.value = false;
}

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = false;
  try {
    roles.value = await listHubRoles();
    if (isEdit.value) {
      const id = String(route.params.id);
      const target = (await listHubUsers()).find((u) => u.id === id);
      if (!target) throw new Error(t('employeeForm.notFound'));
      hasPin.value = target.has_pin;
      Object.assign(form, {
        name: target.name,
        email: target.email,
        role: target.role,
        pin: '',
        isActive: target.is_active,
      });
      initial = {
        name: target.name,
        email: target.email,
        role: target.role,
        isActive: target.is_active,
      };
    }
    markClean();
  } catch {
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

/** Retira el PIN del usuario (queda sin acceso local). Se aplica al guardar. */
function clearPin(): void {
  form.pin = '';
  hasPin.value = false;
  dirty.value = true;
}

async function onSave(): Promise<void> {
  submitted.value = true;
  if (!canSubmit.value) return;
  saving.value = true;
  saveError.value = '';
  const name = form.name.trim();
  const email = form.email.trim();
  const pin = form.pin.trim();
  try {
    if (isEdit.value) {
      // Parcial: solo viaja lo que cambió. `pin: ''` solo si se pulsó «retirar PIN» — un campo
      // vacío sin tocar nada no debe borrarle el PIN a nadie.
      const patch: HubUserPatch = {};
      if (name !== initial.name) patch.name = name;
      if (email !== initial.email) patch.email = email;
      if (form.role !== initial.role) patch.role = form.role;
      if (form.isActive !== initial.isActive) patch.is_active = form.isActive;
      if (pin) patch.pin = pin;
      else if (!hasPin.value) patch.pin = '';
      await updateHubUser(String(route.params.id), patch);
    } else {
      await createHubUser({ name, email, role: form.role || 'employee', pin });
    }
    markClean();
    void toast(isEdit.value ? t('employees.updated') : t('employees.created'), 'success');
    await router.replace('/employees');
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : t('employees.saveError');
  } finally {
    saving.value = false;
  }
}

async function confirmDiscard(): Promise<boolean> {
  if (!dirty.value || serializeForm() === snapshot) return true;
  const alert = await alertController.create({
    header: t('employeeForm.unsavedTitle'),
    message: t('employeeForm.unsavedBody'),
    buttons: [
      { text: t('employeeForm.keepEditing'), role: 'cancel' },
      { text: t('employeeForm.discard'), role: 'confirm' },
    ],
  });
  await alert.present();
  const result = await alert.onDidDismiss();
  return result.role === 'confirm';
}

async function onCancel(): Promise<void> {
  if (await confirmDiscard()) await router.push('/employees');
}

onBeforeRouteLeave(async () => confirmDiscard());
onMounted(async () => {
  await load();
  dirty.value = false;
});
watch(form, () => {
  if (!loading.value) dirty.value = serializeForm() !== snapshot;
}, { deep: true });
</script>

<style scoped>
.employee-card {
  max-width: 56rem;
}

.form-loading {
  display: flex;
  justify-content: center;
  padding: 2.5rem 0;
}

.emp-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.875rem;
}

.active-toggle {
  width: 100%;
  padding-block: 0.25rem;
}

.clear-pin {
  align-self: flex-start;
  --color: var(--ion-color-danger);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

@media (max-width: 48rem) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-actions {
    flex-direction: column-reverse;
  }

  .form-actions ion-button {
    width: 100%;
  }
}
</style>
