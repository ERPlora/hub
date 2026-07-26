<!--
  PublicPresencePanel — toggle "Presencia web pública" de Ajustes (ADR-0160).

  Activa/desactiva la PARTE PÚBLICA del hub (landing + páginas públicas) escribiendo la clave core
  `public.landing.visible` (bool, default false) por la API de settings del hub ya existente
  (`PUT /api/settings`, hub-settings.ts). Con OFF, el hub no tiene presencia web pública.

  Mismo patrón que el toggle "Mostrar documentación de la API" de SettingsPage: refleja el valor
  server-side de la cache reactiva `hubSettings`, persiste al instante (optimista con revert + toast)
  y solo lo cambia un admin (el `:disabled` es cosmético; el runtime revalida owner/admin).
-->
<template>
  <ion-card>
    <ion-card-content class="p-0">
      <ion-item lines="none">
        <HubIcon slot="start" name="globe-outline" />
        <ion-label>
          <h2>{{ t('settings.publicPresence') }}</h2>
          <p>{{ t('settings.publicPresenceDesc') }}</p>
        </ion-label>
        <ion-toggle
          :checked="landingVisible"
          :disabled="!isAdmin"
          :aria-label="t('settings.publicPresence')"
          data-testid="public-presence-toggle"
          slot="end"
          @ion-change="onToggle($event)"
        />
      </ion-item>
    </ion-card-content>
  </ion-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonCard, IonCardContent, IonItem, IonLabel, IonToggle } from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { isAdmin } from '../lib/session';
import { hubSettings, updateHubSettings } from '../lib/hub-settings';
import { toastSuccess, toastError } from '../lib/toast';

// Clave core plana del store k/v (ADR-0160). `as const` para que el tipo del PUT sea exacto.
const KEY = 'public.landing.visible' as const;

const { t } = useI18n();

// Refleja el valor server-side actual (cache reactiva sembrada en el boot / al abrir Ajustes).
const landingVisible = ref<boolean>(hubSettings.value?.[KEY] ?? false);
watch(hubSettings, (s) => {
  if (s) landingVisible.value = s[KEY];
});

// Persiste al instante (solo admin). Optimista con revert: actualiza el toggle ya y lo revierte si
// el runtime rechaza (p. ej. 401 no-admin), con toast de éxito/fallo.
async function onToggle(e: Event): Promise<void> {
  if (!isAdmin.value) return; // defensa: el toggle ya está disabled para no-admin
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  if (checked === landingVisible.value) return; // evita re-disparo al re-sincronizar :checked
  const prev = landingVisible.value;
  landingVisible.value = checked;
  try {
    await updateHubSettings({ [KEY]: checked });
    await toastSuccess(t('settings.saved'));
  } catch {
    landingVisible.value = prev;
    await toastError(t('settings.saveError'));
  }
}
</script>
