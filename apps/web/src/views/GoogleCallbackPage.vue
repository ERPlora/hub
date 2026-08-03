<!--
  Callback del login con Google que vuelve al Hub (#945).

  El Hub no puede hablar con Google directamente (sin client secret ni
  redirect_uri registrado). Abre el login de Google del Cloud con un `next` que
  apunta al hub-bridge; tras autenticarse, el Cloud acuña un AuthExchangeCode y
  redirige aquí como /auth/google/callback?code=…. Esta vista canjea ese code
  por la sesión Cloud (sessionExchange) y ejecuta el mismo bootstrap que el
  login por email: setTokens → runtimeCloudSession → setHubSession → setUser →
  redirige. Sin este destino, el catch-all del router mandaba al usuario a
  /dashboard → /login, dejándolo logueado en el SaaS pero fuera del Hub.
-->
<template>
  <ion-page>
    <ion-content class="ion-padding center-content">
      <div v-if="loading" class="google-callback-state">
        <ion-spinner name="crescent" />
        <p>{{ t('login.completingSignIn') }}</p>
      </div>
      <div v-else-if="errorMsg" class="google-callback-state">
        <HubIcon name="alert-circle-outline" />
        <p>{{ errorMsg }}</p>
        <ion-button fill="outline" size="small" @click="goLogin">
          {{ t('login.backToLogin') }}
        </ion-button>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { IonPage, IonContent, IonSpinner, IonButton } from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import { setUser, setHubSession } from '../lib/session';
import { setTokens, runtimeCloudSession, sessionExchange } from '../lib/cloud';
import { bootHubContext } from '../lib/runtime';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

const loading = ref(true);
const errorMsg = ref('');

function redirectTarget(): string {
  // Misma validación que LoginPage.redirectTarget: solo paths internos seguros.
  const raw = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
  return typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//') && !raw.startsWith('/login')
    ? raw
    : '/';
}

function goLogin(): void {
  router.replace({ name: 'login' });
}

onMounted(async () => {
  const code = typeof route.query.code === 'string' ? route.query.code : '';
  if (!code) {
    loading.value = false;
    errorMsg.value = t('login.errorGoogleCallback');
    return;
  }

  try {
    // 1. Canjea el code one-time por el par de JWT del Cloud.
    const result = await sessionExchange(code);

    // 2. Bootstrap de sesión (espejo del login por email). Para Google no hay
    //    PIN/dispositivo-confiable: la sesión Cloud es la autoridad.
    setTokens(result.access, result.refresh);

    const sess = await runtimeCloudSession(result.access, result.user.name, result.user.email);
    setHubSession(sess.token);
    setUser({
      id: sess.user.id,
      cloudUserId: result.user.id,
      name: result.user.name,
      email: result.user.email,
      avatarUrl: result.user.avatarUrl ?? null,
      role: sess.user.role,
      permissions: sess.permissions,
    });

    // Refresca el contexto del runtime (módulos/entitlement) antes de entrar.
    try {
      await bootHubContext();
    } catch {
      // No bloqueante: el dashboard reintenta el contexto al montar.
    }

    await router.replace(redirectTarget());
  } catch {
    loading.value = false;
    errorMsg.value = t('login.errorGoogleCallback');
  }
});
</script>

<style scoped>
.center-content {
  display: flex;
  align-items: center;
  justify-content: center;
}
.google-callback-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  text-align: center;
  max-width: 20rem;
  margin: 0 auto;
  color: var(--ion-color-medium);
}
.google-callback-state ion-spinner {
  width: 2.5rem;
  height: 2.5rem;
}
</style>
