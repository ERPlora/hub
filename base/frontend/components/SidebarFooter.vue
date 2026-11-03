<script setup lang="ts">
// base's piece of the side menu's foot (`createShell({ chrome: { sidebarFooter } })`, BASE-F11), between the QR and the
// brand: «Upgrade plan», then right below it «Manage on erplora.com». Each decides for itself whether it shows: the
// first sells, so only on the web; the second, wherever the server embeds the way to the panel, save the Google Play copy.
import ManageLink from './ManageLink.vue';
import UpgradePlanLink from './UpgradePlanLink.vue';
</script>

<template>
  <div class="sidebar-footer">
    <UpgradePlanLink />
    <ManageLink />
  </div>
</template>

<style scoped>
.sidebar-footer {
  display: grid;
  gap: 2px;
}
</style>
