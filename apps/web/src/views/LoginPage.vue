<template>
  <ion-page>
    <!-- Sin ion-header en login (no hay menú ni barra de título). -->
    <ion-content>

      <!-- Botón de tema: esquina superior derecha -->
      <ion-button
        fill="clear"
        aria-label="Cambiar tema"
        class="theme-btn"
        @click="toggleTheme"
      >
        <ion-icon slot="icon-only" :icon="dark ? sunnyOutline : moonOutline" />
      </ion-button>

      <div class="login-wrap">
        <div class="login-box">

          <!-- Logo / cabecera -->
          <div class="logo-area">
            <div class="logo-mark" aria-hidden="true">E</div>
            <p class="logo-sub">
              <template v-if="step === 'setup'">Crea tu PIN de acceso</template>
              <template v-else-if="step === 'pin'">Introduce tu PIN</template>
              <template v-else>Inicia sesión en tu hub</template>
            </p>
          </div>

          <!-- Tarjeta principal -->
          <ion-card class="ion-no-margin login-card">
            <ion-card-content>

              <!-- Tabs PIN | Email (solo cuando el dispositivo es de confianza y no en setup) -->
              <ion-segment
                v-if="showTabs"
                :value="step"
                class="mb-5"
                @ion-change="step = ($event as CustomEvent<{ value: Step }>).detail.value"
              >
                <ion-segment-button value="pin">
                  <ion-icon :icon="keypadOutline" />
                  <ion-label>PIN</ion-label>
                </ion-segment-button>
                <ion-segment-button value="email">
                  <ion-icon :icon="mailOutline" />
                  <ion-label>Email</ion-label>
                </ion-segment-button>
              </ion-segment>

              <!-- Paso: login por email+contraseña -->
              <form v-if="step === 'email'" class="step-form" @submit.prevent="submitEmail">
                <ion-input
                  v-model="emailVal"
                  label="Email"
                  label-placement="stacked"
                  type="email"
                  autocomplete="username"
                  fill="outline"
                  placeholder="tu@empresa.com"
                  @ion-input="emailVal = ($event as CustomEvent<{ value: string }>).detail.value ?? ''"
                />
                <ion-input
                  v-model="passwordVal"
                  label="Contraseña"
                  label-placement="stacked"
                  type="password"
                  autocomplete="current-password"
                  fill="outline"
                  placeholder="••••••••"
                  @ion-input="passwordVal = ($event as CustomEvent<{ value: string }>).detail.value ?? ''"
                />

                <!-- Checkbox "confiar en este dispositivo" + popover informativo -->
                <div class="trust-row">
                  <ion-checkbox
                    :checked="trust"
                    label-placement="end"
                    @ion-change="trust = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
                  >
                    <span class="trust-label">Confiar en este dispositivo</span>
                  </ion-checkbox>
                  <ion-button
                    id="trust-info-btn"
                    fill="clear"
                    size="small"
                    aria-label="Más información sobre dispositivos de confianza"
                    class="trust-info-btn"
                  >
                    <ion-icon slot="icon-only" :icon="informationCircleOutline" />
                  </ion-button>
                  <ion-popover
                    trigger="trust-info-btn"
                    trigger-action="click"
                    side="top"
                    alignment="center"
                  >
                    <div class="popover-content">
                      <p class="popover-title">Acceso por PIN</p>
                      <p class="popover-body">
                        Marca esta casilla para poder entrar con un <strong>PIN</strong> en este
                        dispositivo la próxima vez, sin escribir email y contraseña. Si no la marcas,
                        siempre tendrás que iniciar sesión con email.
                      </p>
                    </div>
                  </ion-popover>
                </div>

                <ion-note v-if="emailError" color="danger" class="error-note">
                  {{ emailError }}
                </ion-note>

                <ion-button type="submit" expand="block" :disabled="emailLoading">
                  <ion-spinner v-if="emailLoading" name="crescent" />
                  <template v-else>
                    <ion-icon slot="start" :icon="logInOutline" />
                    Entrar
                  </template>
                </ion-button>

                <ion-button
                  v-if="trusted && !showTabs"
                  fill="clear"
                  size="small"
                  @click="step = 'pin'"
                >
                  Usar PIN en su lugar
                </ion-button>
              </form>

              <!-- Paso: login por PIN -->
              <div v-else-if="step === 'pin'" class="step-form">

                <!-- Paso 1: elegir usuario (cuando hay varios en el dispositivo) -->
                <template v-if="!pinUser">
                  <ion-text color="medium" class="pin-choose-title">
                    <p>Elige tu usuario</p>
                  </ion-text>
                  <div class="user-grid">
                    <button
                      v-for="u in trustedUsers"
                      :key="u.id"
                      type="button"
                      class="user-card"
                      @click="selectPinUser(u)"
                    >
                      <span class="user-avatar">{{ u.initials }}</span>
                      <span class="user-name">{{ u.name }}</span>
                      <span v-if="u.email" class="user-email">{{ u.email }}</span>
                    </button>
                  </div>
                  <ion-button
                    v-if="!showTabs"
                    fill="clear"
                    size="small"
                    @click="step = 'email'"
                  >
                    Iniciar sesión con email
                  </ion-button>
                </template>

                <!-- Paso 2: introducir PIN del usuario elegido -->
                <template v-else>
                  <div class="pin-user-info">
                    <span class="user-avatar user-avatar--lg">{{ pinUser.initials }}</span>
                    <p class="user-name mt-2">{{ pinUser.name }}</p>
                    <button
                      v-if="trustedUsers.length > 1"
                      type="button"
                      class="change-user-btn"
                      @click="pinUser = null; pinValue = ''; pinError = false"
                    >
                      Cambiar usuario
                    </button>
                  </div>

                  <!-- PinPad inline: campo numérico oculto + dots de visualización -->
                  <div class="pinpad-wrap">
                    <div class="pinpad-dots" :class="{ 'pinpad-dots--error': pinError }">
                      <span
                        v-for="i in 4"
                        :key="i"
                        class="dot"
                        :class="{ filled: pinValue.length >= i }"
                      />
                    </div>
                    <ion-input
                      ref="pinInputRef"
                      :value="pinValue"
                      type="number"
                      inputmode="numeric"
                      :maxlength="4"
                      pattern="[0-9]*"
                      aria-label="PIN de 4 dígitos"
                      class="pin-hidden-input"
                      @ion-input="onPinInput"
                    />
                  </div>

                  <div class="pinpad-keys">
                    <button
                      v-for="key in ['1','2','3','4','5','6','7','8','9','','0','⌫']"
                      :key="key"
                      type="button"
                      class="pin-key"
                      :class="{ 'pin-key--empty': key === '' }"
                      :aria-label="key === '⌫' ? 'Borrar' : key === '' ? undefined : key"
                      :tabindex="key === '' ? -1 : 0"
                      @click="pressKey(key)"
                    >
                      {{ key }}
                    </button>
                  </div>

                  <ion-note v-if="pinError" color="danger" class="error-note">
                    PIN incorrecto
                  </ion-note>
                  <ion-button
                    v-if="!showTabs"
                    fill="clear"
                    size="small"
                    @click="step = 'email'; pinUser = null; pinValue = ''; pinError = false"
                  >
                    Iniciar sesión con email
                  </ion-button>
                </template>
              </div>

              <!-- Paso: alta del PIN (primer login con "Confiar en este dispositivo") -->
              <div v-else-if="step === 'setup'" class="step-form">
                <ion-text color="medium" class="setup-hint">
                  <p>{{ setupPhase === 'first' ? 'Elige un PIN de 4 dígitos' : 'Confirma tu PIN' }}</p>
                </ion-text>

                <!-- PinPad inline reutilizado para setup -->
                <div class="pinpad-wrap">
                  <div class="pinpad-dots" :class="{ 'pinpad-dots--error': setupError }">
                    <span
                      v-for="i in 4"
                      :key="i"
                      class="dot"
                      :class="{ filled: currentSetupPin.length >= i }"
                    />
                  </div>
                </div>

                <div class="pinpad-keys">
                  <button
                    v-for="key in ['1','2','3','4','5','6','7','8','9','','0','⌫']"
                    :key="key"
                    type="button"
                    class="pin-key"
                    :class="{ 'pin-key--empty': key === '' }"
                    :aria-label="key === '⌫' ? 'Borrar' : key === '' ? undefined : key"
                    :tabindex="key === '' ? -1 : 0"
                    @click="pressSetupKey(key)"
                  >
                    {{ key }}
                  </button>
                </div>

                <ion-note v-if="setupError" color="danger" class="error-note">
                  Los PIN no coinciden, inténtalo de nuevo
                </ion-note>
              </div>

            </ion-card-content>
          </ion-card>

          <p class="footer-note">
            ERPlora · {{ step === 'pin' ? 'dispositivo de confianza' : 'conexión segura con Cloud' }}
          </p>

        </div>
      </div>

    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  IonPage, IonContent, IonCard, IonCardContent, IonButton, IonIcon,
  IonInput, IonCheckbox, IonText, IonSpinner, IonSegment, IonSegmentButton,
  IonLabel, IonPopover, IonNote,
} from '@ionic/vue';
import {
  sunnyOutline, moonOutline, keypadOutline, mailOutline,
  logInOutline, informationCircleOutline,
} from 'ionicons/icons';
import { setUser } from '../lib/session';
import { cloudLogin, setTokens } from '../lib/cloud';

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------
type Step = 'pin' | 'email' | 'setup';

