<template>
  <ion-page>
    <!-- Sin ion-header en login (no hay menú ni barra de título). -->
    <ion-content>

      <!-- Botón de tema: esquina superior derecha -->
      <ion-button
        fill="clear"
        :aria-label="t('login.toggleTheme')"
        class="theme-btn"
        @click="toggleTheme"
      >
        <HubIcon slot="icon-only" :name="isDark ? 'sunny-outline' : 'moon-outline'" />
      </ion-button>

      <div class="login-wrap">
        <div class="login-box">

          <!-- Logo / cabecera -->
          <div class="logo-area">
            <!-- Logo de marca: el personalizado del hub si lo hay, si no el de ERPlora (local,
                offline-safe). Si la URL personalizada falla/está offline, cae al logo local. -->
            <img
              class="logo-img"
              :src="hubLogo"
              alt="ERPlora"
              decoding="async"
              @error="onLogoError"
            />
            <p class="logo-sub">
              <template v-if="step === 'setup'">{{ t('login.subtitleSetup') }}</template>
              <template v-else-if="step === 'pin'">{{ t('login.subtitlePin') }}</template>
              <template v-else>{{ t('login.subtitleEmail') }}</template>
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
                  <HubIcon name="keypad-outline" />
                  <ion-label>{{ t('login.tabPin') }}</ion-label>
                </ion-segment-button>
                <ion-segment-button value="email">
                  <HubIcon name="mail-outline" />
                  <ion-label>{{ t('login.tabEmail') }}</ion-label>
                </ion-segment-button>
              </ion-segment>

              <!-- Paso: login por email+contraseña -->
              <form v-if="step === 'email'" class="step-form" @submit.prevent="submitEmail">
                <ion-input
                  v-model="emailVal"
                  :label="t('login.emailLabel')"
                  label-placement="floating"
                  type="email"
                  autocomplete="username"
                  fill="outline"
                  :placeholder="t('login.emailPlaceholder')"
                  @ion-input="emailVal = ($event as CustomEvent<{ value: string }>).detail.value ?? ''"
                />
                <ion-input
                  v-model="passwordVal"
                  :label="t('login.passwordLabel')"
                  label-placement="floating"
                  type="password"
                  autocomplete="current-password"
                  fill="outline"
                  placeholder="••••••••"
                  @ion-input="passwordVal = ($event as CustomEvent<{ value: string }>).detail.value ?? ''"
                >
                  <ion-input-password-toggle slot="end"></ion-input-password-toggle>
                </ion-input>

                <!-- Checkbox "confiar en este dispositivo" + popover informativo -->
                <div class="trust-row">
                  <ion-checkbox
                    :checked="trust"
                    label-placement="end"
                    @ion-change="trust = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
                  >
                    <span class="trust-label">{{ t('login.trustDevice') }}</span>
                  </ion-checkbox>
                  <ion-button
                    id="trust-info-btn"
                    fill="clear"
                    size="small"
                    :aria-label="t('login.trustInfoAria')"
                    class="trust-info-btn"
                  >
                    <HubIcon slot="icon-only" name="information-circle-outline" />
                  </ion-button>
                  <ion-popover
                    trigger="trust-info-btn"
                    trigger-action="click"
                    side="top"
                    alignment="center"
                  >
                    <div class="popover-content">
                      <p class="popover-title">{{ t('login.popoverTitle') }}</p>
                      <!-- eslint-disable-next-line vue/no-v-html -->
                      <p class="popover-body" v-html="t('login.popoverBody')"></p>
                    </div>
                  </ion-popover>
                </div>

                <ion-note v-if="emailError" color="danger" class="error-note">
                  {{ emailError }}
                </ion-note>

                <ion-button type="submit" expand="block" :disabled="emailLoading">
                  <ion-spinner v-if="emailLoading" name="crescent" />
                  <template v-else>
                    <HubIcon slot="start" name="log-in-outline" />
                    {{ t('login.signIn') }}
                  </template>
                </ion-button>

                <ion-button
                  v-if="trusted && !showTabs"
                  fill="clear"
                  size="small"
                  @click="step = 'pin'"
                >
                  {{ t('login.usePinInstead') }}
                </ion-button>
              </form>

              <!-- Paso: login por PIN -->
              <div v-else-if="step === 'pin'" class="step-form">

                <!-- Paso 1: elegir usuario (cuando hay varios en el dispositivo) -->
                <template v-if="!pinUser">
                  <ion-text color="medium" class="pin-choose-title">
                    <p>{{ t('login.chooseUser') }}</p>
                  </ion-text>
                  <div class="user-scroll">
                    <div class="user-grid">
                      <ion-card
                        v-for="u in trustedUsers"
                        :key="u.id"
                        button
                        class="user-card"
                        @click="selectPinUser(u)"
                      >
                        <ion-card-content class="ion-text-center">
                          <ok-avatar :name="u.name" size="lg"></ok-avatar>
                          <p class="user-name">{{ u.name }}</p>
                          <p v-if="u.email" class="user-email">{{ u.email }}</p>
                        </ion-card-content>
                      </ion-card>
                    </div>
                  </div>
                  <ion-button
                    v-if="!showTabs"
                    fill="clear"
                    size="small"
                    @click="step = 'email'"
                  >
                    {{ t('login.signInWithEmail') }}
                  </ion-button>
                </template>

                <!-- Paso 2: introducir PIN del usuario elegido -->
                <template v-else>
                  <div class="pin-user-info">
                    <ok-avatar :name="pinUser.name" size="lg"></ok-avatar>
                    <p class="user-name mt-2">{{ pinUser.name }}</p>
                  </div>

                  <!-- ok-pinpad: pantalla (4 círculos), teclado y, si hay varios usuarios,
                       tecla «cambiar usuario» (flecha a la izquierda del 0; borrado a la derecha). -->
                  <div class="pinpad-wrap">
                    <ok-pinpad
                      ref="mainPinpadRef"
                      dots
                      :length="4"
                      :error="pinError"
                      secondary-icon="arrow-back-outline"
                      :secondary-label="t('login.changeUser')"
                      @ok-input="onMainPinInput"
                      @ok-complete="onMainPinComplete"
                      @ok-secondary="onChangeUser"
                    ></ok-pinpad>
                  </div>

                  <ion-note v-if="pinError" color="danger" class="error-note">
                    {{ t('login.pinIncorrect') }}
                  </ion-note>
                  <ion-button
                    v-if="!showTabs"
                    fill="clear"
                    size="small"
                    @click="onPinToEmail"
                  >
                    {{ t('login.signInWithEmail') }}
                  </ion-button>
                </template>
              </div>

              <!-- Paso: alta del PIN (primer login con "Confiar en este dispositivo") -->
              <div v-else-if="step === 'setup'" class="step-form">
                <ion-text color="medium" class="setup-hint">
                  <p>{{ setupPhase === 'first' ? t('login.setupChoosePin') : t('login.setupConfirmPin') }}</p>
                </ion-text>

                <!-- ok-pinpad reutilizado para el alta de PIN. -->
                <div class="pinpad-wrap">
                  <ok-pinpad
                    ref="setupPinpadRef"
                    dots
                    :length="4"
                    :error="setupError"
                    @ok-complete="onSetupPinComplete"
                  ></ok-pinpad>
                </div>

                <ion-note v-if="setupError" color="danger" class="error-note">
                  {{ t('login.setupMismatch') }}
                </ion-note>
              </div>

            </ion-card-content>
          </ion-card>

          <p class="footer-note">
            ERPlora · {{ step === 'pin' ? t('login.footerTrustedDevice') : t('login.footerSecureCloud') }}
          </p>

        </div>
      </div>

    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonPage, IonContent, IonCard, IonCardContent, IonButton,
  IonInput, IonInputPasswordToggle, IonCheckbox, IonText, IonSpinner, IonSegment, IonSegmentButton,
  IonLabel, IonPopover, IonNote
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import { setUser, setHubSession, getHubSession } from '../lib/session';
import { cloudLogin, setTokens, runtimeCloudSession, runtimePinLogin, runtimeSetPin } from '../lib/cloud';
import { config } from '../lib/config';
import { isTauri, invokeTauri } from '../lib/device';
import { pinUsers } from '../lib/runtime';
import { isDark, toggleTheme } from '../lib/theme';
import { hubLogo, DEFAULT_HUB_LOGO } from '../lib/branding';

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------
type Step = 'pin' | 'email' | 'setup';

