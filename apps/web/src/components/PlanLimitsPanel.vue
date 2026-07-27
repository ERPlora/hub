<template>
  <!-- Panel «Plan y límites» (ADR-0154, hub#203): uso de recursos del hub FRENTE a la cuota del
       plan + dispositivos vs `max_devices`, con CTA de upgrade para el free tier. Se monta solo
       cuando su pestaña está activa (v-if en SystemPage) → el polling vive con la pestaña. -->
  <div class="plan-limits">
    <div v-if="loading" class="pl-loading">
      <ion-spinner name="crescent" />
    </div>

    <template v-else>
      <ok-inline-feedback
        v-if="failed"
        tone="danger"
        icon="cloud-offline-outline"
        :heading="t('planLimits.loadErrorTitle')"
      >
        {{ t('planLimits.loadErrorBody') }}
        <ion-button slot="actions" size="small" fill="outline" @click="load">
          {{ t('planLimits.retry') }}
        </ion-button>
      </ok-inline-feedback>

      <template v-else-if="metrics">
        <!-- Cabecera: plan contratado + estado de salud. -->
        <div class="pl-header">
          <div>
            <div class="pl-header__label">{{ t('planLimits.currentPlan') }}</div>
            <div class="pl-header__plan">{{ planLabel }}</div>
          </div>
          <ok-status-pill :tone="reason ? 'warning' : 'success'" dot>
            {{ reason ? t('planLimits.nearLimit') : t('planLimits.healthy') }}
          </ok-status-pill>
        </div>

        <!-- CTA de upgrade: SOLO plan free rozando un límite (RAM/BD >=80% o tope de dispositivos). -->
        <ok-inline-feedback
          v-if="reason"
          class="pl-cta"
          tone="warning"
          icon="trending-up-outline"
          :heading="t('planLimits.upgradeTitle')"
        >
          {{ upgradeMessage }}
          <ion-button slot="actions" size="small" @click="openUpgrade">
            <HubIcon slot="start" name="open-outline" />
            {{ t('planLimits.upgradeCta') }}
          </ion-button>
        </ok-inline-feedback>

        <ion-grid class="ion-no-padding pl-grid">
          <ion-row>
            <!-- RAM: uso vs límite del cgroup (= cuota del plan). -->
            <ion-col size="12" size-md="6">
              <ion-card class="ion-no-margin pl-card">
                <ion-card-content>
                  <div class="pl-card__head">
                    <HubIcon name="hardware-chip-outline" class="pl-card__icon" />
                    <span class="pl-card__title">{{ t('planLimits.memory') }}</span>
                    <ok-status-pill size="sm" :tone="toneFor(metrics.memory.fraction)">
                      {{ memPct !== null ? `${memPct}%` : t('planLimits.na') }}
                    </ok-status-pill>
                  </div>
                  <ion-progress-bar
                    v-if="metrics.memory.fraction !== null"
                    :value="metrics.memory.fraction"
                    :color="colorFor(metrics.memory.fraction)"
                  ></ion-progress-bar>
                  <div class="pl-card__foot">
                    {{ metrics.memory.usedBytes !== null
                      ? usageLabel(metrics.memory.usedBytes, metrics.memory.limitBytes)
                      : t('planLimits.naHint') }}
                  </div>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- CPU: cores usados vs límite del cgroup. -->
            <ion-col size="12" size-md="6">
              <ion-card class="ion-no-margin pl-card">
                <ion-card-content>
                  <div class="pl-card__head">
                    <HubIcon name="speedometer-outline" class="pl-card__icon" />
                    <span class="pl-card__title">{{ t('planLimits.cpu') }}</span>
                    <ok-status-pill size="sm" :tone="toneFor(metrics.cpu.fraction)">
                      {{ cpuPct !== null ? `${cpuPct}%` : t('planLimits.na') }}
                    </ok-status-pill>
                  </div>
                  <ion-progress-bar
                    v-if="metrics.cpu.fraction !== null"
                    :value="metrics.cpu.fraction"
                    :color="colorFor(metrics.cpu.fraction)"
                  ></ion-progress-bar>
                  <div class="pl-card__foot">
                    {{ metrics.cpu.usedCores !== null ? cpuLabel : t('planLimits.naHint') }}
                  </div>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- Base de datos: tamaño real frente a la cuota firmada del plan; sin barra cuando
                 el plan es ilimitado o el token es anterior al claim. -->
            <ion-col size="12" size-md="6">
              <ion-card class="ion-no-margin pl-card">
                <ion-card-content>
                  <div class="pl-card__head">
                    <HubIcon name="server-outline" class="pl-card__icon" />
                    <span class="pl-card__title">{{ t('planLimits.database') }}</span>
                    <ok-status-pill size="sm" tone="neutral">{{ metrics.database.engine }}</ok-status-pill>
                  </div>
                  <ion-progress-bar
                    v-if="metrics.database.fraction !== null"
                    :value="metrics.database.fraction"
                    :color="colorFor(metrics.database.fraction)"
                  ></ion-progress-bar>
                  <div class="pl-card__big">{{ formatBytes(metrics.database.sizeBytes) }}</div>
                  <div class="pl-card__foot">
                    {{ metrics.database.limitBytes !== null
                      ? usageLabel(metrics.database.sizeBytes, metrics.database.limitBytes)
                      : t('planLimits.dbNoQuota') }}
                  </div>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- Dispositivos/sesiones vs el tope del plan («1 dispositivo» del free bien visible). -->
            <ion-col size="12" size-md="6">
              <ion-card class="ion-no-margin pl-card">
                <ion-card-content>
                  <div class="pl-card__head">
                    <HubIcon name="phone-portrait-outline" class="pl-card__icon" />
                    <span class="pl-card__title">{{ t('planLimits.devices') }}</span>
                    <ok-status-pill size="sm" :tone="devicesTone">
                      {{ metrics.sessions.maxDevices > 0 ? t('planLimits.capped') : t('planLimits.unlimited') }}
                    </ok-status-pill>
                  </div>
                  <div class="pl-card__big">{{ devicesHeadline }}</div>
                  <div class="pl-card__foot">{{ t('planLimits.activeSessions', { n: metrics.sessions.active }) }}</div>
                </ion-card-content>
              </ion-card>
            </ion-col>
          </ion-row>
        </ion-grid>

        <p class="pl-note">{{ t('planLimits.liveNote') }}</p>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonSpinner, IonButton, IonGrid, IonRow, IonCol, IonCard, IonCardContent, IonProgressBar,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { openExternal } from '../lib/open-external';
import {
  fetchSystemMetrics, formatBytes, toPct, upgradeReason, upgradeLink, type SystemMetrics,
} from '../lib/system-metrics';

const { t } = useI18n();

/** Refresco en vivo: polling ligero SOLO mientras la página es visible (no montamos push nuevo:
 *  el canal Outbox/refresh_on de ADR-0054 transporta eventos de dominio, no métricas del sistema). */
const POLL_MS = 5000;

const loading = ref(true);
const failed = ref(false);
const metrics = ref<SystemMetrics | null>(null);
let timer: number | null = null;

const reason = computed(() => (metrics.value ? upgradeReason(metrics.value) : null));
const planLabel = computed<string>(() => {
  const p = metrics.value?.plan;
  return p ? p.charAt(0).toUpperCase() + p.slice(1) : t('planLimits.unknownPlan');
});
const memPct = computed<number | null>(() => toPct(metrics.value?.memory.fraction));
const cpuPct = computed<number | null>(() => toPct(metrics.value?.cpu.fraction));
const cpuLabel = computed<string>(() => {
  const c = metrics.value?.cpu;
  if (!c || c.usedCores === null) return t('planLimits.naHint');
  const used = c.usedCores.toFixed(2);
  return c.limitCores !== null
    ? t('planLimits.coresOf', { used, limit: c.limitCores })
    : t('planLimits.cores', { used });
});
const devicesHeadline = computed<string>(() => {
  const s = metrics.value?.sessions;
  if (!s) return '—';
  return s.maxDevices > 0 ? `${s.devices} / ${s.maxDevices}` : String(s.devices);
});
const devicesTone = computed<string>(() => {
  const s = metrics.value?.sessions;
  if (!s || s.maxDevices === 0) return 'neutral';
  return s.devices >= s.maxDevices ? 'warning' : 'success';
});
const upgradeMessage = computed<string>(() => {
  switch (reason.value) {
    case 'memory': return t('planLimits.upgradeMemory');
    case 'database': return t('planLimits.upgradeDatabase');
    case 'devices': return t('planLimits.upgradeDevices');
    default: return '';
  }
});

/** Barra/etiqueta de color por fracción: verde <80%, ámbar 80–90%, rojo ≥90%. */
function colorFor(fraction: number | null): string {
  if (fraction === null) return 'medium';
  if (fraction >= 0.9) return 'danger';
  if (fraction >= 0.8) return 'warning';
  return 'success';
}
function toneFor(fraction: number | null | undefined): string {
  if (fraction == null) return 'neutral';
  if (fraction >= 0.9) return 'danger';
  if (fraction >= 0.8) return 'warning';
  return 'success';
}
function usageLabel(used: number | null, limit: number | null): string {
  return limit !== null
    ? t('planLimits.usedOfLimit', { used: formatBytes(used), limit: formatBytes(limit) })
    : t('planLimits.usedNoLimit', { used: formatBytes(used) });
}

async function openUpgrade(): Promise<void> {
  await openExternal(upgradeLink());
}

/** Carga inicial (con spinner). Marca error si el runtime no responde. */
async function load(): Promise<void> {
  loading.value = true;
  const data = await fetchSystemMetrics();
  metrics.value = data;
  failed.value = data === null;
  loading.value = false;
}

/** Refresco silencioso en vivo: actualiza si hay datos, conserva los últimos buenos si falla. */
async function refresh(): Promise<void> {
  const data = await fetchSystemMetrics();
  if (data) {
    metrics.value = data;
    failed.value = false;
  }
}

function onVisibility(): void {
  if (document.visibilityState === 'visible') void refresh();
}

onMounted(() => {
  void load();
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void refresh();
  }, POLL_MS);
  document.addEventListener('visibilitychange', onVisibility);
});

onBeforeUnmount(() => {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
  document.removeEventListener('visibilitychange', onVisibility);
});
</script>

<style scoped>
.pl-loading {
  display: grid;
  place-items: center;
  padding: 48px 0;
}
.pl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 4px 4px 12px;
}
.pl-header__label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ion-color-medium);
}
.pl-header__plan {
  font-size: 1.375rem;
  font-weight: 700;
  line-height: 1.1;
}
.pl-cta {
  margin: 0 4px 12px;
}
.pl-card {
  height: 100%;
}
.pl-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.pl-card__icon {
  font-size: 20px;
  opacity: 0.55;
}
.pl-card__title {
  font-weight: 600;
  flex: 1;
}
.pl-card__big {
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1.2;
  margin-top: 8px;
}
.pl-card__foot {
  margin-top: 8px;
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
}
ion-progress-bar {
  height: 8px;
  border-radius: 4px;
  --buffer-background: var(--ion-color-step-150, #e0e0e0);
}
.pl-note {
  margin: 12px 4px 0;
  font-size: 0.75rem;
  opacity: 0.6;
}
</style>