interface TrustedUser {
  id: string;
  name: string;
  email?: string;
  initials: string;
}

// ---------------------------------------------------------------------------
// Tema (dark mode Ionic: añade/quita la clase ion-palette-dark en <html>)
// ---------------------------------------------------------------------------
const dark = ref<boolean>(
  typeof document !== 'undefined'
    ? document.documentElement.classList.contains('ion-palette-dark')
    : false,
);

function toggleTheme(): void {
  dark.value = !dark.value;
  document.documentElement.classList.toggle('ion-palette-dark', dark.value);
}

// ---------------------------------------------------------------------------
// Estado de la sesión de dispositivo (PIN / trust)
// PIN y lista de usuarios de confianza se persisten en localStorage bajo
// 'erplora.trusted' y 'erplora.trusted_users'. El flujo de AUTH real del
// Cloud (ARQUITECTURA.md §2.9) se implementa en cloud.ts; aquí solo leemos
// el flag y la lista para mostrar/ocultar los pasos.
// ---------------------------------------------------------------------------
function readTrusted(): boolean {
  try { return localStorage.getItem('erplora.trusted') === '1'; } catch { return false; }
}
function readTrustedUsers(): TrustedUser[] {
  try {
    const raw = localStorage.getItem('erplora.trusted_users');
    return raw ? (JSON.parse(raw) as TrustedUser[]) : [];
  } catch { return []; }
}
function saveTrustedUsers(list: TrustedUser[]): void {
  try { localStorage.setItem('erplora.trusted_users', JSON.stringify(list)); } catch { /* ignore */ }
}
function saveTrustedFlag(val: boolean): void {
  try {
    if (val) localStorage.setItem('erplora.trusted', '1');
    else localStorage.removeItem('erplora.trusted');
  } catch { /* ignore */ }
}

