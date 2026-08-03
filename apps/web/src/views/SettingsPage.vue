<template>
  <AppPage :title="t('nav.settings')" content-layout="detail">
      <!-- ── Tab: Hub ── -->
      <template v-if="tab === 'hub'">
        <h2 class="text-base font-semibold mb-2 px-1">{{ t('settings.hubWide') }}</h2>
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- País fiscal GLOBAL del negocio. Persistido como ISO-3166 en hub_settings; no es
                   un selector de “tipo de negocio” ni un dato local del navegador. -->
              <ion-item>
                <HubIcon slot="start" name="business-outline" />
                <ion-label>
                  <h2>{{ t('settings.country') }}</h2>
                  <p>{{ t('settings.countryDesc') }}</p>
                </ion-label>
                <ion-select
                  v-if="isAdmin"
                  v-model="hubCountry"
                  interface="popover"
                  :aria-label="t('settings.country')"
                  slot="end"
                  @ion-change="onCountryChange($event.detail.value as string)"
                >
                  <ion-select-option value="ES">{{ t('settings.countrySpain') }}</ion-select-option>
                  <ion-select-option value="PT">{{ t('settings.countryPortugal') }}</ion-select-option>
                </ion-select>
                <ion-note v-else slot="end">{{ hubCountry }}</ion-note>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>

        <!-- Ajustes GLOBALES del hub (server-side, /api/settings): moneda + idioma DEFAULT + doc API.
             Solo editables por admin (PUT exige owner/admin); para el resto, valores en solo-lectura. -->
        <ion-card class="mt-3">
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- Moneda del hub (GLOBAL, sin override por usuario). -->
              <ion-item>
                <HubIcon slot="start" name="cash-outline" />
                <ion-label>
                  <h2>{{ t('settings.currency') }}</h2>
                  <p>{{ t('settings.currencyDesc') }}</p>
                </ion-label>
                <ion-select
                  v-if="isAdmin"
                  v-model="hubCurrency"
                  interface="popover"
                  :aria-label="t('settings.currency')"
                  slot="end"
                  @ion-change="onCurrencyChange($event.detail.value as string)"
                >
                  <ion-select-option v-for="c in CURRENCIES" :key="c.code" :value="c.code">
                    {{ c.code }} · {{ c.name }}
                  </ion-select-option>
                </ion-select>
                <ion-note v-else slot="end">{{ hubCurrency }}</ion-note>
              </ion-item>

              <!-- Idioma DEFAULT del hub (server). Distinto del idioma PERSONAL de arriba: este es el
                   que ven los usuarios sin override propio. -->
              <ion-item>
                <HubIcon slot="start" name="globe-outline" />
                <ion-label>
                  <h2>{{ t('settings.hubLanguage') }}</h2>
                  <p>{{ t('settings.hubLanguageDesc') }}</p>
                </ion-label>
                <ion-select
                  v-if="isAdmin"
                  v-model="hubLanguage"
                  interface="popover"
                  :aria-label="t('settings.hubLanguage')"
                  slot="end"
                  @ion-change="onHubLanguageChange($event.detail.value as Locale)"
                >
                  <ion-select-option v-for="l in availableLocales" :key="l.code" :value="l.code">
                    {{ l.name }}
                  </ion-select-option>
                </ion-select>
                <ion-note v-else slot="end">{{ hubLanguageName }}</ion-note>
              </ion-item>

              <!-- Paleta DEFAULT del hub (GLOBAL, hub_settings.theme_palette — ADR-0138): la que
                   ven los usuarios SIN override local. Solo admin; persiste al instante como la
                   moneda. -->
              <ion-item lines="none">
                <HubIcon slot="start" name="color-palette-outline" />
                <ion-label>
                  <h2>{{ t('settings.hubPalette') }}</h2>
                  <p>{{ t('settings.hubPaletteDesc') }}</p>
                </ion-label>
                <ion-note v-if="!isAdmin" slot="end">{{ hubPalette }}</ion-note>
              </ion-item>
              <div v-if="isAdmin" class="ion-padding-horizontal ion-padding-bottom">
                <ok-theme-picker
                  hide-mode
                  :palette="hubPalette"
                  :labels.prop="pickerLabels"
                  @ok-change="onHubPaletteChange"
                ></ok-theme-picker>
              </div>
            </ion-list>
          </ion-card-content>
        </ion-card>

        <!-- Mostrar documentación de la API (ADR-0057 §4): setting GLOBAL del hub (server-side) que
             muestra/oculta la entrada de menú + la página Swagger. Solo lo cambia un admin; la
             seguridad real es el gate de sesión sobre openapi.json en el runtime. -->
        <ion-card class="mt-3">
          <ion-card-content class="p-0">
            <ion-item lines="none">
              <HubIcon slot="start" name="code-slash-outline" />
              <ion-label>
                <h2>{{ t('settings.showApiDocs') }}</h2>
                <p>{{ t('settings.showApiDocsDesc') }}</p>
              </ion-label>
              <ion-toggle
                :checked="showApiDocs"
                :disabled="!isAdmin"
                :aria-label="t('settings.showApiDocs')"
                @ion-change="onApiDocsToggle($event)"
                slot="end"
              />
            </ion-item>
          </ion-card-content>
        </ion-card>

        <h2 class="text-base font-semibold mt-4 mb-2 px-1">{{ t('settings.hardware') }}</h2>

        <!-- ERPlora Bridge -->
        <ion-card>
          <ion-card-content class="p-0">
            <ion-item button detail lines="none">
              <HubIcon slot="start" name="extension-puzzle-outline" />
              <ion-label>
                <h2>ERPlora Bridge</h2>
                <p>{{ t('settings.bridgeDesc') }}</p>
              </ion-label>
              <ion-note slot="end">{{ t('settings.disabled') }}</ion-note>
            </ion-item>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Negocio (identidad fiscal genérica) ── -->
      <template v-else-if="tab === 'tax'">
        <!-- Identidad de NEGOCIO GLOBAL (fuente única país-agnóstica, ADR-0061): identificador fiscal
             (NIF/CIF/VAT…) + razón social + dirección. La leen invoice (emisor) y los módulos fiscales
             por país. Lo específico de país (IVA/IGIC, e-factura) vive en módulos, no aquí. Solo admin. -->
        <ion-card>
          <ion-card-content>
            <ion-label>
              <h2>{{ t('settings.fiscalIdentity') }}</h2>
              <p>{{ t('settings.fiscalIdentityDesc') }}</p>
            </ion-label>
            <ion-input
              class="mt-2"
              fill="outline"
              label-placement="floating"
              :label="t('settings.fiscalNif')"
              :readonly="!isAdmin"
              v-model="businessTaxId"
              placeholder="B12345678 · FR…"
            />
            <ion-input
              class="mt-2"
              fill="outline"
              label-placement="floating"
              :label="t('settings.fiscalName')"
              :readonly="!isAdmin"
              v-model="businessLegalName"
              placeholder="Mi Empresa SL"
            />
            <ion-textarea
              class="mt-2"
              fill="outline"
              label-placement="floating"
              :label="t('settings.fiscalAddress')"
              :readonly="!isAdmin"
              auto-grow
              v-model="businessAddress"
            />
          </ion-card-content>
        </ion-card>

        <ion-button v-if="isAdmin" class="mt-3" expand="block" @click="saveTaxSettings">
          <HubIcon slot="start" name="save-outline" />
          {{ t('settings.saveChanges') }}
        </ion-button>

        <!-- Certificado fiscal (.p12): recurso del NEGOCIO/hub (no del módulo verifactu). Se sube
             aquí, junto al VAT y el nombre de la tienda. El runtime es la autoridad: solo guarda el
             estado vía GET, nunca devuelve los bytes; PUT/DELETE son solo admin (401 si no). -->
        <ion-card class="mt-3">
          <ion-card-content>
            <ion-label>
              <h2>{{ t('settings.certTitle') }}</h2>
              <p>{{ t('settings.certDesc') }}</p>
            </ion-label>

            <ion-item lines="none" class="mt-2">
              <HubIcon
                slot="start"
                :name="cert.present ? 'shield-checkmark-outline' : 'shield-outline'"
              />
              <ion-label>
                <p v-if="cert.present">
                  {{ t('settings.certPresent', { date: certUploadedLabel }) }}
                </p>
                <p v-else>{{ t('settings.certAbsent') }}</p>
                <p v-if="cert.present && cert.subject">{{ cert.subject }}</p>
              </ion-label>
            </ion-item>

            <!-- Selector de fichero oculto disparado por un ion-button (patrón estándar CSP-safe). -->
            <input
              ref="certFileInput"
              type="file"
              accept=".p12,.pfx"
              class="cert-file-input"
              @change="onCertFileChange"
            />

            <ion-button
              expand="block"
              fill="outline"
              class="mt-2"
              :disabled="!isAdmin"
              @click="triggerCertFilePicker"
            >
              <HubIcon slot="start" name="document-attach-outline" />
              {{ certFileName || t('settings.certChooseFile') }}
            </ion-button>

            <ion-input
              class="mt-2"
              type="password"
              fill="outline"
              label-placement="floating"
              :label="t('settings.certPassword')"
              :disabled="!isAdmin"
              v-model="certPassword"
            />

            <ion-button
              expand="block"
              class="mt-3"
              :disabled="!isAdmin || certBusy"
              @click="uploadCert"
            >
              <HubIcon slot="start" name="cloud-upload-outline" />
              {{ t('settings.certUpload') }}
            </ion-button>

            <ion-button
              v-if="cert.present"
              expand="block"
              color="danger"
              fill="outline"
              class="mt-2"
              :disabled="!isAdmin || certBusy"
              @click="removeCert"
            >
              <HubIcon slot="start" name="trash-outline" />
              {{ t('settings.certDelete') }}
            </ion-button>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Comunicaciones ── -->
      <template v-else-if="tab === 'communications'">
        <ion-card>
          <ion-card-content>
            <ion-label>
              <h2>{{ t('settings.emailChannelTitle') }}</h2>
              <p>{{ t('settings.emailChannelDesc') }}</p>
            </ion-label>

            <ion-item lines="none" class="mt-2">
              <HubIcon slot="start" :name="emailStatus.connected ? 'checkmark-circle-outline' : 'alert-circle-outline'" />
              <ion-label>
                <h2>{{ emailModeLabel }}</h2>
                <p>{{ emailStatus.connected ? t('settings.emailReady') : t('settings.emailError') }}</p>
                <p v-if="emailStatus.last_error">{{ emailStatus.last_error }}</p>
              </ion-label>
            </ion-item>

            <ion-select
              class="mt-2"
              fill="outline"
              label-placement="floating"
              :label="t('settings.emailProvider')"
              interface="popover"
              :disabled="!isAdmin || emailBusy"
              v-model="emailForm.mode"
            >
              <ion-select-option value="managed">{{ t('settings.emailManaged') }}</ion-select-option>
              <ion-select-option value="google_oauth">Google</ion-select-option>
              <ion-select-option value="microsoft_oauth">Microsoft</ion-select-option>
              <ion-select-option value="smtp">SMTP</ion-select-option>
            </ion-select>

            <p v-if="emailForm.mode === 'managed'" class="communication-hint mt-2">
              {{ t('settings.emailManagedDesc') }}
            </p>

            <template v-else-if="emailForm.mode === 'google_oauth' || emailForm.mode === 'microsoft_oauth'">
              <p class="communication-hint mt-2">{{ t('settings.emailOauthDesc') }}</p>
              <ion-button
                expand="block"
                fill="outline"
                class="mt-2"
                :disabled="!isAdmin || emailBusy"
                @click="connectEmailOauth"
              >
                <HubIcon slot="start" name="log-in-outline" />
                {{ t('settings.emailConnectAccount', { provider: emailForm.mode === 'google_oauth' ? 'Google' : 'Microsoft' }) }}
              </ion-button>
              <ion-note v-if="emailStatus.account_email" class="block mt-2">
                {{ t('settings.emailConnectedAs', { email: emailStatus.account_email }) }}
              </ion-note>
            </template>

            <template v-else>
              <div class="communication-grid mt-2">
                <ion-input fill="outline" label-placement="floating" :label="t('settings.smtpHost')" :readonly="!isAdmin" v-model="emailForm.host" />
                <ion-input fill="outline" label-placement="floating" :label="t('settings.smtpPort')" type="number" :readonly="!isAdmin" v-model="emailForm.port" />
                <ion-select fill="outline" label-placement="floating" :label="t('settings.smtpSecurity')" interface="popover" :disabled="!isAdmin" v-model="emailForm.security">
                  <ion-select-option value="tls">TLS</ion-select-option>
                  <ion-select-option value="starttls">STARTTLS</ion-select-option>
                  <ion-select-option value="none">{{ t('settings.smtpNone') }}</ion-select-option>
                </ion-select>
                <ion-input fill="outline" label-placement="floating" :label="t('settings.smtpUsername')" :readonly="!isAdmin" v-model="emailForm.username" />
                <ion-input fill="outline" label-placement="floating" :label="t('settings.smtpPassword')" type="password" :readonly="!isAdmin" v-model="emailForm.password" :placeholder="emailStatus.has_secret ? t('settings.smtpPasswordKeep') : ''" />
                <ion-input fill="outline" label-placement="floating" :label="t('settings.emailFromName')" :readonly="!isAdmin" v-model="emailForm.from_name" />
                <ion-input fill="outline" label-placement="floating" :label="t('settings.emailFromAddress')" type="email" :readonly="!isAdmin" v-model="emailForm.from_email" />
              </div>
            </template>

            <ion-input
              v-if="emailForm.mode !== 'google_oauth' && emailForm.mode !== 'microsoft_oauth'"
              class="mt-2"
              fill="outline"
              label-placement="floating"
              :label="t('settings.emailReplyTo')"
              type="email"
              :readonly="!isAdmin"
              v-model="emailForm.reply_to"
            />

            <ion-button v-if="isAdmin && emailForm.mode !== 'google_oauth' && emailForm.mode !== 'microsoft_oauth'" expand="block" class="mt-3" :disabled="emailBusy" @click="saveEmailChannel">
              <HubIcon slot="start" name="save-outline" />
              {{ t('settings.saveChanges') }}
            </ion-button>
            <ion-button v-if="isAdmin" expand="block" fill="outline" class="mt-2" :disabled="emailBusy || !emailStatus.connected" @click="sendEmailTest">
              <HubIcon slot="start" name="paper-plane-outline" />
              {{ t('settings.emailSendTest') }}
            </ion-button>
            <ion-button v-if="isAdmin && emailStatus.mode !== 'managed'" expand="block" fill="clear" color="danger" class="mt-2" :disabled="emailBusy" @click="disconnectEmail">
              {{ t('settings.emailDisconnect') }}
            </ion-button>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Tickets ── -->
      <template v-else-if="tab === 'tickets'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-item button detail lines="none">
              <HubIcon slot="start" name="ticket-outline" />
              <ion-label>
                <h2>{{ t('settings.receiptTemplate') }}</h2>
                <p>{{ t('settings.receiptTemplateDesc') }}</p>
              </ion-label>
            </ion-item>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Permisos (capabilities de módulo, default-deny) ── -->
      <!-- Lista los módulos instalados que DECLARAN permisos; por cada uno, un toggle por capability.
           El runtime es la autoridad (PUT solo admin → 401 si no); aquí el gate `:disabled` es solo
           cosmético. La gestión autoritativa de permisos vive AQUÍ (el modal de Apps es un
           atajo de consentimiento al instalar). -->
      <template v-else-if="tab === 'permissions'">
        <ion-card>
          <ion-card-content>
            <ion-label>
              <h2>{{ t('settings.permissionsTitle') }}</h2>
              <p>{{ t('settings.permissionsDesc') }}</p>
              <p v-if="!isAdmin" class="mt-1">{{ t('settings.permissionsAdminOnly') }}</p>
            </ion-label>
          </ion-card-content>
        </ion-card>

        <div v-if="permsLoading" class="flex justify-center py-6">
          <ion-spinner name="dots" />
        </div>

        <ion-card v-else-if="modulesWithCaps.length === 0">
          <ion-card-content>
            <ok-empty-state
              icon="shield-checkmark-outline"
              :message="t('settings.permissionsNoModules')"
            />
          </ion-card-content>
        </ion-card>

        <ion-card v-for="m in modulesWithCaps" :key="m.moduleId" class="mt-3">
          <ion-card-content class="p-0">
            <ion-list-header>
              <ion-label>{{ m.name }}</ion-label>
            </ion-list-header>
            <ion-list lines="none">
              <ion-item v-for="cap in m.capabilities" :key="cap.id">
                <ion-label>
                  <h2>{{ cap.label }}</h2>
                  <p>{{ cap.description }}</p>
                </ion-label>
                <ion-toggle
                  :checked="cap.granted"
                  :disabled="!isAdmin"
                  :aria-label="`${cap.label} · ${m.name}`"
                  slot="end"
                  @ion-change="onCapabilityToggle(m, cap, $event)"
                />
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Datos: importar / exportar el hub (ADR-0113; decisión humano 2026-07-12) ──
           Import y export viven JUNTOS en esta pestaña de la navegación secundaria de Ajustes
           (antes eran las páginas /import y /export). Deep-link: /settings?tab=data. Un sub-segment
           elige entre importar (por defecto) y exportar (decisión humano 2026-07-17). -->
      <template v-else-if="tab === 'data'">
        <DataPanel :initial="dataView" />
      </template>
    <!-- Footer tab bar -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment class="ok-tabbar" :value="tab" @ion-change="tab = ($event.detail.value as Tab)">
          <ion-segment-button value="hub">
            <HubIcon name="business-outline" />
            <ion-label>{{ t('settings.tabHub') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="tax">
            <HubIcon name="wallet-outline" />
            <ion-label>{{ t('settings.tabTax') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="communications">
            <HubIcon name="mail-outline" />
            <ion-label>{{ t('settings.tabCommunications') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="tickets">
            <HubIcon name="ticket-outline" />
            <ion-label>{{ t('settings.tabTickets') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="permissions">
            <HubIcon name="shield-checkmark-outline" />
            <ion-label>{{ t('settings.tabPermissions') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="data" data-testid="settings-tab-data">
            <HubIcon name="swap-vertical-outline" />
            <ion-label>{{ t('settings.tabData') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonFooter,
  IonToolbar,
  IonSegment,
  IonSegmentButton,
  IonCard,
  IonCardContent,
  IonList,
  IonItem,
  IonLabel,
  IonNote,
  IonSelect,
  IonSelectOption,
  IonToggle,
  IonButton,
  IonInput,
  IonTextarea,
  IonSpinner,
  IonListHeader,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import DataPanel from '../components/DataPanel.vue';
import { bootHubLanguage, availableLocales, type Locale } from '../i18n';
import { apiDocsEnabled } from '../lib/api-docs';
import { isAdmin } from '../lib/session';
import { resolveSettingsTab, type SettingsTab } from '../lib/settings-tabs';
import { hubSettings, getHubSettings, updateHubSettings, type HubSettings } from '../lib/hub-settings';
import { publishHubCurrency } from '../lib/money';
import { toastSuccess, toastError } from '../lib/toast';
import {
  listInstalledModules,
  getModuleCapabilities,
  putModuleCapabilities,
  getBusinessCertificate,
  putBusinessCertificate,
  deleteBusinessCertificate,
  getEmailChannel,
  putEmailChannel,
  disconnectEmailChannel,
  testEmailChannel,
  beginEmailOauth,
  type ModuleCapability,
  type BusinessCertificate,
  type EmailChannelStatus,
  type EmailChannelInput,
} from '../lib/runtime';

const { t } = useI18n();

type Tab = SettingsTab;

// Deep-link a una pestaña por HASH (/settings#permisos) — la ruta base no cambia, así Ionic
// no trata el cambio de pestaña como página secundaria (no se desmonta el tabbar ni hay botón back).
// Compat: #store (pestaña Tienda retirada por duplicar Hub) se normaliza a #hub.
const route = useRoute();
const router = useRouter();
const initialTab = resolveSettingsTab(route.hash);
const tab = ref<Tab>(initialTab);
if (route.hash && route.hash !== `#${initialTab}`) {
  void router.replace({ hash: `#${initialTab}` });
}
// Al cambiar de pestaña, sincroniza el hash (replace = no apila historial; "atrás" sale de Ajustes).
watch(tab, (value) => {
  if (value !== (route.hash.slice(1) || 'hub')) void router.replace({ hash: `#${value}` });
});
// Back/forward y deep-links: si el hash cambia, actualiza el tab local.
watch(() => route.hash, (h) => {
  const next = resolveSettingsTab(h);
  if (next !== tab.value) tab.value = next;
  if (h && h !== `#${next}`) void router.replace({ hash: `#${next}` });
});

// Vista inicial del sub-segment de Datos: importar por defecto (lo habitual); ?data=export permite
// aterrizar en exportar desde un deep-link.
const dataView: 'import' | 'export' = route.query.data === 'export' ? 'export' : 'import';

// Monedas ISO-4217 ofrecidas (lista razonable; EUR por defecto). El runtime acepta cualquier ISO.
const CURRENCIES: { code: string; name: string }[] = [
  { code: 'EUR', name: 'Euro' },
  { code: 'USD', name: 'US Dollar' },
  { code: 'GBP', name: 'Pound Sterling' },
  { code: 'CHF', name: 'Swiss Franc' },
  { code: 'SEK', name: 'Swedish Krona' },
  { code: 'NOK', name: 'Norwegian Krone' },
  { code: 'DKK', name: 'Danish Krone' },
  { code: 'PLN', name: 'Polish Złoty' },
  { code: 'MXN', name: 'Mexican Peso' },
  { code: 'BRL', name: 'Brazilian Real' },
];

// ── Estado: Hub-wide (server-side, /api/settings) ──
// Moneda GLOBAL del hub e idioma DEFAULT del hub. Se siembran de la cache (boot) y se refrescan en
// onMounted; persisten al cambiar (solo admin) vía updateHubSettings.
const hubCurrency = ref<string>(hubSettings.value?.currency ?? 'EUR');
const hubLanguage = ref<Locale>(hubSettings.value?.language ?? 'es');
// Paleta GLOBAL del hub (ADR-0138): la default para usuarios sin override local.
const hubPalette = ref<string>(hubSettings.value?.theme_palette ?? 'erplora');
const hubCountry = ref<string>(hubSettings.value?.country_code ?? 'ES');
// Doc de la API: deriva del setting server-side (lib/api-docs → hubSettings.api_docs_enabled).
const showApiDocs = apiDocsEnabled;

// ── Estado: Comunicaciones / correo ─────────────────────────────────────────────────────────
const defaultEmailStatus = (): EmailChannelStatus => ({
  mode: 'managed', connected: true, status: 'ready', host: '', port: 0,
  security: 'starttls', username: '', from_name: 'ERPlora',
  from_email: 'noreply@erplora.com', reply_to: '', account_email: '',
  has_secret: false, last_error: '', updated_by: '',
});
const emailStatus = ref<EmailChannelStatus>(defaultEmailStatus());
const emailForm = ref<EmailChannelInput>({ mode: 'managed', port: 587, security: 'starttls' });
const emailBusy = ref(false);
const emailModeLabel = computed(() => {
  const labels: Record<string, string> = {
    managed: t('settings.emailManaged'), google_oauth: 'Google',
    microsoft_oauth: 'Microsoft', smtp: 'SMTP',
  };
  return labels[emailStatus.value.mode] ?? emailStatus.value.mode;
});

function hydrateEmailForm(status: EmailChannelStatus): void {
  emailStatus.value = status;
  emailForm.value = {
    mode: status.mode,
    host: status.host,
    port: status.port || 587,
    security: status.security,
    username: status.username,
    password: '',
    from_name: status.from_name,
    from_email: status.from_email,
    reply_to: status.reply_to,
    account_email: status.account_email,
  };
}

async function loadEmailChannel(): Promise<void> {
  if (!isAdmin.value) return;
  try { hydrateEmailForm(await getEmailChannel()); }
  catch { await toastError(t('settings.emailLoadError')); }
}

async function saveEmailChannel(): Promise<void> {
  if (!isAdmin.value) return;
  emailBusy.value = true;
  try {
    hydrateEmailForm(await putEmailChannel({
      ...emailForm.value,
      port: Number(emailForm.value.port) || 587,
    }));
    await toastSuccess(t('settings.emailSaved'));
  } catch {
    await toastError(t('settings.emailSaveError'));
  } finally { emailBusy.value = false; }
}

async function sendEmailTest(): Promise<void> {
  if (!isAdmin.value) return;
  emailBusy.value = true;
  try {
    await testEmailChannel();
    await loadEmailChannel();
    await toastSuccess(t('settings.emailTestSent'));
  } catch { await toastError(t('settings.emailTestError')); }
  finally { emailBusy.value = false; }
}

async function disconnectEmail(): Promise<void> {
  if (!isAdmin.value) return;
  emailBusy.value = true;
  try {
    hydrateEmailForm(await disconnectEmailChannel());
    await toastSuccess(t('settings.emailDisconnected'));
  } catch { await toastError(t('settings.emailDisconnectError')); }
  finally { emailBusy.value = false; }
}

async function connectEmailOauth(): Promise<void> {
  if (!isAdmin.value) return;
  emailBusy.value = true;
  try {
    const provider = emailForm.value.mode === 'google_oauth' ? 'google' : 'microsoft';
    window.location.assign(await beginEmailOauth(provider));
  } catch {
    emailBusy.value = false;
    await toastError(t('settings.emailOauthError'));
  }
}

/** Nombre legible del idioma DEFAULT del hub (para la vista solo-lectura de no-admin). */
const hubLanguageName = computed<string>(
  () => availableLocales.find((l) => l.code === hubLanguage.value)?.name ?? hubLanguage.value,
);

// Mantiene los refs locales en sync si la cache de settings cambia (p.ej. carga post-login en App).
watch(hubSettings, (s) => {
  if (!s) return;
  hubCurrency.value = s.currency;
  hubLanguage.value = s.language;
  hubPalette.value = s.theme_palette;
  hubCountry.value = s.country_code;
  businessTaxId.value = s.business_tax_id;
  businessLegalName.value = s.business_legal_name;
  businessAddress.value = s.business_address;
});

// Refresca los settings del hub al abrir Ajustes (best-effort; degrada a la cache sembrada).
onMounted(() => {
  void getHubSettings().catch(() => null);
  if (tab.value === 'communications') void loadEmailChannel();
});

let emailLoaded = false;
watch(
  tab,
  (current) => {
    if (current === 'communications' && !emailLoaded) {
      emailLoaded = true;
      void loadEmailChannel();
    }
  },
  { immediate: true },
);

// ── Estado: Negocio (identidad fiscal genérica, server-side /api/settings — ADR-0061) ──
// FUENTE ÚNICA país-agnóstica que usan invoice (emisor) y los módulos fiscales por país. Se siembra
// de la cache y se sincroniza con el watch de abajo. (IVA/régimen/VeriFactu salieron del core: el
// Hub es internacional → viven en el módulo `taxes` y en los módulos de compliance por país.)
const businessTaxId = ref<string>(hubSettings.value?.business_tax_id ?? '');
const businessLegalName = ref<string>(hubSettings.value?.business_legal_name ?? '');
const businessAddress = ref<string>(hubSettings.value?.business_address ?? '');

// Textos i18n del ok-theme-picker (defaults en inglés dentro del componente, ADR-0055).
const pickerLabels = computed(() => ({
  palette: t('settings.themePalette'),
  mode: t('settings.theme'),
  system: t('settings.themeSystem'),
  light: t('settings.themeLight'),
  dark: t('settings.themeDark'),
}));

// ok-theme-picker GLOBAL (solo admin): persiste al instante en hub_settings, como la moneda.
// theme.ts refleja la nueva global en el shell salvo que este navegador tenga override.
function onHubPaletteChange(e: Event): void {
  const next = (e as CustomEvent<{ palette: string }>).detail.palette;
  const prev = hubPalette.value;
  if (next === prev) return;
  hubPalette.value = next;
  void persistHubSettings({ theme_palette: next }, () => {
    hubPalette.value = prev;
  });
}

// Persiste un cambio parcial en los settings del hub (server). Solo admin (el runtime revalida).
// Revierte el ref en error para no mentir al usuario, y muestra toast de éxito/fallo.
async function persistHubSettings(
  partial: Partial<HubSettings>,
  revert: () => void,
): Promise<void> {
  try {
    await updateHubSettings(partial);
    await toastSuccess(t('settings.saved'));
  } catch {
    revert();
    await toastError(t('settings.saveError'));
  }
}

// Moneda del hub (GLOBAL): persiste al instante. money.ts la lee de la cache → todo el dinero se
// re-formatea sin recargar.
function onCurrencyChange(value: string): void {
  const prev = hubSettings.value?.currency ?? 'EUR';
  hubCurrency.value = value;
  // Mantén fresca la moneda que leen los Web Components de módulo vía el fallback del SDK (ADR-0059)
  // sin recargar; si el guardado falla, el revert la vuelve a la previa.
  publishHubCurrency(value);
  void persistHubSettings({ currency: value }, () => {
    hubCurrency.value = prev;
    publishHubCurrency(prev);
  });
}

// Idioma DEFAULT del hub (server): persiste al instante y reconcilia en caliente — si el usuario NO
// tiene override personal, el shell cambia de idioma ahora; si lo tiene, su elección manda.
function onHubLanguageChange(value: Locale): void {
  const prev = hubSettings.value?.language ?? 'es';
  hubLanguage.value = value;
  void persistHubSettings({ language: value }, () => {
    hubLanguage.value = prev;
  });
  bootHubLanguage(value);
}

// País fiscal del Hub (GLOBAL): driver para impuestos y módulos de cumplimiento. Se persiste con
// código ISO; nunca se deriva del catálogo de tipos de negocio del SaaS.
function onCountryChange(value: string): void {
  const prev = hubSettings.value?.country_code ?? 'ES';
  hubCountry.value = value;
  void persistHubSettings({ country_code: value }, () => {
    hubCountry.value = prev;
  });
}

// Toggle "Mostrar documentación de la API": setting GLOBAL del hub (solo admin). Persiste vía
// updateHubSettings; reactivo en la nav (App.vue) y el gate de la ruta (router) sin recargar.
function onApiDocsToggle(e: Event): void {
  if (!isAdmin.value) return; // defensa: el toggle ya está disabled para no-admin
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  if (checked === apiDocsEnabled.value) return; // evita re-disparo al re-sincronizar :checked
  void persistHubSettings({ api_docs_enabled: checked }, () => {
    /* la cache no se tocó: el :checked vuelve solo al valor server */
  });
}

async function saveTaxSettings(): Promise<void> {
  // Persiste la identidad de NEGOCIO GLOBAL (server-side, /api/settings — ADR-0061). Solo admin (el
  // runtime revalida); el tax_id se normaliza en el runtime. Impuestos/e-factura ya no viven aquí.
  const prev = {
    business_tax_id: hubSettings.value?.business_tax_id ?? '',
    business_legal_name: hubSettings.value?.business_legal_name ?? '',
    business_address: hubSettings.value?.business_address ?? '',
  };
  await persistHubSettings(
    {
      business_tax_id: businessTaxId.value.trim(),
      business_legal_name: businessLegalName.value.trim(),
      business_address: businessAddress.value.trim(),
    },
    () => {
      businessTaxId.value = prev.business_tax_id;
      businessLegalName.value = prev.business_legal_name;
      businessAddress.value = prev.business_address;
    },
  );
}

// ── Estado: Certificado fiscal del negocio (server-side /api/business/certificate) ──
// El certificado de empresa (.p12) es un recurso del NEGOCIO/hub (salió del módulo verifactu): se
// sube aquí junto al VAT y el nombre de la tienda. El runtime nunca devuelve los bytes; solo el
// estado. Subir/eliminar es solo admin (el runtime revalida → 401 si no).
const cert = ref<BusinessCertificate>({ present: false });
const certFileInput = ref<HTMLInputElement | null>(null);
const certFile = ref<File | null>(null);
const certFileName = ref<string>('');
const certPassword = ref<string>('');
const certBusy = ref<boolean>(false);

/** Fecha de subida formateada para el estado "Certificado configurado (subido el …)". */
const certUploadedLabel = computed<string>(() => {
  const raw = cert.value.uploaded_at;
  if (!raw) return '';
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? raw : d.toLocaleString();
});

// Lee el estado del certificado al abrir Ajustes (best-effort; degrada a "Sin certificado").
onMounted(() => {
  void getBusinessCertificate()
    .then((c) => {
      cert.value = c;
    })
    .catch(() => null);
});

function triggerCertFilePicker(): void {
  certFileInput.value?.click();
}

function onCertFileChange(e: Event): void {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  certFile.value = file;
  certFileName.value = file?.name ?? '';
}

/** Lee un fichero como base64 (sin el prefijo dataURL `data:...;base64,`). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const comma = result.indexOf(',');
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error('FileReader error'));
    reader.readAsDataURL(file);
  });
}

// Sube/reemplaza el certificado: lee el .p12 como base64 y hace PUT con {pkcs12_b64, password}.
// Solo admin (el runtime revalida). Refresca el estado y limpia el formulario al terminar.
async function uploadCert(): Promise<void> {
  if (!isAdmin.value) return; // defensa: los botones ya están disabled para no-admin
  if (!certFile.value) {
    await toastError(t('settings.certNoFile'));
    return;
  }
  certBusy.value = true;
  try {
    const b64 = await fileToBase64(certFile.value);
    await putBusinessCertificate(b64, certPassword.value);
    await toastSuccess(t('settings.certUploaded'));
    certFile.value = null;
    certFileName.value = '';
    certPassword.value = '';
    if (certFileInput.value) certFileInput.value.value = '';
    cert.value = await getBusinessCertificate().catch(() => ({ present: true }));
  } catch {
    await toastError(t('settings.certUploadError'));
  } finally {
    certBusy.value = false;
  }
}

// Elimina el certificado (DELETE). Solo admin. Refresca el estado al terminar.
async function removeCert(): Promise<void> {
  if (!isAdmin.value) return;
  certBusy.value = true;
  try {
    await deleteBusinessCertificate();
    await toastSuccess(t('settings.certDeleted'));
    cert.value = await getBusinessCertificate().catch(() => ({ present: false }));
  } catch {
    await toastError(t('settings.certDeleteError'));
  } finally {
    certBusy.value = false;
  }
}

// ── Estado: Permisos (capabilities de módulo, default-deny) ──
// Gestión AUTORITATIVA de los permisos que declara cada módulo instalado. El runtime es la
// autoridad (PUT solo admin → 401 si no); el `:disabled` del toggle es solo cosmético.
interface ModulePermissions {
  moduleId: string;
  name: string;
  /** Solo las que el módulo DECLARA (`requested:true`); el resto no se muestra. */
  capabilities: ModuleCapability[];
}

const permsLoading = ref<boolean>(false);
const modulesWithCaps = ref<ModulePermissions[]>([]);

/**
 * Carga, por cada módulo instalado, sus capabilities declaradas. Best-effort: si un módulo falla
 * al leer sus permisos lo omite. Solo aparecen módulos que declaran al menos una capability.
 */
async function loadPermissions(): Promise<void> {
  permsLoading.value = true;
  try {
    const installed = await listInstalledModules();
    const results = await Promise.all(
      installed.map(async (m) => {
        try {
          const caps = await getModuleCapabilities(m.id);
          const declared = caps.capabilities.filter((c) => c.requested);
          return declared.length ? { moduleId: m.id, name: m.name, capabilities: declared } : null;
        } catch {
          return null;
        }
      }),
    );
    modulesWithCaps.value = results.filter((r): r is ModulePermissions => r !== null);
  } catch {
    modulesWithCaps.value = [];
    await toastError(t('settings.permissionsLoadError'));
  } finally {
    permsLoading.value = false;
  }
}

// Carga perezosa al entrar en la pestaña Permisos (una vez; el watch evita recargar en cada cambio).
let permsLoaded = false;
watch(
  tab,
  (current) => {
    if (current === 'permissions' && !permsLoaded) {
      permsLoaded = true;
      void loadPermissions();
    }
  },
  { immediate: true },
);

/**
 * Concede/revoca una capability de un módulo (PUT default-deny, solo admin). Optimista con revert:
 * actualiza el estado local al instante y lo revierte si el runtime rechaza (p. ej. 401 no-admin).
 */
async function onCapabilityToggle(m: ModulePermissions, cap: ModuleCapability, e: Event): Promise<void> {
  if (!isAdmin.value) return; // defensa: el toggle ya está disabled para no-admin
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  if (checked === cap.granted) return; // evita re-disparo al re-sincronizar :checked
  const prev = cap.granted;
  cap.granted = checked;
  try {
    await putModuleCapabilities(m.moduleId, { [cap.id]: checked });
    await toastSuccess(
      t(checked ? 'settings.permissionGranted' : 'settings.permissionRevoked', {
        cap: cap.label,
        module: m.name,
      }),
    );
  } catch {
    cap.granted = prev;
    await toastError(t('settings.permissionSaveError'));
  }
}
</script>

<style scoped>
/* Input de fichero oculto (lo dispara un ion-button). Antes iba por inline style. */
.cert-file-input {
  display: none;
}
.communication-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.75rem;
}
.communication-hint {
  color: var(--ion-color-medium);
  line-height: 1.45;
}
</style>
