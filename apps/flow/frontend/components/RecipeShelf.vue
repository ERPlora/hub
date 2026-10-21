<script setup lang="ts">
// «Comes with …» (WORKBOOK FLOW-F33, F34, F35; the old module's FLOWS-F05 and F06): the ready-made
// automations the apps bring, under the gallery's own cards, one section per app (`flow.recipe.list`,
// live). A card opens (one at a time) to say what it does and what it may do and why, in its app's words.
// «Turn it on» builds it on with exactly those permissions (`flow.recipe.enable`); once built it says how it
// is and offers «Pause it» (a pause, never a delete) or «Turn it on», «See it» and «Restore the factory one»
// (asked first: the owner's changes go). «New version» when its app brings a newer one. Below, what this
// business cannot use and why. With nothing to offer, the section does not show.
import { InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import { usePhrasing } from '../composables/usePhrasing';
import { useT } from '../composables/useT';
import { actionLabel, statePill } from '../lib/phrasing';
import { wording } from '../lib/refusal';
import type { CatalogOut, RecipeOut } from '../operations';

defineProps<{ catalog: CatalogOut | null }>();
const t = useT();
const phrasing = usePhrasing();
const router = useRouter();
const { confirm } = useConfirm();
const shelf = useLive('flow.recipe.list', {});
const enable = useCommand('flow.recipe.enable');
const disable = useCommand('flow.recipe.disable');
const restore = useCommand('flow.recipe.restore');
const busy = computed(() => enable.pending.value || disable.pending.value || restore.pending.value);
const open = ref<string | null>(null);
const errors = shallowRef<Record<string, ApiError | undefined>>({});

const groups = computed(() => {
  const byApp = new Map<string, { app: string; name: string; icon: string; recipes: RecipeOut[] }>();
  for (const recipe of shelf.data.value?.recipes ?? []) {
    const group = byApp.get(recipe.app) ?? { app: recipe.app, name: recipe.app_name, icon: recipe.icon, recipes: [] };
    group.recipes.push(recipe);
    byApp.set(recipe.app, group);
  }
  return [...byApp.values()];
});
const setAside = computed(() => shelf.data.value?.set_aside ?? []);
const hidden = computed(() => {
  const apps = [...new Set(setAside.value.filter((item) => item.code === 'flow.recipe_needs_apps').flatMap((item) => item.apps))].sort();
  if (!apps.length) return '';
  const names = apps.map((app) => (phrasing.value.te(`flow.gallery.apps.${app}`) ? phrasing.value.t(`flow.gallery.apps.${app}`) : app));
  return t('flow.recipes.hidden', { apps: new Intl.ListFormat(phrasing.value.locale, { type: 'conjunction' }).format(names) });
});
const invalid = computed(() => setAside.value.filter((item) => item.code === 'flow.recipe_invalid'));

function toggle(recipe: RecipeOut): void {
  open.value = open.value === recipe.ref ? null : recipe.ref;
}

async function attempt(recipe: RecipeOut, action: () => Promise<void>): Promise<void> {
  errors.value = { ...errors.value, [recipe.ref]: undefined };
  try {
    await action();
  } catch (failure) {
    errors.value = { ...errors.value, [recipe.ref]: failure as ApiError };
  }
}

const turnOn = (recipe: RecipeOut) =>
  attempt(recipe, async () => {
    const done = await enable.run({ recipe: recipe.ref });
    void toastSuccess(t('flow.recipes.on', { name: done.flow.name }));
  });

const pause = (recipe: RecipeOut) =>
  attempt(recipe, async () => {
    await disable.run({ recipe: recipe.ref });
    void toastSuccess(t('flow.recipes.off', { name: recipe.installed?.name ?? recipe.name }));
  });

async function backToFactory(recipe: RecipeOut): Promise<void> {
  const yes = await confirm({
    title: t('flow.recipes.restoreTitle'),
    message: t('flow.recipes.restoreMessage'),
    confirmLabel: t('flow.recipes.restoreYes'),
    cancelLabel: t('flow.recipes.restoreNo'),
  });
  if (!yes) return;
  await attempt(recipe, async () => {
    await restore.run({ recipe: recipe.ref });
    void toastSuccess(t('flow.recipes.restored'));
  });
}
</script>

<template>
  <InlineFeedback
    v-if="shelf.error.value && !shelf.data.value"
    tone="danger"
    data-testid="flow-recipes-error"
  >
    {{ $t('flow.recipes.loadError') }}
    <IonButton
      size="small"
      fill="clear"
      data-testid="flow-recipes-retry"
      @click="shelf.refresh()"
    >
      {{ $t('flow.live.retry') }}
    </IonButton>
  </InlineFeedback>
  <div
    v-if="groups.length || setAside.length"
    class="flow-recipes"
    data-testid="flow-recipes"
  >
    <section
      v-for="group in groups"
      :key="group.app"
      class="flow-recipes__app"
      :data-testid="`flow-recipes-${group.app}`"
    >
      <h3 class="flow-recipes__title">
        <HubIcon :name="group.icon" />
        {{ $t('flow.recipes.comesWith', { app: group.name }) }}
      </h3>
      <div class="flow-recipes__grid">
        <article
          v-for="recipe in group.recipes"
          :key="recipe.ref"
          class="flow-recipes__card"
          :class="{ 'flow-recipes__card--open': open === recipe.ref }"
          :data-testid="`flow-recipe-${recipe.ref}`"
        >
          <button
            type="button"
            class="flow-recipes__open"
            :aria-expanded="open === recipe.ref ? 'true' : 'false'"
            :data-testid="`flow-recipe-open-${recipe.ref}`"
            @click="toggle(recipe)"
          >
            <span class="flow-recipes__text">
              <strong>{{ recipe.name }}</strong>
              <span class="flow-recipes__summary">{{ recipe.summary }}</span>
            </span>
            <span class="flow-recipes__pills">
              <StatusPill
                v-if="recipe.installed"
                v-bind="statePill(recipe.installed, phrasing)"
              />
              <StatusPill
                v-if="recipe.installed?.outdated"
                tone="info"
                :label="$t('flow.recipes.newVersion')"
              />
            </span>
          </button>
          <div
            v-if="open === recipe.ref"
            class="flow-recipes__panel"
            :data-testid="`flow-recipe-panel-${recipe.ref}`"
          >
            <p class="flow-recipes__from">
              {{ $t('flow.recipes.comesWithLong', { app: recipe.app_name }) }}
            </p>
            <p v-if="recipe.description">
              {{ recipe.description }}
            </p>
            <InlineFeedback
              v-if="recipe.installed?.outdated"
              tone="info"
            >
              {{ $t('flow.recipes.newVersionLong') }}
            </InlineFeedback>
            <h4>{{ $t('flow.recipes.asks') }}</h4>
            <ul>
              <li
                v-for="grant in recipe.grants"
                :key="grant.operation"
              >
                <strong>{{ actionLabel(grant.operation, catalog, phrasing) }}</strong> — {{ grant.reason }}
              </li>
            </ul>
            <InlineFeedback
              v-if="errors[recipe.ref]"
              tone="danger"
              :data-testid="`flow-recipe-error-${recipe.ref}`"
            >
              {{ wording(errors[recipe.ref], $t('flow.errors.action')) }}
            </InlineFeedback>
            <div class="flow-recipes__actions">
              <IonButton
                v-if="!recipe.installed?.enabled"
                mode="md"
                :disabled="busy"
                :data-testid="`flow-recipe-enable-${recipe.ref}`"
                @click="turnOn(recipe)"
              >
                {{ $t('flow.recipes.enable') }}
              </IonButton>
              <IonButton
                v-else
                mode="md"
                fill="outline"
                :disabled="busy"
                :data-testid="`flow-recipe-disable-${recipe.ref}`"
                @click="pause(recipe)"
              >
                {{ $t('flow.recipes.disable') }}
              </IonButton>
              <IonButton
                v-if="recipe.installed"
                mode="md"
                fill="outline"
                :data-testid="`flow-recipe-see-${recipe.ref}`"
                @click="router.push(`/flow/automations/${recipe.installed.flow_id}`)"
              >
                {{ $t('flow.recipes.see') }}
              </IonButton>
              <IonButton
                v-if="recipe.installed"
                mode="md"
                fill="clear"
                :disabled="busy"
                :data-testid="`flow-recipe-restore-${recipe.ref}`"
                @click="backToFactory(recipe)"
              >
                <HubIcon name="ion:refresh-outline" />{{ $t('flow.recipes.restore') }}
              </IonButton>
              <span
                v-if="!recipe.installed"
                class="flow-recipes__hint"
              >{{ $t('flow.recipes.enableHint') }}</span>
            </div>
          </div>
        </article>
      </div>
    </section>
    <p
      v-if="hidden"
      class="flow-recipes__hint"
      data-testid="flow-recipes-hidden"
    >
      {{ hidden }}
    </p>
    <p
      v-for="item in invalid"
      :key="item.ref"
      class="flow-recipes__hint"
      data-testid="flow-recipes-invalid"
    >
      {{ $t('flow.recipes.invalid', { name: item.name, reason: item.message }) }}
    </p>
  </div>
</template>

<style scoped>
.flow-recipes {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.flow-recipes__app {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.flow-recipes__title {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0.25rem 0 0;
  font-size: 0.95rem;
  font-weight: 600;
}
.flow-recipes__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 18rem), 1fr));
  gap: 0.6rem;
  align-items: start;
}
.flow-recipes__card {
  border: 1px solid var(--ep-border, #d7d5cc);
  border-radius: 14px;
  background: var(--ep-surface, var(--ion-card-background, #fff));
  overflow: hidden;
}
.flow-recipes__card--open {
  grid-column: 1 / -1;
}
.flow-recipes__open {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  width: 100%;
  min-height: 3rem;
  padding: 0.7rem;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.flow-recipes__text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  flex: 1 1 auto;
  min-width: 0;
}
.flow-recipes__pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.3rem;
}
.flow-recipes__summary,
.flow-recipes__hint {
  font-size: 0.85rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-recipes__hint {
  margin: 0;
}
.flow-recipes__panel {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0 0.9rem 0.9rem;
}
.flow-recipes__panel p,
.flow-recipes__panel h4,
.flow-recipes__panel ul {
  margin: 0;
}
.flow-recipes__panel h4 {
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-recipes__from {
  font-weight: 600;
}
.flow-recipes__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
</style>
