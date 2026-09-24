// Fixture for hub#1797: the agenda's «Charge» — the exact navigation `appointments` does
// (`goToTill()`): push the till's address with the booking and tell the shell with `popstate`.
class E2eAgenda extends HTMLElement {
  connectedCallback() {
    const button = document.createElement('button');
    button.dataset.testid = 'e2e-agenda-charge';
    button.textContent = 'Charge';
    button.addEventListener('click', () => {
      window.history.pushState({}, '', '/m/e2e_till/pos?ticket=T1');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    this.replaceChildren(button);
  }
}
customElements.define('erp-e2e-agenda', E2eAgenda);
