<script setup lang="ts">
// «Manage on erplora.com» at the foot of the side menu, right below «Upgrade plan» (BASE-F11; the old hub's
// `management-link.ts`, gh:hub#364, gh:hub#1400): this business on erplora.com's panel. It shows only where
// `base/spa.py` embeds its address (`hub-home`'s `manage_url`: whoever may open the panel, with their account, never a
// PIN session) and never in the Google Play copy (`managementOffered`: nothing until the installed app answers). It does
// not sell, so unlike «Upgrade plan» the installed app offers it too; its click goes the Hub's one way out,
// `openExternalLink` (gh:hub#439: a new tab in a browser, the system browser in the installed app).
import { HubIcon, openExternalLink } from '@erplora/ui/shell';
import { computed } from 'vue';

import { type HubHome, readJsonBlock } from '../lib/home';
import { managementOffered } from '../lib/management';

const manageUrl = readJsonBlock<HubHome>('hub-home')?.manage_url ?? '';
const offered = managementOffered();
const shown = computed(() => manageUrl !== '' && offered.value);
</script>

<template>
  <a
    v-if="shown"
    class="manage-link"
    data-testid="menu-manage"
    :href="manageUrl"
    target="_blank"
    rel="noopener"
    :title="$t('base.plan.manage')"
    :aria-label="$t('base.plan.manage')"
    @click="openExternalLink(manageUrl, $event)"
  >
    <HubIcon name="ion:open-outline" />
    <!-- The menu folded to its rail (≥992 px) hides every `.nav-label` (polish.css): the icon stays, named above. -->
    <span class="nav-label">{{ $t('base.plan.manage') }}</span>
  </a>
</template>

<style scoped>
.manage-link {
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

.manage-link:hover,
.manage-link:focus-visible {
  background: color-mix(in oklab, var(--ion-color-primary) 8%, transparent);
  color: var(--ion-color-primary);
}
</style>
