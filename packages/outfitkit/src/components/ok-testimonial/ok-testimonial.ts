import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-testimonial — cita de cliente (prueba social): rating opcional, cita (slot default),
// avatar + autor + rol. `glass` para cristal esmerilado.
//
//   <ok-testimonial rating="5" author="Marina Ribó" role="Gerente · Café Central" avatar="/m.jpg">
//     Cambiamos 7 herramientas por ERPlora y cerramos caja en la mitad de tiempo.
//   </ok-testimonial>
export class OkTestimonial extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      height: 100%;
      --color: var(--ok-text, var(--ion-text-color, #18181b));
      --muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.62));
      --surface: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #fff)));
      --border: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.1));
      --radius: var(--ok-radius, 18px);
      --star: var(--ion-color-warning, #ffc409);
      --primary: var(--ion-color-primary, #1496d6);
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
    }
    .card {
      box-sizing: border-box;
      height: 100%;
      display: flex;
      flex-direction: column;
      gap: 1rem;
      padding: clamp(1.4rem, 2.5vw, 2rem);
      color: var(--color);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      position: relative;
    }
    :host([glass]) .card {
      background: color-mix(in oklab, var(--surface) 62%, transparent);
      -webkit-backdrop-filter: blur(14px) saturate(1.4);
      backdrop-filter: blur(14px) saturate(1.4);
      border-color: color-mix(in oklab, var(--color) 12%, transparent);
    }
    .quote-mark {
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 3rem;
      line-height: 0.6;
      color: color-mix(in oklab, var(--primary) 35%, transparent);
      height: 1.2rem;
    }
    .stars {
      display: inline-flex;
      gap: 0.1rem;
      color: var(--star);
      font-size: 0.95rem;
    }
    .quote {
      flex: 1;
      font-size: clamp(1rem, 0.95rem + 0.35vw, 1.2rem);
      line-height: 1.55;
      letter-spacing: -0.01em;
    }
    ::slotted(*) { margin: 0; }
    .author {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-top: auto;
    }
    .avatar {
      width: 2.5rem;
      height: 2.5rem;
      border-radius: 999px;
      object-fit: cover;
      flex: 0 0 auto;
      background: color-mix(in oklab, var(--primary) 16%, transparent);
      display: grid;
      place-items: center;
      color: var(--primary);
      font-weight: 700;
      font-size: 0.9rem;
    }
    .meta { min-width: 0; }
    .name { font-weight: 650; font-size: 0.95rem; }
    .role { color: var(--muted); font-size: 0.82rem; }
  `;

  /** Nº de estrellas (0–5). Si 0/undefined no se muestran. */
  @property({ type: Number }) rating = 0;
  /** Nombre del autor. */
  @property() author?: string;
  /** Rol / empresa del autor (atributo HTML: author-role; `role` está reservado por ARIA). */
  @property({ attribute: 'author-role' }) authorRole?: string;
  /** URL del avatar. Si no hay, se muestran las iniciales del autor. */
  @property() avatar?: string;
  /** Cristal esmerilado. */
  @property({ type: Boolean, reflect: true }) glass = false;

  private initials(): string {
    if (!this.author) return '';
    return this.author
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0] ?? '')
      .join('')
      .toUpperCase();
  }

  render(): unknown {
    const r = Math.max(0, Math.min(5, Math.round(this.rating)));
    return html`
      <div class="card">
        ${r ? html`<span class="stars" aria-label="${r} de 5">${'★'.repeat(r)}</span>` : html`<span class="quote-mark">”</span>`}
        <div class="quote"><slot></slot></div>
        <div class="author">
          ${this.avatar
            ? html`<img class="avatar" src=${this.avatar} alt=${this.author ?? ''} />`
            : html`<span class="avatar">${this.initials()}</span>`}
          <div class="meta">
            ${this.author ? html`<div class="name">${this.author}</div>` : null}
            ${this.authorRole ? html`<div class="role">${this.authorRole}</div>` : null}
          </div>
        </div>
      </div>
    `;
  }
}

define('ok-testimonial', OkTestimonial);

declare global {
  interface HTMLElementTagNameMap {
    'ok-testimonial': OkTestimonial;
  }
}
