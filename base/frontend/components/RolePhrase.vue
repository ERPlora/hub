<script setup lang="ts">
// What a permission lets a person do, in business words, marked while the role is left to review it.
import { StatusPill } from '@erplora/ui/components';

import { useBaseI18n } from '../lib/i18n';

defineProps<{ phrase: string; review: boolean }>();

const { t } = useBaseI18n();
</script>

<template>
  <span class="ion-text-wrap">
    {{ phrase }}
    <StatusPill
      v-if="review"
      size="sm"
      tone="warning"
      data-testid="role-to-review"
      :label="t('base.roles.toReview')"
    />
  </span>
</template>
