<template>
  <AppPage :title="isEdit ? t('employeeForm.titleEdit') : t('employeeForm.titleNew')" back-href="/employees">
      <ion-card class="ion-no-margin">
        <ion-card-content>
          <!-- Inputs Ionic estándar: fill="outline" + label flotante, SIN ion-item
               (el `fill` ya dibuja su propia caja; envolverlo en ion-item duplica el chrome).
               Mismo patrón que LoginPage para mantener la paridad visual. -->
          <div class="emp-form">
            <ion-input
              v-model="form.name"
              :label="t('employeeForm.name')"
              label-placement="floating"
              fill="outline"
              :placeholder="t('employeeForm.namePlaceholder')"
            />

            <ion-input
              v-model="form.email"
              :label="t('employeeForm.email')"
              label-placement="floating"
              fill="outline"
              type="email"
              :placeholder="t('employeeForm.emailPlaceholder')"
            />

            <ion-select
              v-model="form.role"
              :label="t('employeeForm.role')"
              label-placement="floating"
              fill="outline"
              interface="popover"
            >
              <ion-select-option v-for="r in ROLES" :key="r" :value="r">{{ roleLabel(r) }}</ion-select-option>
            </ion-select>

            <ion-toggle
              :checked="form.active"
              label-placement="start"
              justify="space-between"
              class="active-toggle"
              @ion-change="form.active = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
            >
              {{ t('employeeForm.active') }}
            </ion-toggle>
          </div>

          <div class="mt-4 flex justify-end gap-2">
            <ion-button fill="outline" @click="onCancel">{{ t('employeeForm.cancel') }}</ion-button>
            <ion-button @click="onSave">{{ isEdit ? t('employeeForm.save') : t('employeeForm.create') }}</ion-button>
          </div>
        </ion-card-content>
      </ion-card>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonCard, IonCardContent, IonInput, IonSelect, IonSelectOption,
  IonToggle, IonButton,
} from '@ionic/vue';
import AppPage from '../components/AppPage.vue';

const { t } = useI18n();

const ROLES = ['Administrador', 'Encargado', 'Cajero', 'Almacén'] as const;
type Role = typeof ROLES[number];

const ROLE_LABEL_KEYS: Record<Role, string> = {
  'Administrador': 'employeeForm.roleAdmin',
  'Encargado': 'employeeForm.roleManager',
  'Cajero': 'employeeForm.roleCashier',
  'Almacén': 'employeeForm.roleWarehouse',
};

function roleLabel(role: Role): string {
  return t(ROLE_LABEL_KEYS[role]);
}

interface EmployeeForm {
  name: string;
  email: string;
  role: Role;
  active: boolean;
}

const route = useRoute();
const router = useRouter();

const isEdit = computed(() => !!route.params.id);

const form = reactive<EmployeeForm>({
  name: isEdit.value ? 'María García' : '',
  email: isEdit.value ? 'maria@tienda.com' : '',
  role: isEdit.value ? 'Encargado' : 'Cajero',
  active: true,
});

function onCancel(): void {
  router.push('/employees');
}

async function onSave(): Promise<void> {
  if (isEdit.value) {
    // TODO: llamar al runtime → execute_command('employees.update', { id: route.params.id, ...form })
  } else {
    // TODO: llamar al runtime → execute_command('employees.create', { ...form })
  }
  await router.push('/employees');
}
</script>

<style scoped>
/* Formulario: inputs Ionic standalone separados por gap (mismo ritmo que LoginPage). */
.emp-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
/* El toggle ocupa el ancho como una fila etiqueta-izquierda / control-derecha. */
.active-toggle {
  width: 100%;
  padding-block: 4px;
}
</style>
