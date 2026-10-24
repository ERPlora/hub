<script setup lang="ts">
// «Devices» (Settings › General, BASE-G63…G66; the old hub's DevicesCard): the devices someone entered this hub on, live
// (`base.device.list`), the last entered first. Each row: the name the business gave it (or «Unnamed device» and what
// it is: «Chrome · Android»), «The one you are using», how it asks, when it was used, until when its session stays open
// and who entered last; never its identifier. «Name it» opens a field under the row; «Remove this device» asks first,
// with its consequence (the one in hand ends this session, then the way in); «Remove the devices unused for 30 days»
// too. Settings mounts it only for who runs the hub (the list is theirs). A list that cannot be read is never empty.
import { formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';

import { leaveTo } from '../lib/access';
import { useBaseI18n } from '../lib/i18n';
import type { DeviceRow } from '../operations';
import '../settings.css';

const { t, locale } = useBaseI18n();
const { data, status } = useLive('base.device.list', {});
const rename = useCommand('base.device.rename');
const remove = useCommand('base.device.remove');
const prune = useCommand('base.device.prune');

const devices = computed(() => data.value?.devices ?? []);
const when = (value: string | null): string => formatDateTime(value, locale.value);

// One question or field open at a time, under its row.
const naming = ref<string | null>(null);
const draft = ref('');
const nameError = ref('');
const removing = ref<string | null>(null);
const removeError = ref('');
const pruning = ref(false);
const pruneError = ref('');

function startNaming(device: DeviceRow): void {
  removing.value = null;
  naming.value = device.id;
  draft.value = device.name;
  nameError.value = '';
}

async function saveName(): Promise<void> {
  if (!naming.value || rename.pending.value) return;
  nameError.value = '';
  try {
    await rename.run({ id: naming.value, name: draft.value.trim() });
    naming.value = null;
  } catch (reason) {
    const detail = reason instanceof ApiError && reason.message ? ` ${reason.message}` : '';
    nameError.value = `${t('base.devices.renameFailed')}${detail}`;
  }
}

function askRemove(device: DeviceRow): void {
  naming.value = null;
  removing.value = device.id;
  removeError.value = '';
}

async function confirmRemove(): Promise<void> {
  if (!removing.value || remove.pending.value) return;
  removeError.value = '';
  try {
    const answer = await remove.run({ id: removing.value });
    removing.value = null;
    if (answer.yours) leaveTo('/');
  } catch {
    removeError.value = t('base.devices.removeFailed');
  }
}

async function confirmPrune(): Promise<void> {
  if (prune.pending.value) return;
  pruneError.value = '';
  try {
    await prune.run({});
    pruning.value = false;
  } catch {
    pruneError.value = t('base.devices.pruneFailed');
  }
}
</script>

<template>
  <section
    class="settings-card"
    data-testid="devices-card"
  >
    <h2 class="settings-card__title">
      {{ t('base.devices.title') }}
    </h2>
    <p class="settings-card__intro">
      {{ t('base.devices.intro') }}
    </p>
    <InlineFeedback
      v-if="status === 'error' && !data"
      tone="danger"
      data-testid="devices-load-error"
      :heading="t('base.devices.loadError')"
    />
    <p
      v-else-if="!data"
      class="settings-card__note devices__loading"
    >
      <ion-spinner name="crescent" />
      {{ t('base.devices.loading') }}
    </p>
    <p
      v-else-if="devices.length === 0"
      class="settings-card__note"
      data-testid="devices-empty"
    >
      {{ t('base.devices.empty') }}
    </p>
    <ul
      v-else
      class="devices"
    >
      <li
        v-for="device in devices"
        :key="device.id"
        class="devices__row"
        data-testid="device-row"
      >
        <div class="devices__head">
          <HubIcon
            class="devices__icon"
            :name="device.mode === 'shared' ? 'ion:desktop-outline' : 'ion:laptop-outline'"
            aria-hidden="true"
          />
          <div class="devices__what">
            <p class="devices__name">
              {{ device.name || t('base.devices.unnamed') }}
              <span
                v-if="device.current"
                class="devices__current"
              >{{ t('base.devices.current') }}</span>
            </p>
            <p class="settings-card__note">
              <template v-if="!device.name">
                {{ device.agent }} ·
              </template>
              {{ device.mode === 'shared' ? t('base.devices.modeShared') : t('base.devices.modePersonal') }} ·
              {{ device.in_use ? t('base.devices.inUse') : t('base.devices.lastUsed', { when: when(device.last_entry_at) }) }}
            </p>
            <p
              v-if="device.session_until"
              class="settings-card__note"
            >
              {{ t('base.devices.sessionUntil', { when: when(device.session_until) }) }}
            </p>
            <p
              v-if="device.last_user"
              class="settings-card__note"
            >
              {{ t('base.devices.lastUser', { who: device.last_user }) }}
            </p>
          </div>
          <div class="devices__actions">
            <ion-button
              fill="clear"
              size="small"
              data-testid="device-rename"
              @click="startNaming(device)"
            >
              {{ t('base.devices.rename') }}
            </ion-button>
            <ion-button
              fill="clear"
              size="small"
              color="danger"
              data-testid="device-remove"
              :aria-label="t('base.devices.remove')"
              :title="t('base.devices.remove')"
              @click="askRemove(device)"
            >
              <HubIcon
                name="ion:trash-outline"
                aria-hidden="true"
              />
            </ion-button>
          </div>
        </div>

        <form
          v-if="naming === device.id"
          class="devices__inline"
          @submit.prevent="saveName"
        >
          <ion-input
            data-testid="device-name"
            :value="draft"
            :label="t('base.devices.renameLabel')"
            :placeholder="t('base.devices.renamePlaceholder')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="80"
            @ion-input="draft = String($event.detail.value ?? '')"
          />
          <p
            v-if="nameError"
            class="devices__error"
            role="alert"
            data-testid="device-name-error"
          >
            {{ nameError }}
          </p>
          <div class="devices__buttons">
            <ion-button
              size="small"
              type="submit"
              data-testid="device-name-save"
              :disabled="rename.pending.value"
              @click="saveName"
            >
              {{ t('base.devices.save') }}
            </ion-button>
            <ion-button
              size="small"
              fill="clear"
              data-testid="device-name-keep"
              @click="naming = null"
            >
              {{ t('base.devices.keep') }}
            </ion-button>
          </div>
        </form>

        <div
          v-if="removing === device.id"
          class="devices__inline"
          data-testid="device-remove-ask"
        >
          <p class="devices__ask">
            {{ t('base.devices.removeAsk') }}
          </p>
          <p class="settings-card__note">
            {{ device.current ? t('base.devices.removeYours') : t('base.devices.removeBody') }}
          </p>
          <p
            v-if="removeError"
            class="devices__error"
            role="alert"
            data-testid="device-remove-error"
          >
            {{ removeError }}
          </p>
          <div class="devices__buttons">
            <ion-button
              size="small"
              color="danger"
              data-testid="device-remove-confirm"
              :disabled="remove.pending.value"
              @click="confirmRemove"
            >
              {{ t('base.devices.remove') }}
            </ion-button>
            <ion-button
              size="small"
              fill="clear"
              data-testid="device-remove-keep"
              @click="removing = null"
            >
              {{ t('base.devices.keep') }}
            </ion-button>
          </div>
        </div>
      </li>
    </ul>

    <template v-if="data && data.unused > 0">
      <ion-button
        v-if="!pruning"
        fill="outline"
        size="small"
        class="devices__prune"
        data-testid="devices-prune"
        @click="pruning = true"
      >
        {{ data.unused === 1 ? t('base.devices.pruneOne') : t('base.devices.pruneMany', { n: data.unused }) }}
      </ion-button>
      <div
        v-else
        class="devices__inline"
        data-testid="devices-prune-ask"
      >
        <p class="devices__ask">
          {{ data.unused === 1 ? t('base.devices.pruneAskOne') : t('base.devices.pruneAsk', { n: data.unused }) }}
        </p>
        <p class="settings-card__note">
          {{ t('base.devices.pruneBody') }}
        </p>
        <p
          v-if="pruneError"
          class="devices__error"
          role="alert"
          data-testid="devices-prune-error"
        >
          {{ pruneError }}
        </p>
        <div class="devices__buttons">
          <ion-button
            size="small"
            color="danger"
            data-testid="devices-prune-confirm"
            :disabled="prune.pending.value"
            @click="confirmPrune"
          >
            {{ t('base.devices.pruneConfirm') }}
          </ion-button>
          <ion-button
            size="small"
            fill="clear"
            data-testid="devices-prune-keep"
            @click="pruning = false"
          >
            {{ t('base.devices.keep') }}
          </ion-button>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.devices {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.devices__row {
  padding: 12px 0;
  border-top: 1px solid var(--ion-color-step-100, #e6e6e6);
}

.devices__row:first-child {
  border-top: 0;
}

.devices__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.devices__icon {
  flex: none;
  margin-top: 2px;
  font-size: 1.375rem;
  color: var(--ion-color-medium);
}

.devices__what {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.devices__name {
  margin: 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.devices__current {
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(var(--ion-color-primary-rgb, 22, 151, 213), 0.12);
  color: var(--ion-color-primary);
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}

.devices__actions {
  flex: none;
  display: flex;
  align-items: center;
}

.devices__inline {
  margin: 10px 0 0 34px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.devices__ask {
  margin: 0;
  font-weight: 600;
}

.devices__error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}

.devices__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.devices__prune {
  align-self: flex-start;
}

.devices__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 480px) {
  .devices__inline {
    margin-left: 0;
  }
}
</style>
