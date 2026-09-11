// Versión que el shell del BANCO reporta, fijada a propósito (hub#1752).
//
// El pie del sidebar pinta `v{{ appVersion }}`, y ese número sale de `__APP_VERSION__`, que
// `vite.config.ts` resuelve por env `APP_VERSION` > último tag de git > `package.json`. Sin fijarlo,
// lo que entra en la baseline depende del ESTADO DEL CHECKOUT que la generó: un Mac con tags pinta
// `v1.1.7` y un runner que clona en superficial pinta `v0.0.0` — medido el 11/09 comparando las dos
// capturas del dashboard a 1440px.
//
// ⚠️ Lo que esto NO es: una defensa contra un rojo masivo. Se midió antes de escribir esto, y la
// verdad es la contraria — con `maxDiffPixelRatio: 0.002` (≈2.600 px a 1440×900) el cambio de
// `v1.1.7` a `v0.0.0-bench` (≈600 px de texto) pasa la comparación EN VERDE. O sea que hoy el
// contrato visual ni siquiera ve este cambio; se fija por DETERMINISMO y por paridad local↔CI, no
// porque estuviera tumbando nada. Que el umbral lo absorba es suerte del tamaño de la cadena, no
// diseño: una versión más larga sí puede reflotar el pie. El agujero del umbral —los cambios de
// texto pequeños que el contrato no ve— se sigue aparte, en hub#1823.
//
// El valor NO es un número de versión real a propósito: nadie debe leer una baseline y creer que
// afirma algo sobre la versión que se publica.
export const BENCH_APP_VERSION = '0.0.0-bench';
