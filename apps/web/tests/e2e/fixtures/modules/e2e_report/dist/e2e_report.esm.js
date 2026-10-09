// Fixture for hub#2539: a report only an administrator may open (its tab and its query carry
// `e2e_report.view`, which only the admin role holds). It reads its figure ONCE, when it mounts —
// like any real report — so whatever it painted stays on screen until the page is mounted again.
class E2eReport extends HTMLElement {
  connectedCallback() {
    this.textContent = 'report:loading';
    Promise.resolve(this.client?.query('e2e_report.figures.get', {}))
      .then((rows) => { this.textContent = `report:${JSON.stringify(rows)}`; })
      .catch((e) => { this.textContent = `report:refused:${e?.code ?? 'error'}`; });
  }
}
customElements.define('erp-e2e-report', E2eReport);
