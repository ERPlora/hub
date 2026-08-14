// Urls de los assets de un módulo, direccionadas POR VERSIÓN (hub#935).
//
// El defecto: todas las versiones de un módulo se servían desde la misma url
// (`/modules/<id>/dist/<id>.esm.js`) y sin ninguna cabecera de caché. Al actualizar, el `import()`
// del shell pedía ese mismo recurso, la caché lo contestaba con los bytes de la versión anterior, y
// el custom element quedaba registrado con el código VIEJO mientras el manifest, la ficha del
// marketplace y la lista de apps decían la versión NUEVA. Sin ningún aviso — lo que hace invisible
// el arreglo de cualquier módulo de la flota.
//
// La versión va en la RUTA y no en la query porque la clave de caché del borde ignora la query
// (probado en un hub real: `?v=$RANDOM` sigue devolviendo `cf-cache-status: HIT`). Una ruta distinta
// no la puede ignorar nadie.
//
// Vive en su propio fichero, sin dependencias, porque lo necesitan los dos lados de la línea: el
// cargador de módulos (navegador) y la config de Vite (dev, Node).

/** Base de la que cuelgan los assets de un módulo. Con `version` conocida, la ruta la incluye. */
export function moduleBase(moduleId: string, version?: string | null): string {
  const base = `/modules/${moduleId}`;
  // Sin versión (runtime anterior a hub#935, manifest sin `version`) se cae a la url de siempre: el
  // runtime la marca «revalida siempre», así que sigue siendo correcta — solo que no cacheable.
  return version ? `${base}/v/${encodeURIComponent(version)}` : base;
}

/** `/modules/<id>/v/<version>/<resto>` → `/modules/<id>/<resto>`. Lo demás, tal cual. */
export function stripModuleVersion(url: string): string {
  // Solo el TERCER segmento cuenta como marcador de versión: un directorio `v/` más adentro del
  // módulo es contenido suyo y se sirve tal cual.
  return url.replace(/^\/modules\/([^/]+)\/v\/[^/]+\//, '/modules/$1/');
}
