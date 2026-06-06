// Declaración mínima de los custom elements de Ionic para el JSX de Stencil.
// El shell (apps/web = @ionic/react) registra los `ion-*` globalmente en runtime;
// aquí solo los declaramos para que el typecheck de Stencil no falle al usarlos.
// No se bundlean en el módulo: Ionic lo provee el shell.
declare namespace JSX {
  interface IntrinsicElements {
    'ion-searchbar': any;
    'ion-button': any;
    'ion-buttons': any;
    'ion-icon': any;
    'ion-input': any;
    'ion-select': any;
    'ion-select-option': any;
    'ion-item': any;
    'ion-label': any;
    'ion-list': any;
    'ion-spinner': any;
    'ion-badge': any;
    'ion-chip': any;
    'ion-note': any;
  }
}
