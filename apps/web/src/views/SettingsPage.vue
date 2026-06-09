<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-buttons slot="start">
          <ion-menu-button />
        </ion-buttons>
        <ion-title>Ajustes del Hub</ion-title>
      </ion-toolbar>
    </ion-header>

    <ion-content class="ion-padding">
      <!-- ── Tab: Hub ── -->
      <template v-if="tab === 'hub'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- System Language -->
              <ion-item>
                <ion-icon slot="start" :icon="languageOutline" />
                <ion-label>
                  <h2>System Language</h2>
                  <p>Default language for the Hub interface</p>
                </ion-label>
                <ion-select
                  v-model="hubLang"
                  interface="popover"
                  aria-label="System Language"
                  slot="end"
                >
                  <ion-select-option value="es">Español</ion-select-option>
                  <ion-select-option value="en">English</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Timezone -->
              <ion-item>
                <ion-icon slot="start" :icon="globeOutline" />
                <ion-label>
                  <h2>Timezone</h2>
                  <p>Timezone for dates and schedules</p>
                </ion-label>
                <ion-select
                  v-model="hubTimezone"
                  interface="popover"
                  aria-label="Timezone"
                  slot="end"
                >
                  <ion-select-option value="madrid">Europe/Madrid</ion-select-option>
                  <ion-select-option value="canary">Atlantic/Canary</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Country -->
              <ion-item>
                <ion-icon slot="start" :icon="businessOutline" />
                <ion-label>
                  <h2>Country</h2>
                  <p>Country for regional settings</p>
                </ion-label>
                <ion-select
                  v-model="hubCountry"
                  interface="popover"
                  aria-label="Country"
                  slot="end"
                >
                  <ion-select-option value="spain">Spain</ion-select-option>
                  <ion-select-option value="portugal">Portugal</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Theme -->
              <ion-item>
                <ion-icon slot="start" :icon="colorPaletteOutline" />
                <ion-label>
                  <h2>Theme</h2>
                  <p>Appearance mode for the interface</p>
                </ion-label>
                <ion-select
                  v-model="hubTheme"
                  interface="popover"
                  aria-label="Theme"
                  slot="end"
                  @ion-change="onThemeChange($event.detail.value as ThemeMode)"
                >
                  <ion-select-option value="system">System (auto)</ion-select-option>
                  <ion-select-option value="light">Light</ion-select-option>
                  <ion-select-option value="dark">Dark</ion-select-option>
                </ion-select>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>

        <ion-button class="mt-3" expand="block" @click="saveHubSettings">
          <ion-icon slot="start" :icon="saveOutline" />
          Guardar ajustes
        </ion-button>

        <!-- Show modules in sidebar toggle -->
        <ion-card class="mt-3">
          <ion-card-content class="p-0">
            <ion-item lines="none">
              <ion-icon slot="start" :icon="readerOutline" />
              <ion-label>
                <h2>Show modules in sidebar</h2>
                <p>Display installed modules as shortcuts in the sidebar navigation</p>
              </ion-label>
              <ion-toggle v-model="showModulesInSidebar" slot="end" />
            </ion-item>
          </ion-card-content>
        </ion-card>

        <h2 class="text-base font-semibold mt-4 mb-2 px-1">Hardware</h2>

        <!-- ERPlora Bridge -->
        <ion-card>
          <ion-card-content class="p-0">
            <ion-item button detail lines="none">
              <ion-icon slot="start" :icon="extensionPuzzleOutline" />
              <ion-label>
                <h2>ERPlora Bridge</h2>
                <p>Printers, cash drawer, barcode scanner and bridge connection</p>
              </ion-label>
              <ion-note slot="end">Disabled</ion-note>
            </ion-item>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Store ── -->
      <template v-else-if="tab === 'store'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- Store Type -->
              <ion-item>
                <ion-icon slot="start" :icon="storefrontOutline" />
                <ion-label>
                  <h2>Store Type</h2>
                  <p>Default sales workflow</p>
                </ion-label>
                <ion-select
                  v-model="storeType"
                  interface="popover"
                  aria-label="Store Type"
                  slot="end"
                >
                  <ion-select-option value="retail">Retail</ion-select-option>
                  <ion-select-option value="food">Food Service</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Locale -->
              <ion-item>
                <ion-icon slot="start" :icon="globeOutline" />
                <ion-label>
                  <h2>Locale</h2>
                  <p>Regional display format</p>
                </ion-label>
                <ion-select
                  v-model="storeLocale"
                  interface="popover"
                  aria-label="Locale"
                  slot="end"
                >
                  <ion-select-option value="es">Spain</ion-select-option>
                  <ion-select-option value="en">United Kingdom</ion-select-option>
                </ion-select>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Tax ── -->
      <template v-else-if="tab === 'tax'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- IVA por defecto -->
              <ion-item>
                <ion-icon slot="start" :icon="walletOutline" />
                <ion-label>
                  <h2>IVA por defecto</h2>
                  <p>Tipo aplicado a productos nuevos</p>
                </ion-label>
                <ion-select
                  v-model="taxIva"
                  interface="popover"
                  aria-label="IVA por defecto"
                  slot="end"
                >
                  <ion-select-option value="21">21% (general)</ion-select-option>
                  <ion-select-option value="10">10% (reducido)</ion-select-option>
                  <ion-select-option value="4">4% (superreducido)</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Régimen fiscal -->
              <ion-item>
                <ion-icon slot="start" :icon="businessOutline" />
                <ion-label>
                  <h2>Régimen fiscal</h2>
                  <p>Régimen de facturación</p>
                </ion-label>
                <ion-select
                  v-model="taxRegime"
                  interface="popover"
                  aria-label="Régimen fiscal"
                  slot="end"
                >
                  <ion-select-option value="general">Régimen general</ion-select-option>
                  <ion-select-option value="recargo">Recargo de equivalencia</ion-select-option>
                </ion-select>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>

        <!-- VeriFactu toggle -->
        <ion-card class="mt-3">
          <ion-card-content class="p-0">
            <ion-item lines="none">
              <ion-icon slot="start" :icon="ticketOutline" />
              <ion-label>
                <h2>VeriFactu</h2>
                <p>Reporte de facturas conforme a la normativa</p>
              </ion-label>
              <ion-toggle v-model="taxVerifactu" slot="end" />
            </ion-item>
          </ion-card-content>
        </ion-card>

        <ion-button class="mt-3" expand="block" @click="saveTaxSettings">
          <ion-icon slot="start" :icon="saveOutline" />
          Guardar cambios
        </ion-button>
      </template>

      <!-- ── Tab: Tickets ── -->
      <template v-else-if="tab === 'tickets'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-item button detail lines="none">
              <ion-icon slot="start" :icon="ticketOutline" />
              <ion-label>
                <h2>Ticket Template</h2>
                <p>Printed and digital receipt settings</p>
              </ion-label>
            </ion-item>
          </ion-card-content>
        </ion-card>
      </template>
    </ion-content>

    <!-- Footer tab bar -->
    <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="tab = ($event.detail.value as Tab)">
          <ion-segment-button value="hub">
            <ion-icon :icon="businessOutline" />
            <ion-label>Hub</ion-label>
          </ion-segment-button>
          <ion-segment-button value="store">
            <ion-icon :icon="storefrontOutline" />
            <ion-label>Store</ion-label>
          </ion-segment-button>
          <ion-segment-button value="tax">
            <ion-icon :icon="walletOutline" />
            <ion-label>Tax</ion-label>
          </ion-segment-button>
          <ion-segment-button value="tickets">
            <ion-icon :icon="ticketOutline" />
            <ion-label>Tickets</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
    </ion-footer>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import {
  IonPage,
  IonHeader,
  IonToolbar,
  IonButtons,
  IonMenuButton,
  IonTitle,
  IonContent,
  IonFooter,
  IonSegment,
  IonSegmentButton,
  IonCard,
  IonCardContent,
  IonList,
  IonItem,
  IonLabel,
  IonIcon,
  IonNote,
  IonSelect,
  IonSelectOption,
  IonToggle,
  IonButton,
} from '@ionic/vue';
import {
  businessOutline,
  colorPaletteOutline,
  extensionPuzzleOutline,
  globeOutline,
  languageOutline,
  readerOutline,
  saveOutline,
  storefrontOutline,
  ticketOutline,
  walletOutline,
} from 'ionicons/icons';