const trusted = ref<boolean>(readTrusted());
const trustedUsers = ref<TrustedUser[]>(readTrustedUsers());

// ---------------------------------------------------------------------------
// Flujo de pasos
// ---------------------------------------------------------------------------
const step = ref<Step>(trusted.value ? 'pin' : 'email');
const showTabs = computed(() => trusted.value && step.value !== 'setup');

// ---------------------------------------------------------------------------
// EmailForm state
// ---------------------------------------------------------------------------
const router = useRouter();
const emailVal = ref<string>('');
const passwordVal = ref<string>('');
const trust = ref<boolean>(true);
const emailLoading = ref<boolean>(false);
const emailError = ref<string>('');

// Genera iniciales a partir del nombre completo
function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

async function submitEmail(): Promise<void> {
  emailError.value = '';
  emailLoading.value = true;
  try {
    // Login real contra el Cloud Portal (ARQUITECTURA.md §2.3: Bearer + X-Hub-Id).
    const result = await cloudLogin(emailVal.value.trim().toLowerCase(), passwordVal.value);
    setTokens(result.access, result.refresh);
    setUser({
      id: result.user.id,
      name: result.user.name,
      email: result.user.email,
      avatarUrl: result.user.avatarUrl ?? null,
    });

    // Si el usuario eligió "Confiar en este dispositivo", registramos el usuario
    // localmente y redirigimos al alta de PIN.
    if (trust.value) {
      const userEntry: TrustedUser = {
        id: result.user.id,
        name: result.user.name,
        email: result.user.email,
        initials: initials(result.user.name),
      };
      const existing = trustedUsers.value.filter((u) => u.id !== result.user.id);
      trustedUsers.value = [userEntry, ...existing];
      saveTrustedUsers(trustedUsers.value);
      saveTrustedFlag(true);
      trusted.value = true;
      // Solo pedimos crear PIN si el backend indica que es la primera vez o si
      // no hay PIN ya guardado para este usuario. Actualmente cloudLogin.firstTime
      // devuelve siempre false (el Cloud no expone este flag aún); lo dejamos como
      // hook para cuando el backend lo soporte.
      if (result.firstTime) {
        step.value = 'setup';
        return; // no navega aún; PinSetup navega tras confirmar el PIN
      }
    }

    const redirect = (router.currentRoute.value.query.redirect as string) || '/';
    await router.replace(redirect);
  } catch {
    // TODO: cablear cloud.ts login real cuando el Cloud esté accesible desde el hub.
    // Por ahora, en modo demo/sandbox usamos credenciales ficticias para probar el flujo.
    if ((import.meta.env.VITE_DEMO ?? '1') === '1') {
      setUser({ id: 'u1', name: emailVal.value || 'Demo Owner', email: emailVal.value || 'demo@erplora.com' });
      if (trust.value) {
        const userEntry: TrustedUser = {
          id: 'u1',
          name: emailVal.value || 'Demo Owner',
          email: emailVal.value || 'demo@erplora.com',
          initials: initials(emailVal.value || 'Demo Owner'),
        };
        trustedUsers.value = [userEntry];
        saveTrustedUsers(trustedUsers.value);
        saveTrustedFlag(true);
        trusted.value = true;
        step.value = 'setup';
        return;
      }
      const redirect = (router.currentRoute.value.query.redirect as string) || '/';
      await router.replace(redirect);
      return;
    }
    emailError.value = 'No se pudo iniciar sesión. Revisa tus credenciales o la conexión.';
  } finally {
    emailLoading.value = false;
  }
}

