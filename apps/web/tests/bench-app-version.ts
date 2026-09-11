// Versión que el shell del BANCO reporta, fijada a propósito (hub#1752).
//
// El pie del sidebar pinta `v{{ appVersion }}`, y ese número sale de `__APP_VERSION__`, que
// `vite.config.ts` resuelve por env `APP_VERSION` > último tag de git > `package.json`. Sin fijarlo,
// lo que entra en la baseline depende del ESTADO DEL CHECKOUT que la generó: un Mac con tags pinta
// `v1.1.7` y un runner que clona en superficial pinta `v0.0.0` — medido el 11/09 comparando las dos
// capturas del dashboard a 1440px.
//
// ⚠️ What this is NOT: a defence against a mass red. It is pinned for DETERMINISM and for
// local<->CI parity, not because it was ever knocking anything over — when this was written the
// bench could not even SEE the change: with the budget of the day (`maxDiffPixelRatio: 0.002`,
// 2592 px at 1440x900) going from `v1.1.7` to `v0.0.0-bench` passed GREEN.
//
// That hole is closed since hub#1823: the budget is an absolute 20 px (`visual-diff-budget.ts`),
// and the same change is now measured at 106 px — one single digit is 33 px — so the footer is
// back inside the contract and this constant is what keeps it from moving on its own.
//
// El valor NO es un número de versión real a propósito: nadie debe leer una baseline y creer que
// afirma algo sobre la versión que se publica.
export const BENCH_APP_VERSION = '0.0.0-bench';
