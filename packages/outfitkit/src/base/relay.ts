// Re-emite un evento de un `ion-*` interno como evento `ok-*` del host, preservando `detail`.
// Los wrappers ocultan Ionic: el consumidor escucha SIEMPRE eventos `ok-*`, nunca `ionInput`/
// `ionChange`. `composed: true` deja que el evento cruce el shadow DOM del wrapper.
export function relay(host: HTMLElement, source: Event, type: string): void {
  host.dispatchEvent(
    new CustomEvent(type, {
      detail: (source as CustomEvent).detail,
      bubbles: true,
      composed: true,
    }),
  );
}
