// Rutas con nombre simbólico que usa el chrome del shell (topbar/sidebar), para no repetir
// strings de path. Centralizar facilita cambiarlas cuando existan las pantallas dedicadas.

// Perfil del usuario. NOTA: el Hub aún NO tiene una pantalla de perfil dedicada (no hay
// ProfilePage.vue ni ruta /profile). Hasta que exista, el avatar de la topbar y el enlace
// "perfil" del footer del sidebar apuntan a Ajustes (la pantalla más cercana). Cuando se cree la
// pantalla de perfil, basta cambiar esta constante (y registrar la ruta).
export const PROFILE_ROUTE = '/settings';
