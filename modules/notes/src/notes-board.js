// Web Component del módulo "notes" (Lit). ui.entry del manifest; el shell lo carga en runtime.
import { LitElement, html, css } from 'lit';

export class ErpNotesBoard extends LitElement {
  static properties = { notes: { state: true } };
  static styles = css`
    :host { display:block; font-family: system-ui, sans-serif; }
    h2 { margin:0 0 .5rem; font-size:1.1rem; }
    ul { list-style:none; padding:0; margin:0; display:grid; gap:.5rem; }
    li { padding:.7rem .9rem; border:1px solid #e7e2d6; border-radius:.6rem; }
    .t { font-weight:600; color:#1c1b17; }
    .b { color:#8b897f; font-size:.85rem; }
    .ok { color:#16a34a; font-size:.85rem; }
  `;
  constructor() { super(); this.notes = [
    { id:'1', title:'Pedido proveedor', body:'Llamar el lunes' },
    { id:'2', title:'Inventario', body:'Recontar bebidas' },
  ]; }
  render() {
    return html`<h2>Notas <span class="ok">· módulo cargado en runtime ✓</span></h2>
      <ul>${this.notes.map(n => html`<li><div class="t">${n.title}</div><div class="b">${n.body}</div></li>`)}</ul>`;
  }
}
customElements.define('erp-notes-board', ErpNotesBoard);
