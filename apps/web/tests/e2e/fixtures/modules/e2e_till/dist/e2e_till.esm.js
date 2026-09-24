// Fixture for hub#1797: a till that follows the module deep-link contract exactly as `sales` does
// (sales#279, flows#57). It serves `?ticket=` when its boot settles AND on every `popstate`, and
// consumes the link with `replaceState` — which is what makes two live copies race: whichever
// copy serves first erases the link from the address before the other one reads it.
let seq = 0;
class E2eTill extends HTMLElement {
  constructor() {
    super();
    this.instance = String(++seq);
    this.served = '';
    this.booted = false;
    this.onPopState = () => { if (this.booted) this.serve(); };
  }
  connectedCallback() {
    this.dataset.instance = this.instance;
    window.addEventListener('popstate', this.onPopState);
    this.render();
    // The boot reads over the network in the real module; a short wait keeps its ordering.
    setTimeout(() => { this.booted = true; this.dataset.booted = '1'; this.serve(); }, 150);
  }
  disconnectedCallback() {
    window.removeEventListener('popstate', this.onPopState);
  }
  serve() {
    if (!this.isConnected || !window.location.pathname.endsWith('/m/e2e_till/pos')) return;
    const url = new URL(window.location.href);
    const ticket = url.searchParams.get('ticket');
    if (!ticket) return;
    url.searchParams.delete('ticket');
    window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
    this.served = ticket;
    this.render();
  }
  render() {
    this.dataset.served = this.served;
    this.textContent = this.served ? `ticket:${this.served}` : 'ticket:none';
  }
}
customElements.define('erp-e2e-till', E2eTill);
