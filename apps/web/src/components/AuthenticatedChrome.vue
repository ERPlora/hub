<template>
  <!-- Renderless on purpose: it adds no element of its own, so whatever it wraps keeps the exact
       DOM parent it had (the `ion-menu` stays a direct child of `ion-split-pane`, which is how
       Ionic pairs it with `content-id`). -->
  <slot v-if="visible" />
</template>

<script setup lang="ts">
/**
 * The one gate of the shell's authenticated chrome (hub#925).
 *
 * Everything that only makes sense to someone already inside their business — the side menu with
 * the account card and the navigation, the assistant drawer, the elevation dialog — goes inside
 * this component. Nothing else decides it: there is a single `v-if` for the whole shell, here.
 *
 * **Why this is not `v-if="isAuthed"`.** `isAuthed` is `user != null`, and that is not «there is a
 * session»: it is «there was one and its trace is still in localStorage». The login screen was
 * therefore painted with the full sidebar around it — account name and email included — every time
 * anything landed on `/login` without clearing that trace first (a hub session that died, hub#902 /
 * hub#846; a boot race, hub#858; a typed URL). One screen claiming both «this is who you are» and
 * «say who you are».
 *
 * The invariant is about the ROUTE as much as the session: chrome exists where a session is
 * REQUIRED and PRESENT. «Required» is already declared, once per route, by the router's
 * `meta.auth` — the same flag the auth gate reads to send visitors to `/login`. So a screen that
 * asks for credentials (`/login`, `/auth/google/callback`) is outside the shell by construction,
 * and a new public screen inherits that the moment it is declared, with nobody remembering
 * anything.
 */
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { isAuthed } from '../lib/session';

const route = useRoute();

const visible = computed<boolean>(() => isAuthed.value && route.meta.auth === true);
</script>