type Tab = 'hub' | 'store' | 'tax' | 'tickets';
type ThemeMode = 'system' | 'light' | 'dark';

const tab = ref<Tab>('hub');

// ── Estado: Hub ──
const hubLang = ref<string>('es');
const hubTimezone = ref<string>('madrid');
const hubCountry = ref<string>('spain');
const hubTheme = ref<ThemeMode>('system');
const showModulesInSidebar = ref<boolean>(false);

// ── Estado: Store ──
const storeType = ref<string>('retail');
const storeLocale = ref<string>('es');

// ── Estado: Tax ──
const taxIva = ref<string>('21');
const taxRegime = ref<string>('general');
const taxVerifactu = ref<boolean>(true);

function onThemeChange(value: ThemeMode): void {
  hubTheme.value = value;
  // Aplicar modo al documento (manipulación directa del DOM, sin eval)
  document.documentElement.classList.remove('ion-palette-dark', 'ion-palette-light');
  if (value === 'dark') {
    document.documentElement.classList.add('ion-palette-dark');
  } else if (value === 'light') {
    document.documentElement.classList.add('ion-palette-light');
  }
}

function saveHubSettings(): void {
  // En producción: llamada al endpoint del Hub.
  console.info('[SettingsPage] Hub settings saved', {
    lang: hubLang.value,
    timezone: hubTimezone.value,
    country: hubCountry.value,
    theme: hubTheme.value,
    showModulesInSidebar: showModulesInSidebar.value,
  });
}

function saveTaxSettings(): void {
  // En producción: llamada al endpoint del Hub.
  console.info('[SettingsPage] Ajustes fiscales guardados', {
    iva: taxIva.value,
    regime: taxRegime.value,
    verifactu: taxVerifactu.value,
  });
}
</script>
