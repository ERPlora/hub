// Fixture for hub#2414: a module whose footer tabs carry the labels of Reservations in Spanish
// («Reservas · Lista de espera · Disponibilidad»). The screens are empty on purpose: what the spec
// measures is the tab strip the SHELL paints from `navigation[]`, not the module's content.
for (const id of ['list', 'waitlist', 'availability']) {
  customElements.define(
    `erp-e2e-tabs-${id}`,
    class extends HTMLElement {
      connectedCallback() {
        const heading = document.createElement('h2');
        heading.dataset.testid = `e2e-tabs-${id}`;
        heading.textContent = id;
        this.replaceChildren(heading);
      }
    },
  );
}
