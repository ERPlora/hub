/**
 * Trae a la vista la pestaña activa del tabbar de footer (ADR-0022).
 *
 * Con más pestañas de las que caben, la barra scrollea en horizontal (polish.css, hub#165). Si la
 * pestaña activa NO viene de un toque sino de la URL —ModuleView deep-linkea `/m/<moduleId>/<navId>`,
 * y hoy `tables` y `verifactu` tienen 5 pestañas, que a 390px ya desbordan— al montar puede quedar
 * fuera de vista y el usuario no ve cuál está activa.
 *
 * Ionic no lo cubre: `ion-segment` no hace `scrollIntoView` y su prop `scrollable` solo cambia
 * layout y gestos. Se usa `scrollLeft` (y no `scrollIntoView`) para no arrastrar a los ancestros
 * scrolleables ni pelearse con el scroll de la página.
 */
export function scrollActiveTabIntoView(segment: HTMLElement | null): void {
  if (!segment) return;

  const activa = segment.querySelector<HTMLElement>('.segment-button-checked');
  if (!activa) return;

  // Todo cabe → no hay nada que traer.
  if (segment.scrollWidth <= segment.clientWidth) return;

  const inicio = activa.offsetLeft;
  const fin = inicio + activa.offsetWidth;
  const visibleInicio = segment.scrollLeft;
  const visibleFin = visibleInicio + segment.clientWidth;

  if (inicio < visibleInicio) {
    segment.scrollLeft = inicio;
  } else if (fin > visibleFin) {
    segment.scrollLeft = fin - segment.clientWidth;
  }
}
