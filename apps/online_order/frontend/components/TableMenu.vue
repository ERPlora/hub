<script setup lang="ts">
// The menu a customer reads on their phone after scanning their table's QR (ONLINE_ORDER-F03): the business and the
// table with its zone above it, the set menus and then each category with its dishes. Opening a dish reads its options;
// opening a set menu shows its courses. Its calls go through base's public door, with the table's code in their body.
import { EmptyState, InlineFeedback, type Money } from '@erplora/ui/components';
import { type ApiClient, ApiError } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonButton, IonCol, IonGrid, IonList, IonListHeader, IonRow, IonSpinner, IonText } from '@ionic/vue';
import { computed, onMounted, ref } from 'vue';

import { useBaseI18n } from '../../../../base/frontend/lib/i18n';
import type { MenuComboOut, MenuItemOut, PublicMenuOut } from '../operations';
import DishSheet, { type ChoiceGroup, type OpenedDish } from './DishSheet.vue';
import MenuDish from './MenuDish.vue';

const props = defineProps<{ api: ApiClient; money: Money | undefined; code: string }>();
const { t } = useBaseI18n();

const menu = ref<PublicMenuOut | null>(null);
const loading = ref(true);
const failure = ref<ApiError | null>(null);
const notActive = computed(() => failure.value?.code === 'online_order.qr_not_active');
const isEmpty = computed(() => !!menu.value && !menu.value.groups.length && !menu.value.combos.length);

async function load(): Promise<void> {
  loading.value = true;
  failure.value = null;
  try {
    menu.value = await props.api.call('online_order.public.menu', { code: props.code });
  } catch (error) {
    menu.value = null;
    failure.value = error instanceof ApiError ? error : new ApiError(0, 'client_error', String(error));
  } finally {
    loading.value = false;
  }
}

const sheetOpen = ref(false);
const opened = ref<OpenedDish>({ name: '', description: '', price: 0, image_url: '', allergens: [] });
const groups = ref<ChoiceGroup[]>([]);
const optionsLoading = ref(false);
const optionsFailed = ref(false);
let openedDish = '';

async function loadOptions(): Promise<void> {
  const dish = openedDish;
  optionsLoading.value = true;
  optionsFailed.value = false;
  try {
    const read = await props.api.call('online_order.public.options', { code: props.code, product_id: dish });
    if (dish !== openedDish) return;
    groups.value = read.groups.map((group) => ({ ...group, choices: group.options }));
  } catch {
    if (dish === openedDish) optionsFailed.value = true;
  } finally {
    if (dish === openedDish) optionsLoading.value = false;
  }
}

function openDish(dish: MenuItemOut): void {
  opened.value = dish;
  groups.value = [];
  openedDish = dish.id;
  sheetOpen.value = true;
  void loadOptions();
}

function openCombo(combo: MenuComboOut): void {
  opened.value = { ...combo, description: '', allergens: [] };
  groups.value = combo.courses;
  openedDish = '';
  optionsLoading.value = false;
  optionsFailed.value = false;
  sheetOpen.value = true;
}

function courses(combo: MenuComboOut): string {
  return combo.courses.map((course) => course.name).join(' · ');
}

onMounted(load);
</script>

<template>
  <AppPage
    :title="t('online_order.menu.title')"
    content-layout="detail"
  >
    <ion-grid>
      <ion-row class="ion-justify-content-center">
        <ion-col
          size="12"
          size-md="10"
          size-lg="8"
          size-xl="6"
        >
          <p
            v-if="loading"
            data-testid="oo-menu-loading"
            role="status"
          >
            <ion-spinner name="crescent" />
            {{ t('online_order.menu.loading') }}
          </p>
          <EmptyState
            v-else-if="notActive"
            icon="ion:qr-code-outline"
            :heading="t('online_order.menu.notActive')"
            :message="t('online_order.menu.notActiveMessage')"
            data-testid="oo-menu-not-active"
          />
          <InlineFeedback
            v-else-if="failure"
            tone="danger"
            role="alert"
            data-testid="oo-menu-error"
          >
            {{ t('online_order.menu.loadError') }}
            <template #actions>
              <ion-button
                fill="clear"
                data-testid="oo-menu-retry"
                @click="load"
              >
                {{ t('online_order.menu.retry') }}
              </ion-button>
            </template>
          </InlineFeedback>
          <template v-else-if="menu">
            <header>
              <h2
                v-if="menu.business_name"
                class="ion-no-margin"
                data-testid="oo-menu-business"
              >
                {{ menu.business_name }}
              </h2>
              <ion-text color="medium">
                <p
                  class="ion-no-margin"
                  data-testid="oo-menu-table"
                >
                  {{ t('online_order.sheet.table', { number: menu.table_number }) }}<template v-if="menu.zone_name">
                    · {{ menu.zone_name }}
                  </template>
                </p>
              </ion-text>
            </header>
            <EmptyState
              v-if="isEmpty"
              icon="ion:restaurant-outline"
              :heading="t('online_order.menu.empty')"
              :message="t('online_order.menu.emptyMessage')"
              data-testid="oo-menu-empty"
            />
            <ion-list
              v-if="menu.combos.length"
              data-testid="oo-menu-group"
            >
              <ion-list-header>{{ t('online_order.menu.menus') }}</ion-list-header>
              <MenuDish
                v-for="combo in menu.combos"
                :key="combo.id"
                :name="combo.name"
                :detail="courses(combo)"
                :price="combo.price"
                :image-url="combo.image_url"
                :allergens="[]"
                :money="money"
                :testid="`oo-menu-combo-${combo.id}`"
                @open="openCombo(combo)"
              />
            </ion-list>
            <ion-list
              v-for="(group, index) in menu.groups"
              :key="`${index}-${group.name}`"
              data-testid="oo-menu-group"
            >
              <ion-list-header>{{ group.name || t('online_order.menu.moreDishes') }}</ion-list-header>
              <MenuDish
                v-for="dish in group.items"
                :key="dish.id"
                :name="dish.name"
                :detail="dish.description"
                :price="dish.price"
                :image-url="dish.image_url"
                :allergens="dish.allergens"
                :money="money"
                :testid="`oo-menu-dish-${dish.id}`"
                @open="openDish(dish)"
              />
            </ion-list>
            <DishSheet
              v-model:open="sheetOpen"
              :dish="opened"
              :groups="groups"
              :money="money"
              :loading="optionsLoading"
              :error="optionsFailed"
              @retry="loadOptions"
            />
          </template>
        </ion-col>
      </ion-row>
    </ion-grid>
  </AppPage>
</template>
