<script setup lang="ts">
// «Upgrade plan» at the foot of the side menu (BASE-G169; the old hub's, HUB_SHELL-F129): this hub's plan page
// on erplora.com, which `base/spa.py` embeds in `hub-home`, for every profile (the owner often comes in through
// the till's session); what the hub may do there, erplora.com decides by profile. Its click goes with the pass
// (BASE-F11, `useSaasPass`), so the person arrives already signed in; the link keeps the usual address, for when the
// browser blocks the new tab. It sells, so only on the web (`useSurface`).
import { HubIcon } from '@erplora/ui/shell';

import { usePlanLink } from '../lib/plan-link';
import { useSaasPass } from '../lib/saas-pass';

const { planUrl, offered } = usePlanLink();
const { openSaasPass } = useSaasPass();
</script>

<template>
  <a
    v-if="offered"
    class="upgrade-plan"
    data-testid="upgrade-plan"
    :href="planUrl"
    target="_blank"
    rel="noopener"
    :title="$t('base.plan.upgrade')"
    :aria-label="$t('base.plan.upgrade')"
    @click="openSaasPass('plan', planUrl, $event)"
  >
    <HubIcon name="ion:sparkles-outline" />
    <!-- The menu folded to its rail (≥992 px) hides every `.nav-label` (polish.css): the icon stays, named above. -->
    <span class="nav-label">{{ $t('base.plan.upgrade') }}</span>
  </a>
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
