<template>
  <AppPage :title="isEdit ? t('employeeForm.titleEdit') : t('employeeForm.titleNew')" back-href="/employees">
      <ion-card class="ion-no-margin">
        <ion-card-content>
          <ion-list>
            <ion-item>
              <ion-input
                v-model="form.name"
                :label="t('employeeForm.name')"
                label-placement="floating"
                :placeholder="t('employeeForm.namePlaceholder')"
              />
            </ion-item>

            <ion-item>
              <ion-input
                v-model="form.email"
                :label="t('employeeForm.email')"
                label-placement="floating"
                type="email"
                :placeholder="t('employeeForm.emailPlaceholder')"
              />
            </ion-item>

            <ion-item>
              <ion-select
                v-model="form.role"
                :label="t('employeeForm.role')"
                label-placement="floating"
              >
                <ion-select-option v-for="r in ROLES" :key="r" :value="r">{{ roleLabel(r) }}</ion-select-option>
              </ion-select>
            </ion-item>

            <ion-item lines="none">
              <ion-toggle
                :checked="form.active"
                @ion-change="form.active = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
              >
                {{ t('employeeForm.active') }}
              </ion-toggle>
            </ion-item>
          </ion-list>

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
  IonCard, IonCardContent, IonList, IonItem, IonInput, IonSelect, IonSelectOption,
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
