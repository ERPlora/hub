// @ionic/core/components/*.js no expone tipos vía `exports` para moduleResolution Bundler.
// Los usamos solo para registrar Web Components (defineCustomElement), así que como módulos
// sin tipos es suficiente. (Finding: alternativa sería tipar cada defineCustomElement.)
declare module '@ionic/core/components/*';
