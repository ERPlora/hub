<template>
  <ion-page>
    <AppTopbar :title="isEdit ? 'Editar empleado' : 'Nuevo empleado'" back-href="/employees" />

    <ion-content class="ion-padding">
      <ion-card class="ion-no-margin">
        <ion-card-content>
          <ion-list>
            <ion-item>
              <ion-input
                v-model="form.name"
                label="Nombre"
                label-placement="stacked"
                placeholder="Nombre y apellidos"
              />
            </ion-item>

            <ion-item>
              <ion-input
                v-model="form.email"
                label="Email"
                label-placement="stacked"
                type="email"
                placeholder="empleado@empresa.com"
              />
            </ion-item>

            <ion-item>
              <ion-select
                v-model="form.role"
                label="Rol"
                label-placement="stacked"
              >
                <ion-select-option v-for="r in ROLES" :key="r" :value="r">{{ r }}</ion-select-option>
              </ion-select>
            </ion-item>

            <ion-item lines="none">
              <ion-toggle
                :checked="form.active"
                @ion-change="form.active = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
              >
                Activo
              </ion-toggle>
            </ion-item>
          </ion-list>

          <div class="mt-4 flex justify-end gap-2">
            <ion-button fill="outline" @click="onCancel">Cancelar</ion-button>
            <ion-button @click="onSave">{{ isEdit ? 'Guardar' : 'Crear' }}</ion-button>
          </div>
        </ion-card-content>
      </ion-card>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  IonPage, IonContent,
  IonCard, IonCardContent, IonList, IonItem, IonInput, IonSelect, IonSelectOption,
  IonToggle, IonButton,
} from '@ionic/vue';
import AppTopbar from '../components/AppTopbar.vue';

const ROLES = ['Administrador', 'Encargado', 'Cajero', 'Almacén'] as const;
type Role = typeof ROLES[number];

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
