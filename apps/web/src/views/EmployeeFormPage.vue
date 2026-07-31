<template>
  <AppPage
    :title="isEdit ? t('employeeForm.titleEdit') : t('employeeForm.titleNew')"
    back-href="/employees"
    content-layout="detail"
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
              v-model="form.firstName"
              :label="t('employeeForm.firstName')"
              label-placement="floating"
              fill="outline"
              autocomplete="given-name"
              :maxlength="100"
              :error-text="submitted && !form.firstName.trim() ? t('employeeForm.required') : ''"
              required
            />
            <ion-input
              v-model="form.lastName"
              :label="t('employeeForm.lastName')"
              label-placement="floating"
              fill="outline"
              autocomplete="family-name"
              :maxlength="100"
              :error-text="submitted && !form.lastName.trim() ? t('employeeForm.required') : ''"
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
            <ion-input
              v-model="form.phone"
              :label="t('employeeForm.phone')"
              label-placement="floating"
              fill="outline"
              type="tel"
              autocomplete="tel"
              :maxlength="20"
            />
            <ion-select
              v-model="form.roleId"
              :label="t('employeeForm.role')"
              label-placement="floating"
              fill="outline"
              interface="popover"
            >
              <ion-select-option value="">{{ t('employeeForm.noRole') }}</ion-select-option>
              <ion-select-option v-for="role in roles" :key="String(role.id)" :value="String(role.id)">
                {{ role.name }}
              </ion-select-option>
            </ion-select>
            <ion-select
              v-model="form.status"
              :label="t('employeeForm.status')"
              label-placement="floating"
              fill="outline"
              interface="popover"
            >
              <ion-select-option value="active">{{ t('employees.status.active') }}</ion-select-option>
              <ion-select-option value="inactive">{{ t('employees.status.inactive') }}</ion-select-option>
              <ion-select-option value="on_leave">{{ t('employees.status.on_leave') }}</ion-select-option>
              <ion-select-option value="terminated">{{ t('employees.status.terminated') }}</ion-select-option>
            </ion-select>
            <ion-input
              v-model="form.hireDate"
              :label="t('employeeForm.hireDate')"
              label-placement="floating"
              fill="outline"
              type="date"
            />
          </div>

          <ion-toggle
            :checked="form.isBookable"
            label-placement="start"
            justify="space-between"
            class="active-toggle"
            @ion-change="form.isBookable = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
          >
            {{ t('employeeForm.bookable') }}
          </ion-toggle>

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
import { getClient } from '../lib/runtime';
import { toast } from '../lib/toast';

interface StaffRole {
  id: string;
  name: string;
}

interface StaffMember {
  id: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  role_id?: string | null;
  status?: EmployeeStatus;
  hire_date?: string | null;
  is_bookable?: number | boolean;
}

type EmployeeStatus = 'active' | 'inactive' | 'on_leave' | 'terminated';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const client = getClient();
const isEdit = computed(() => typeof route.params.id === 'string' && route.params.id.length > 0);

const form = reactive({
  firstName: '',
  lastName: '',
  email: '',
  phone: '',
  roleId: '',
  status: 'active' as EmployeeStatus,
  hireDate: '',
  isBookable: true,
});

const roles = ref<StaffRole[]>([]);
const loading = ref(true);
const saving = ref(false);
const loadError = ref(false);
const saveError = ref('');
const submitted = ref(false);
const dirty = ref(false);
let snapshot = '';

const emailValid = computed(() =>
  !form.email.trim() || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim()),
);
const canSubmit = computed(() =>
  Boolean(form.firstName.trim() && form.lastName.trim() && emailValid.value),
);

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
    roles.value = await client.query<StaffRole[]>('staff.roles.list');
    if (isEdit.value) {
      const rows = await client.query<StaffMember[]>('staff.members.get', {
        staff_id: String(route.params.id),
      });
      const member = rows[0];
      if (!member) throw new Error(t('employeeForm.notFound'));
      Object.assign(form, {
        firstName: member.first_name ?? '',
        lastName: member.last_name ?? '',
        email: member.email ?? '',
        phone: member.phone ?? '',
        roleId: member.role_id ?? '',
        status: member.status ?? 'active',
        hireDate: member.hire_date ?? '',
        isBookable: Boolean(member.is_bookable),
      });
    }
    markClean();
  } catch {
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

async function onSave(): Promise<void> {
  submitted.value = true;
  if (!canSubmit.value) return;
  saving.value = true;
  saveError.value = '';
  const payload = {
    first_name: form.firstName.trim(),
    last_name: form.lastName.trim(),
    email: form.email.trim(),
    phone: form.phone.trim(),
    role_id: form.roleId || null,
    status: form.status,
    hire_date: form.hireDate || null,
    is_bookable: form.isBookable ? 1 : 0,
  };
  try {
    if (isEdit.value) {
      await client.command('staff.members.update', {
        staff_id: String(route.params.id),
        ...payload,
      });
    } else {
      await client.command('staff.members.create', payload);
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
