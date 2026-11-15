<script setup lang="ts">
// This hub's plan page on erplora.com (`hub-home`, embedded by `base/spa.py`), shown for every profile because the
// owner often comes in through the till's session; erplora.com decides what each profile may do there. Its click goes
// with the pass so the person arrives signed in, and the link keeps the plain address for when the browser blocks the
// new tab. It sells, so it shows only on the web (`useSurface`).
import { HubIcon } from '@erplora/ui/shell';

import { usePlanLink } from '../lib/plan-link';
import PlanUpgradeLink from './PlanUpgradeLink.vue';

const { planUrl, offered } = usePlanLink();
</script>

<template>
  <PlanUpgradeLink
    v-if="offered"
    class="upgrade-plan"
    data-testid="upgrade-plan"
    :url="planUrl"
    :title="$t('base.plan.upgrade')"
    :aria-label="$t('base.plan.upgrade')"
  >
    <HubIcon name="ion:sparkles-outline" />
    <!-- The menu folded to its rail (≥992 px) hides every `.nav-label` (polish.css): the icon stays, named above. -->
    <span class="nav-label">{{ $t('base.plan.upgrade') }}</span>
  </PlanUpgradeLink>
</template>

<style scoped>
.upgrade-plan {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border-radius: var(--ep-radius, 12px);
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
}

.upgrade-plan:hover,
.upgrade-plan:focus-visible {
  background: color-mix(in oklab, var(--ion-color-primary) 8%, transparent);
  color: var(--ion-color-primary);
}
</style>