// ---------------------------------------------------------------------------
// PinLogin state
// ---------------------------------------------------------------------------
const pinUser = ref<TrustedUser | null>(
  trustedUsers.value.length === 1 ? trustedUsers.value[0] : null,
);
const pinValue = ref<string>('');
const pinError = ref<boolean>(false);

function selectPinUser(u: TrustedUser): void {
  pinUser.value = u;
  pinValue.value = '';
  pinError.value = false;
}

// Maneja el campo ion-input oculto del pinpad (path de accesibilidad)
function onPinInput(ev: Event): void {
  const val = (ev as CustomEvent<{ value: string }>).detail.value ?? '';
  const digits = val.replace(/\D/g, '').slice(0, 4);
  pinValue.value = digits;
  void checkPin(digits);
}

function pressKey(key: string): void {
  if (key === '') return;
  if (key === '⌫') {
    pinValue.value = pinValue.value.slice(0, -1);
    pinError.value = false;
    return;
  }
  if (pinValue.value.length >= 4) return;
  const next = pinValue.value + key;
  pinValue.value = next;
  void checkPin(next);
}

async function checkPin(pin: string): Promise<void> {
  if (pin.length < 4 || !pinUser.value) return;
  try {
    // TODO: cablear auth.loginPin(userId, pin) cuando el runtime Rust exponga
    // verificación de PIN local (ARQUITECTURA.md §2.9). Por ahora aceptamos
    // cualquier PIN de 4 dígitos en demo.
    const u = pinUser.value;
    setUser({ id: u.id, name: u.name, email: u.email ?? '' });
    const redirect = (router.currentRoute.value.query.redirect as string) || '/';
    await router.replace(redirect);
  } catch {
    pinError.value = true;
    pinValue.value = '';
  }
}

// ---------------------------------------------------------------------------
// PinSetup state
// ---------------------------------------------------------------------------
type SetupPhase = 'first' | 'confirm';
const setupPhase = ref<SetupPhase>('first');
const setupFirst = ref<string>('');
const setupConfirm = ref<string>('');
const setupError = ref<boolean>(false);

const currentSetupPin = computed<string>(() =>
  setupPhase.value === 'first' ? setupFirst.value : setupConfirm.value,
);

function pressSetupKey(key: string): void {
  if (key === '') return;
  const current = setupPhase.value === 'first' ? setupFirst : setupConfirm;
  if (key === '⌫') {
    current.value = current.value.slice(0, -1);
    setupError.value = false;
    return;
  }
  if (current.value.length >= 4) return;
  const next = current.value + key;
  current.value = next;
  if (next.length === 4) {
    void onSetupComplete(next);
  }
}

async function onSetupComplete(pin: string): Promise<void> {
  setupError.value = false;
  if (setupPhase.value === 'first') {
    setupFirst.value = pin;
    setupPhase.value = 'confirm';
  } else {
    if (pin === setupFirst.value) {
      // TODO: cablear auth.setupPin(pin) cuando el runtime Rust soporte PIN local.
      // Por ahora solo guardamos un flag de que el PIN fue creado (el PIN real se
      // verificará en el runtime cuando se implemente ARQUITECTURA.md §2.9).
      try { localStorage.setItem('erplora.pin_set', '1'); } catch { /* ignore */ }
      const redirect = (router.currentRoute.value.query.redirect as string) || '/';
      await router.replace(redirect);
    } else {
      setupError.value = true;
      setupFirst.value = '';
      setupConfirm.value = '';
      setupPhase.value = 'first';
    }
  }
}
</script>