const { t } = useI18n();

interface TrustedUser {
  id: string;
  name: string;
  email?: string;
  initials: string;
}

// ---------------------------------------------------------------------------
// Tema: estado compartido (lib/theme) — mismo modo que el toggle de la topbar.
// ---------------------------------------------------------------------------
// `isDark` / `toggleTheme` se importan de lib/theme (ver imports del SFC).

// ---------------------------------------------------------------------------
// Logo de marca (lib/branding): `hubLogo` = el del hub si lo hay, si no el de ERPlora local.
// Si la URL personalizada falla (rota / offline), caemos al logo local horneado.
// ---------------------------------------------------------------------------
function onLogoError(ev: Event): void {
  const img = ev.target as HTMLImageElement;
  if (!img.src.endsWith(DEFAULT_HUB_LOGO)) img.src = DEFAULT_HUB_LOGO;
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

// El RUNTIME (`GET /api/hub/context` → pin_users) es la AUTORIDAD de quién puede hacer login local
// por PIN. localStorage NO añade usuarios: solo **decora** con email/iniciales (hub_user no guarda
// email), cacheados del login cloud y pegados a la entrada del runtime que coincida por id. Antes se
// "conservaban" los de localStorage ausentes del runtime → podía resucitar usuarios obsoletos
// (drift); ya no. El flujo de seguridad (§2.9) NO cambia: esto solo decide qué pestaña se muestra;
// la pestaña Email sigue disponible. `immediate` cubre el caso ya resuelto.
watch(
  pinUsers,
  (users) => {
    if (!users.length || step.value === 'setup') return;
    const cachedById = new Map(trustedUsers.value.map((u) => [u.id, u]));
    trustedUsers.value = users.map((u) => ({
      id: u.id,
      name: u.name,
      initials: initials(u.name),
      email: cachedById.get(u.id)?.email,
    }));
    trusted.value = true;
    step.value = 'pin';
  },
  { immediate: true },
);

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

    // Primer login = el Cloud crea/resuelve el Hub de ESTE dispositivo y devuelve su hub_id real
    // (ARQUITECTURA.md §2.9b). Lo adoptamos como X-Hub-Id ANTES de activar la sesión, para que el
    // gate de entitlement (App.vue → resolveEntitlement) deje de pegar contra el hub placeholder.
    // En Tauri, además, ENROLAMOS el dispositivo: el shell pide el token de máquina al Cloud y
    // persiste token + hub_id real en disco (hot-reload del runtime embebido), así el catálogo de
    // Apps/entitlement firman con la identidad real sin depender de un JWT fresco. Best-effort: si el
    // enroll falla, el JWT del usuario ya autoriza por IsHubMember.
    if (result.hubId) {
      config.hubId = result.hubId;
      if (isTauri()) {
        await invokeTauri('enroll_device', {
          hubId: result.hubId,
          accessToken: result.access,
        }).catch(() => null);
      }
    }

    setTokens(result.access, result.refresh);

    // Abre la sesión LOCAL del runtime a partir del JWT (autoridad de permisos local, §2.9).
    // El `name` se reusa para el login por PIN (el runtime resuelve el usuario por nombre).
    const sess = await runtimeCloudSession(result.access, result.user.name);
    setHubSession(sess.token);

    setUser({
      id: result.user.id,
      name: result.user.name,
      email: result.user.email,
      avatarUrl: result.user.avatarUrl ?? null,
      // Rol LOCAL resuelto por el runtime (autoridad de permisos, §2.9) → gatea la UI admin.
      role: sess.user.role
    });

    // Si el usuario eligió "Confiar en este dispositivo", registramos el usuario localmente y
    // vamos al alta de PIN (el PIN se fija en el runtime al confirmar — onSetupComplete).
    if (trust.value) {
      const userEntry: TrustedUser = {
        id: result.user.id,
        name: result.user.name,
        email: result.user.email,
        initials: initials(result.user.name)
      };
      const existing = trustedUsers.value.filter((u) => u.id !== result.user.id);
      trustedUsers.value = [userEntry, ...existing];
      saveTrustedUsers(trustedUsers.value);
      saveTrustedFlag(true);
      trusted.value = true;
      step.value = 'setup';
      return; // no navega aún; onSetupComplete navega tras fijar el PIN en el runtime
    }

    const redirect = (router.currentRoute.value.query.redirect as string) || '/';
    await router.replace(redirect);
  } catch {
    // Fallback demo SOLO con VITE_DEMO=1 (config.demo). En prod (sin la flag) el login falla
    // duro y mostramos el error real — nunca creamos una sesión ficticia.
    if (config.demo) {
      setUser({ id: 'u1', name: emailVal.value || 'Demo Owner', email: emailVal.value || 'demo@erplora.com' });
      if (trust.value) {
        const userEntry: TrustedUser = {
          id: 'u1',
          name: emailVal.value || 'Demo Owner',
          email: emailVal.value || 'demo@erplora.com',
          initials: initials(emailVal.value || 'Demo Owner')
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
    emailError.value = t('login.errorSignIn');
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
// Referencia al <ok-pinpad> del paso PIN (para limpiar su valor tras error / cambiar usuario).
const mainPinpadRef = ref<(HTMLElement & { value: string }) | null>(null);

function selectPinUser(u: TrustedUser): void {
  pinUser.value = u;
  pinValue.value = '';
  pinError.value = false;
}

// Eventos del ok-pinpad (el componente pinta los círculos y gestiona el teclado).
function onMainPinInput(ev: Event): void {
  pinValue.value = (ev as CustomEvent<{ value: string }>).detail.value ?? '';
  pinError.value = false;
}
function onMainPinComplete(ev: Event): void {
  const pin = (ev as CustomEvent<{ value: string }>).detail.value ?? '';
  void checkPin(pin);
}
// Tecla secundaria del pinpad (flecha atrás) → volver a elegir usuario.
function onChangeUser(): void {
  pinUser.value = null;
  pinValue.value = '';
  pinError.value = false;
  if (mainPinpadRef.value) mainPinpadRef.value.value = '';
}
// "Iniciar sesión con email" desde el paso PIN.
function onPinToEmail(): void {
  step.value = 'email';
  pinUser.value = null;
  pinValue.value = '';
  pinError.value = false;
}

async function checkPin(pin: string): Promise<void> {
  if (pin.length < 4 || !pinUser.value) return;
  try {
    // Login local por PIN contra el runtime (§2.9): verifica el PIN y abre sesión server-side.
    const u = pinUser.value;
    const sess = await runtimePinLogin(u.name, pin);
    setHubSession(sess.token);
    // Rol LOCAL del runtime (mismo que el gate del backend) → gatea la UI admin (pestaña API keys).
    setUser({ id: u.id, name: u.name, email: u.email ?? '', role: sess.user.role });
    const redirect = (router.currentRoute.value.query.redirect as string) || '/';
    await router.replace(redirect);
  } catch {
    pinError.value = true;
    pinValue.value = '';
    // Limpia los círculos del ok-pinpad para reintentar.
    if (mainPinpadRef.value) mainPinpadRef.value.value = '';
  }
}

// ---------------------------------------------------------------------------
// PinSetup state
// ---------------------------------------------------------------------------
type SetupPhase = 'first' | 'confirm';
const setupPhase = ref<SetupPhase>('first');
const setupFirst = ref<string>('');
const setupError = ref<boolean>(false);
// Referencia al <ok-pinpad> del alta de PIN (para limpiar entre fases / errores).
const setupPinpadRef = ref<(HTMLElement & { value: string }) | null>(null);

function clearSetupPinpad(): void {
  if (setupPinpadRef.value) setupPinpadRef.value.value = '';
}

// Evento ok-complete del pinpad de alta: recibe el PIN completo de 4 dígitos.
function onSetupPinComplete(ev: Event): void {
  const pin = (ev as CustomEvent<{ value: string }>).detail.value ?? '';
  void onSetupComplete(pin);
}

async function onSetupComplete(pin: string): Promise<void> {
  setupError.value = false;
  if (setupPhase.value === 'first') {
    // Fase 1: guarda el primer PIN y pasa a confirmación (limpia el teclado).
    setupFirst.value = pin;
    setupPhase.value = 'confirm';
    clearSetupPinpad();
    return;
  }
  // Fase 2: confirmar contra el primero.
  if (pin === setupFirst.value) {
    // Fija el PIN en el runtime para el usuario de la sesión actual (§2.9). Requiere la sesión
    // abierta en el login cloud previo (X-Hub-Session).
    const session = getHubSession();
    try {
      if (session) await runtimeSetPin(pin, session);
      const redirect = (router.currentRoute.value.query.redirect as string) || '/';
      await router.replace(redirect);
    } catch {
      setupError.value = true;
      setupFirst.value = '';
      setupPhase.value = 'first';
      clearSetupPinpad();
    }
  } else {
    setupError.value = true;
    setupFirst.value = '';
    setupPhase.value = 'first';
    clearSetupPinpad();
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
.logo-img {
  height: 56px;
  width: auto;
  max-width: 200px;
  object-fit: contain;
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
/* Card de tamaño FIJO: todos los pasos (email / pin / setup / selección de usuario)
 * reservan la misma altura, así no hay salto al cambiar entre pestañas. El paso más
 * alto es el del teclado PIN (~411px); reservamos algo más y centramos el contenido. */
.step-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  /* Altura FIJA: misma en email / pin / setup / selección → sin salto al cambiar de paso.
   * Cabe el paso más alto (teclado PIN ~411px). El contenido se alinea arriba y, en la
   * selección de usuario, la lista scrollea dentro (ver .user-grid). */
  height: 26rem;
  /* Formulario (email / PIN / setup) CENTRADO vertical. En la selección de usuario,
   * el .user-scroll lleva flex:1 y rellena el alto, así sus cards quedan ARRIBA. */
  justify-content: center;
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
/* Contenedor de scroll: ocupa el alto restante del card (fijo) y scrollea dentro. */
.user-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  /* Hueco para la barra de scroll sin tapar las cards. */
  padding-right: 4px;
}
.user-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  /* Filas a su altura natural (sin aplastar); el scroll lo hace .user-scroll. */
  align-content: start;
}
/* Cada perfil es un ion-card (button): solo reseteamos el margen para encajar en la rejilla. */
.user-card {
  margin: 0;
}
.user-card .user-name {
  margin-top: 8px;
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
  margin: 2px 0 0;
}

/* ---- PIN user info ---- */
.pin-user-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 4px;
}

/* ---- PinPad (wrapper del ok-pinpad: solo centra) ---- */
.pinpad-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
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
