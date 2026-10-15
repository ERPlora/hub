<script setup lang="ts">
// Schedules → Special days (WORKBOOK «Pantallas · Días especiales»): two tables one under the other, each
// with its title, as the old screen — the special days (a date) and the overrides (a range of dates).
import { AppPage } from '@erplora/ui/shell';

import OverridesList from '../components/OverridesList.vue';
import SpecialDaysList from '../components/SpecialDaysList.vue';
import { scheduleTabs } from '../tabs';
</script>

<template>
  <AppPage
    :title="$t('schedule.title')"
    :tabs="scheduleTabs($t)"
    :tabs-label="$t('schedule.tabs.label')"
  >
    <div class="schedule-special-days">
      <SpecialDaysList />
      <OverridesList />
    </div>
  </AppPage>
</template>

<style scoped>
.schedule-special-days {
  display: grid;
  gap: 1.5rem;
}
</style>