<style scoped>
/* ---- Layout ---- */
.login-wrap {
  display: grid;
  place-items: center;
  min-height: 100%;
  padding: 40px 16px;
}
.login-box {
  width: min(92vw, 400px);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

/* ---- Botón tema ---- */
.theme-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
}

/* ---- Logo ---- */
.logo-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
  text-align: center;
}
.logo-mark {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: var(--ion-color-primary);
  color: #fff;
  font-size: 28px;
  font-weight: 700;
  display: grid;
  place-items: center;
}
.logo-sub {
  font-size: 14px;
  color: var(--ion-color-medium);
  margin: 0;
}

/* ---- Tarjeta ---- */
.login-card {
  width: 100%;
}

/* ---- Pasos ---- */
.step-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ---- Trust row ---- */
.trust-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.trust-label {
  font-size: 13.5px;
}
.trust-info-btn {
  margin: 0;
  height: 28px;
}

/* ---- Popover ---- */
.popover-content {
  padding: 12px;
  max-width: 260px;
}
.popover-title {
  font-weight: 600;
  margin: 0 0 4px;
  font-size: 13px;
}
.popover-body {
  font-size: 13px;
  line-height: 1.4;
  color: var(--ion-color-medium);
  margin: 0;
}

/* ---- Error note ---- */
.error-note {
  font-size: 13px;
  display: block;
}

/* ---- User grid (PIN selector) ---- */
.pin-choose-title {
  text-align: center;
}
.pin-choose-title p {
  font-size: 14px;
  margin: 0 0 8px;
}
.user-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.user-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  border-radius: 12px;
  border: 1px solid var(--ion-color-step-150, #dcdcdc);
  background: var(--ion-card-background, #fff);
  padding: 16px 8px;
  text-align: center;
  cursor: pointer;
  transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.user-card:hover {
  transform: translateY(-2px);
  border-color: var(--ion-color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
.user-card:active {
  transform: scale(0.98);
}
.user-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(20, 150, 214, 0.12);
  color: var(--ion-color-primary);
  font-size: 16px;
  font-weight: 600;
  display: grid;
  place-items: center;
}
.user-avatar--lg {
  width: 56px;
  height: 56px;
  font-size: 18px;
}
.user-name {
  font-size: 14px;
  font-weight: 600;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0;
}
.user-email {
  font-size: 11px;
  color: var(--ion-color-medium);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---- PIN user info ---- */
.pin-user-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 4px;
}
.change-user-btn {
  font-size: 12px;
  color: var(--ion-color-primary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-top: 4px;
}
.change-user-btn:hover {
  text-decoration: underline;
}

/* ---- PinPad ---- */
.pinpad-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.pinpad-dots {
  display: flex;
  gap: 16px;
  justify-content: center;
  padding: 8px 0;
}
.pinpad-dots--error .dot {
  border-color: var(--ion-color-danger);
}
.dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid var(--ion-color-medium);
  transition: background 0.15s, border-color 0.15s;
}
.dot.filled {
  background: var(--ion-color-primary);
  border-color: var(--ion-color-primary);
}
/* El ion-input del PIN es visualmente invisible; solo existe para accesibilidad */
.pin-hidden-input {
  opacity: 0;
  height: 0;
  pointer-events: none;
  position: absolute;
}
.pinpad-keys {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  width: 100%;
  max-width: 260px;
  margin: 0 auto;
}
.pin-key {
  height: 56px;
  border-radius: 12px;
  border: 1px solid var(--ion-color-step-150, #dcdcdc);
  background: var(--ion-card-background, #fff);
  font-size: 20px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.1s, transform 0.1s;
  display: grid;
  place-items: center;
}
.pin-key:hover:not(.pin-key--empty) {
  background: var(--ion-color-light);
}
.pin-key:active:not(.pin-key--empty) {
  transform: scale(0.93);
}
.pin-key--empty {
  visibility: hidden;
  pointer-events: none;
}

/* ---- Setup hint ---- */
.setup-hint {
  text-align: center;
}
.setup-hint p {
  font-size: 14px;
  margin: 0 0 4px;
}

/* ---- Footer note ---- */
.footer-note {
  margin-top: 24px;
  text-align: center;
  font-size: 12px;
  color: var(--ion-color-medium);
}
</style>
