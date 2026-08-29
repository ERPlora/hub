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
              v-model="form.name"
              :label="t('employeeForm.fullName')"
              label-placement="floating"
              mode="md"
              fill="outline"
              autocomplete="name"
              :maxlength="150"
              :error-text="nameError"
              :class="{ 'ion-invalid ion-touched': Boolean(issueOn(NAME_ISSUES)) }"
              required
            />
            <!-- Sin la casilla, el email ES la identidad (hub#356): es por lo que el SaaS manda la
                 invitación y por lo que su primer login encuentra esta ficha. -->
            <ion-input
              v-if="!isLocal"
              v-model="form.email"
              :label="t('employeeForm.email')"
              label-placement="floating"
              mode="md"
              fill="outline"
              type="email"
              autocomplete="email"
              :maxlength="254"
              :helper-text="isEdit ? '' : t('employeeForm.accountEmailHelp')"
              :error-text="emailError"
              :class="{ 'ion-invalid ion-touched': Boolean(issueOn(EMAIL_ISSUES)) }"
            />
            <ion-select
              v-model="form.role"
              :label="t('employeeForm.role')"
              label-placement="floating"
              mode="md"
              fill="outline"
              interface="popover"
              :error-text="issueOn(ROLE_ISSUES) ? t(`employeeForm.errors.${issueOn(ROLE_ISSUES)}`) : ''"
              :class="{ 'ion-invalid ion-touched': Boolean(issueOn(ROLE_ISSUES)) }"
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
              mode="md"
              fill="outline"
              inputmode="numeric"
              :maxlength="hubPinLength"
              :helper-text="pinHelp"
              :error-text="pinError"
              :class="{ 'ion-invalid ion-touched': Boolean(issueOn(PIN_ISSUES)) }"
            />
            <!-- **Placa** (hub#658): un campo que el LECTOR rellena y que sigue siendo tecleable —
                 un iButton lleva el número grabado y no todo el mundo tiene el lector a mano. El
                 lector no necesita que este campo tenga el foco: la ráfaga la caza el listener
                 global del shell y aterriza aquí (el foro de Odoo es el archivo de por qué la
                 captura por foco no vale). La placa NUNCA sustituye al PIN: vaciarla la revoca y el
                 PIN sigue donde estaba. -->
            <ion-input
              v-model="form.badge"
              :label="t('employeeForm.badge')"
              label-placement="floating"
              mode="md"
              fill="outline"
              autocomplete="off"
              :maxlength="64"
              :helper-text="badgeHelp"
              :error-text="badgeError"
            />
          </div>

          <!-- «Local user» (hub#355): nombre + PIN, sin email y sin nada en el SaaS. Solo en el
               ALTA: sobre una ficha existente la vía de acceso se cambia con el email y el PIN,
               no volviendo a decidir qué clase de identidad es. -->
          <ion-toggle
            v-if="!isEdit"
            :checked="form.local"
            label-placement="start"
            justify="space-between"
            class="active-toggle"
            @ion-change="form.local = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
          >
            {{ t('employeeForm.localUser') }}
          </ion-toggle>
          <p v-if="!isEdit" class="toggle-help">{{ t('employeeForm.localUserHelp') }}</p>

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
            class="clear-credential"
            :disabled="saving"
            @click="clearPin"
          >
            {{ t('employeeForm.clearPin') }}
          </ion-button>

          <ion-button
            v-if="hasBadge"
            type="button"
            fill="clear"
            size="small"
            class="clear-credential"
            :disabled="saving"
            @click="clearBadge"
          >
            {{ t('employeeForm.clearBadge') }}
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
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
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
  accountUserIssue,
  createHubUser,
  hubUserErrorKey,
  listHubRoles,
  listHubUsers,
  localUserIssue,
  updateHubUser,
  type HubRole,
  type HubUser,
  type HubUserPatch,
} from '../lib/hub-users';
import { fieldRefusalOf, invalidFieldMessage } from '../lib/invalid-field';
import { platformFailureMessage } from '../lib/platform-failure';
import { hubPinLength } from '../lib/pin-length';
import { onBadgeScan } from '../lib/badge-scanner';
import { nfcBadgeReady } from '../lib/nfc-badge';
import { toast } from '../lib/toast';

const { t, te } = useI18n();
const route = useRoute();
const router = useRouter();
const isEdit = computed(() => typeof route.params.id === 'string' && route.params.id.length > 0);

const form = reactive({
  name: '',
  email: '',
  role: 'employee',
  pin: '',
  badge: '',
  isActive: true,
  /** Casilla «Local user» (hub#355). Solo cuenta en el alta; una ficha existente no la usa. */
  local: false,
});

const roles = ref<HubRole[]>([]);
const users = ref<HubUser[]>([]);
const hasPin = ref(false);
const hasBadge = ref(false);
const loading = ref(true);
const saving = ref(false);
const loadError = ref(false);
const saveError = ref('');
/**
 * El rechazo del último guardado, **anclado al campo** que lo causó (hub#1190).
 *
 * El core responde `invalid_field` con `field` y `reason` como datos (ADR-0398 §6), así que la
 * frase sale del catálogo del shell y se pinta debajo del input que se arregla — que es donde la
 * ponen Odoo, Shopify y Business Central. Un banner al principio del formulario obliga a adivinar
 * qué campo era. Lo que el formulario no tiene (un campo que esta pantalla no pinta) cae al banner.
 */
const fieldRejection = ref<{ field: string; message: string } | null>(null);
const submitted = ref(false);
const dirty = ref(false);
let snapshot = '';
/** Estado guardado, para mandar en el PUT solo lo que cambia. */
let initial = { name: '', email: '', role: '', isActive: true };

const emailValid = computed(() =>
  !form.email.trim() || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim()),
);
/** Alta de usuario LOCAL: solo se decide al crear (hub#355). */
const isLocal = computed(() => !isEdit.value && form.local);
/**
 * Motivo por el que el runtime rechazaría este alta, adelantado aquí. Cada identidad tiene el suyo
 * —`localUserIssue` (hub#355) y `accountUserIssue` (hub#356)—, y el runtime revalida y es la
 * autoridad: `pin_in_use` solo lo sabe él (los PIN están hasheados) y llega en la respuesta.
 */
const altaIssue = computed(() => {
  if (isEdit.value) return '';
  return isLocal.value
    ? localUserIssue({ name: form.name, role: form.role, pin: form.pin }, users.value)
    : accountUserIssue({ email: form.email, role: form.role, pin: form.pin }, users.value);
});

/**
 * Los campos que este formulario PINTA con su propio hueco de error (hub#1190). Un rechazo de
 * cualquier otro campo (el `role`, que es un `ion-select` sin `error-text`) va al banner: anclarlo
 * a un control que no lo enseña sería esconderlo.
 */
const ANCHORED_FIELDS = ['name', 'email', 'pin', 'badge'];

/** Qué campo se lleva cada motivo, para que el error salga donde se arregla. */
const NAME_ISSUES = ['name_taken'];
const EMAIL_ISSUES = ['account_needs_email', 'invalid_email', 'email_taken', 'local_has_email'];
const ROLE_ISSUES = ['account_role_not_grantable', 'local_cannot_administer'];
const PIN_ISSUES = ['local_needs_pin', 'pin_length', 'pin_too_simple'];
/**
 * «Falta el email» es el estado NORMAL de un formulario recién abierto —el alta de cuenta es la
 * que sale por defecto—, así que ese motivo espera a que se pulse «Guardar»; los demás salen en
 * cuanto se pueden ver, que es de lo que sirve adelantarlos.
 */
const ISSUES_THAT_WAIT_FOR_SUBMIT = ['account_needs_email'];

/** El motivo actual si pertenece a este campo (y ya toca enseñarlo), o `''`. */
function issueOn(field: string[]): string {
  const issue = altaIssue.value;
  if (!issue || !field.includes(issue)) return '';
  return !submitted.value && ISSUES_THAT_WAIT_FOR_SUBMIT.includes(issue) ? '' : issue;
}

/** Lo que el SERVIDOR rechazó de este campo en el último guardado, o `''` (hub#1190). */
function rejectionOn(field: string): string {
  return fieldRejection.value?.field === field ? fieldRejection.value.message : '';
}

const nameError = computed(() => {
  if (submitted.value && !form.name.trim()) return t('employeeForm.required');
  const issue = issueOn(NAME_ISSUES);
  return issue ? t(`employeeForm.errors.${issue}`) : rejectionOn('name');
});
const emailError = computed(() => {
  const issue = issueOn(EMAIL_ISSUES);
  if (issue) return t(`employeeForm.errors.${issue}`);
  if (submitted.value && !emailValid.value) return t('employeeForm.invalidEmail');
  return rejectionOn('email');
});
const pinError = computed(() => {
  const issue = issueOn(PIN_ISSUES);
  // hub#1302: `pin_length` needs the digit count THIS hub asks for — harmless for the other two
  // PIN_ISSUES keys, which do not interpolate `{n}` at all.
  return issue ? t(`employeeForm.errors.${issue}`, { n: hubPinLength.value }) : rejectionOn('pin');
});
const BADGE_SHAPE = /^[A-Za-z0-9\-_]{4,64}$/;
const badgeError = computed(() =>
  form.badge.trim() && !BADGE_SHAPE.test(form.badge.trim())
    ? t('employeeForm.errors.badge_shape')
    : rejectionOn('badge'),
);
// «Acércala» solo donde acercarla funciona (hub#988). `nfcBadgeReady` se enciende cuando el shell
// ha atendido una lectura de verdad, no por estar dentro de la app: en un escritorio instalado la
// promesa sería falsa, y una instrucción que no funciona es peor que no darla.
const badgeHelp = computed(() => {
  if (nfcBadgeReady.value) {
    return hasBadge.value ? t('employeeForm.badgeNfcSetHelp') : t('employeeForm.badgeNfcHelp');
  }
  return hasBadge.value ? t('employeeForm.badgeSetHelp') : t('employeeForm.badgeHelp');
});
const pinHelp = computed(() => {
  // hub#1302: `pinHelp`/`localPinHelp`/`accountPinHelp` state a digit count, which is this hub's
  // `pin_length` (4 or 6, hub#974), never a fixed number — `pinSetHelp` below mentions none.
  const n = { n: hubPinLength.value };
  if (isLocal.value) return t('employeeForm.localPinHelp', n);
  if (hasPin.value) return t('employeeForm.pinSetHelp');
  // En el alta de cuenta el PIN es un extra —entra con su cuenta—, no la vía de acceso.
  return isEdit.value ? t('employeeForm.pinHelp', n) : t('employeeForm.accountPinHelp', n);
});
const canSubmit = computed(
  () => Boolean(form.name.trim() && emailValid.value) && !altaIssue.value && !badgeError.value,
);

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
    // El censo lo necesitan las dos caras: la edición para leer la ficha, y el alta local para
    // adelantar «este hub ya conoce a alguien con ese nombre» sin ir al servidor.
    [roles.value, users.value] = await Promise.all([listHubRoles(), listHubUsers()]);
    if (isEdit.value) {
      const id = String(route.params.id);
      const target = users.value.find((u) => u.id === id);
      if (!target) throw new Error(t('employeeForm.notFound'));
      hasPin.value = target.has_pin;
      hasBadge.value = target.has_badge === true;
      Object.assign(form, {
        name: target.name,
        email: target.email,
        role: target.role,
        pin: '',
        badge: '',
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

/**
 * **Revoca la placa, y solo la placa** (hub#658). El PIN no se toca: perder la tarjeta no puede
 * dejar a nadie fuera, y volver a solo-PIN tiene que poder hacerse siempre. El caso Lightspeed
 * L-Series —tarjeta irrevocable, sin recuperación documentada, producto descatalogado— es por qué
 * este botón existe.
 */
function clearBadge(): void {
  form.badge = '';
  hasBadge.value = false;
  dirty.value = true;
}

async function onSave(): Promise<void> {
  submitted.value = true;
  if (!canSubmit.value) return;
  saving.value = true;
  saveError.value = '';
  fieldRejection.value = null;
  const name = form.name.trim();
  const email = form.email.trim();
  const pin = form.pin.trim();
  const badge = form.badge.trim();
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
      // La placa viaja **por separado** del PIN y solo cuando se ha tocado: escribir `badge: ''` en
      // cada guardado revocaría la tarjeta de quien solo cambió el nombre.
      if (badge) patch.badge = badge;
      else if (!hasBadge.value) patch.badge = '';
      await updateHubUser(String(route.params.id), patch);
    } else {
      await createHubUser({
        name,
        // Un usuario local no lleva email: el runtime rechaza el alta si viene uno.
        email: isLocal.value ? '' : email,
        role: form.role || 'employee',
        pin,
        badge,
        local: isLocal.value,
      });
    }
    markClean();
    void toast(isEdit.value ? t('employees.updated') : t('employees.created'), 'success');
    await router.replace('/employees');
  } catch (error) {
    // Orden (hub#1190, hub#1258): motivo de NEGOCIO del core (`hub.users.*`, hub#355) → campo
    // rechazado traducido (hub#1190) → rechazo de PLATAFORMA traducido (`db`,
    // `module_not_installed`… — nadie escribió esa frase para esta pantalla, hub#1102) → la frase
    // que vino. El `message` del runtime está en INGLÉS a propósito (regla del idioma del código):
    // pintarlo tal cual es lo que dejaba «the name is required» delante de una encargada. Se
    // conserva como ÚLTIMO recurso porque dice más que cualquier genérico inventado (misma regla
    // que `platformFailureMessage`, hub#1102).
    const key = hubUserErrorKey(error);
    const message = key
      ? t(`employeeForm.errors.${key}`)
      : (invalidFieldMessage(error, t, te, { length: hubPinLength.value }) ??
        platformFailureMessage(error, t, te) ??
        (error instanceof Error ? error.message : t('employees.saveError')));
    const refusal = fieldRefusalOf(error);
    if (!key && refusal && ANCHORED_FIELDS.includes(refusal.field)) {
      fieldRejection.value = { field: refusal.field, message };
    } else {
      saveError.value = message;
    }
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
// **El lector rellena el campo sin tocarlo** (hub#658): la ráfaga llega del listener global del
// shell, no del foco. Es lo que hace que dar de alta una tarjeta sea «pasarla», que es el gesto que
// el mercado usa (Square, Toast, Aloha), sin que el número pueda caer en otro campo por el camino.
let stopBadgeScan: (() => void) | null = null;
onMounted(async () => {
  stopBadgeScan = onBadgeScan((badge) => {
    form.badge = badge;
    hasBadge.value = false;
    dirty.value = true;
  });
  await load();
  dirty.value = false;
});
onUnmounted(() => {
  stopBadgeScan?.();
  stopBadgeScan = null;
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

.toggle-help {
  margin: -0.5rem 0 0;
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
}

/* Retirar el PIN y retirar la placa: el mismo gesto sobre dos credenciales hermanas (hub#658). */
.clear-credential {
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
