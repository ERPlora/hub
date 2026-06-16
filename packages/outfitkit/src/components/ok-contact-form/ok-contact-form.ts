import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-contact-form — formulario de contacto web/marketing responsive (chrome, como ok-navbar/
// ok-footer; NO es UI de app). Usa ion-input / ion-textarea por dentro para los campos e
// ion-button para enviar (el HOST registra Ionic; aquí no se importa @ionic/core).
//
// Campos por defecto: Nombre, Email, Asunto (opcional), Mensaje (textarea).
// Props:
//   • heading          → título opcional sobre el formulario
//   • submit-label     → texto del botón (def 'Enviar')
//   • action           → URL opcional: si se da, además del evento hace POST nativo (fetch)
//   • success-message  → texto mostrado tras un envío correcto
// Validación básica (requeridos + patrón email): el error se muestra inline bajo el campo y
// no se envía si es inválido.
// Al enviar válido emite `ok-submit` con detail { name, email, subject, message }. Si hay
// `action`, además hace POST y al ok muestra `success-message`.

// Textos i18n del componente (default inglés). Pásalos vía la prop `.labels`.
// (submit-label y success-message siguen siendo props/atributos propios; ver más abajo.)
export interface OkContactFormLabels {
  /** Label del campo Nombre. */
  nameLabel: string;
  /** Label del campo Email. */
  emailLabel: string;
  /** Label del campo Asunto (opcional). */
  subjectLabel: string;
  /** Label del campo Mensaje. */
  messageLabel: string;
  /** Texto del botón mientras se envía. */
  sending: string;
  /** Error: nombre obligatorio. */
  errorNameRequired: string;
  /** Error: email obligatorio. */
  errorEmailRequired: string;
  /** Error: email con formato inválido. */
  errorEmailInvalid: string;
  /** Error: mensaje obligatorio. */
  errorMessageRequired: string;
  /** Error: el POST falló (respuesta no-ok). */
  errorSendFailed: string;
  /** Error: el POST falló por red/conexión. */
  errorNetwork: string;
}

const DEFAULT_LABELS: OkContactFormLabels = {
  nameLabel: 'Name',
  emailLabel: 'Email',
  subjectLabel: 'Subject (optional)',
  messageLabel: 'Message',
  sending: 'Sending…',
  errorNameRequired: 'Name is required.',
  errorEmailRequired: 'Email is required.',
  errorEmailInvalid: 'Enter a valid email.',
  errorMessageRequired: 'Message is required.',
  errorSendFailed: 'Could not send. Please try again.',
  errorNetwork: 'Could not send. Check your connection.',
};

export class OkContactForm extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --background: var(--ok-surface, var(--ion-card-background, #ffffff));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.55));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.12));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --danger-color: var(--ok-danger, var(--ion-color-danger, #c5000f));
      --success-color: var(--ok-success, var(--ion-color-success, #2dd55b));
      --border-radius: var(--ok-radius, var(--ion-border-radius, 8px));
      --max-width: var(--ok-container-max, 640px);
      --padding: var(--ok-spacing, var(--ion-padding, 16px));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* El host ocupa el ancho del contenedor; el formulario se centra con un max-width interno. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
    }
    .wrap {
      box-sizing: border-box;
      max-width: var(--max-width);
      margin-inline: auto;
      background: var(--background);
      padding: var(--padding);
    }
    .heading {
      margin: 0 0 1rem;
      font-size: 1.4rem;
      font-weight: 700;
    }
    /* Grid responsive: 2 columnas en desktop (nombre/email), apilado en móvil. */
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }
    /* Mensaje y asunto a ancho completo (ocupan toda la fila del grid). */
    .field.full {
      grid-column: 1 / -1;
    }
    .control {
      --border-color: var(--border-color);
      --border-radius: var(--border-radius);
    }
    .control[data-invalid] {
      --border-color: var(--danger-color);
      --highlight-color-invalid: var(--danger-color);
    }
    .error {
      color: var(--danger-color);
      font-size: 0.8rem;
      min-height: 1em;
    }
    .actions {
      grid-column: 1 / -1;
      display: flex;
      justify-content: flex-end;
    }
    .success {
      color: var(--success-color);
      font-weight: 600;
      padding: 0.5rem 0;
    }
    @media (max-width: 640px) {
      /* Móvil: todo apilado y botón a ancho completo. */
      .grid { grid-template-columns: 1fr; }
      .actions { justify-content: stretch; }
      .actions ion-button { flex: 1; }
    }
  `;

  /** Título opcional sobre el formulario. */
  @property() heading?: string;
  /** Texto del botón de envío. */
  @property({ attribute: 'submit-label' }) submitLabel = 'Send';
  /** URL opcional: si se da, el envío válido hace además POST nativo (fetch). */
  @property() action?: string;
  /** Texto mostrado tras un envío correcto. */
  @property({ attribute: 'success-message' }) successMessage = 'Thanks! We’ll get back to you soon.';
  /** Textos i18n (default inglés); pasa solo las claves que quieras sobreescribir. */
  @property({ attribute: false }) labels: Partial<OkContactFormLabels> = {};

  // Textos efectivos: defaults inglés sobreescritos por los pasados desde fuera.
  private get t(): OkContactFormLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Valores actuales de los campos (controlados internamente).
  @state() private values = { name: '', email: '', subject: '', message: '' };
  // Errores inline por campo.
  @state() private errors: Record<string, string> = {};
  // Mostrar el mensaje de éxito tras enviar.
  @state() private sent = false;
  // Bloqueo del botón mientras se hace POST.
  @state() private sending = false;

  // Patrón de email básico (suficiente para validación de cliente; el server valida de verdad).
  private static EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  // Lee el valor del ion-input/ion-textarea y lo guarda en el campo correspondiente.
  private onInput(field: keyof typeof this.values) {
    return (e: Event) => {
      const value = (e as CustomEvent).detail?.value ?? '';
      this.values = { ...this.values, [field]: value };
      // Limpia el error del campo en cuanto el usuario edita (UX).
      if (this.errors[field]) {
        const { [field]: _omit, ...rest } = this.errors;
        this.errors = rest;
      }
    };
  }

  // Valida requeridos + patrón email. Devuelve true si todo es válido.
  private validate(): boolean {
    const errors: Record<string, string> = {};
    const { name, email, message } = this.values;
    if (!name.trim()) errors.name = this.t.errorNameRequired;
    if (!email.trim()) errors.email = this.t.errorEmailRequired;
    else if (!OkContactForm.EMAIL_RE.test(email.trim())) errors.email = this.t.errorEmailInvalid;
    if (!message.trim()) errors.message = this.t.errorMessageRequired;
    this.errors = errors;
    return Object.keys(errors).length === 0;
  }

  private async onSubmit(e: Event): Promise<void> {
    // Siempre prevenimos el submit nativo: el POST (si hay action) lo hacemos por fetch.
    e.preventDefault();
    if (this.sending) return;
    if (!this.validate()) return;

    const detail = {
      name: this.values.name.trim(),
      email: this.values.email.trim(),
      subject: this.values.subject.trim(),
      message: this.values.message.trim(),
    };

    // Evento normalizado ok-* para el consumidor (Django/Lit/Vue).
    this.dispatchEvent(
      new CustomEvent('ok-submit', { detail, bubbles: true, composed: true }),
    );

    // Sin action → solo evento; mostramos éxito directamente.
    if (!this.action) {
      this.markSent();
      return;
    }

    // Con action → POST nativo vía fetch (form-urlencoded, sin deps).
    this.sending = true;
    try {
      const body = new URLSearchParams(detail as Record<string, string>);
      const res = await fetch(this.action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      if (res.ok) this.markSent();
      else this.errors = { ...this.errors, message: this.t.errorSendFailed };
    } catch {
      this.errors = { ...this.errors, message: this.t.errorNetwork };
    } finally {
      this.sending = false;
    }
  }

  // Marca el formulario como enviado y limpia los campos.
  private markSent(): void {
    this.sent = true;
    this.values = { name: '', email: '', subject: '', message: '' };
    this.errors = {};
  }

  render(): unknown {
    if (this.sent) {
      return html`<div class="wrap"><div class="success" role="status">${this.successMessage}</div></div>`;
    }
    return html`
      <div class="wrap">
        ${this.heading ? html`<h2 class="heading">${this.heading}</h2>` : null}
        <form class="grid" novalidate @submit=${this.onSubmit}>
          <div class="field">
            <ion-input
              class="control"
              name="name"
              label=${this.t.nameLabel}
              label-placement="stacked"
              fill="outline"
              .value=${this.values.name}
              ?data-invalid=${!!this.errors.name}
              @ionInput=${this.onInput('name')}
            ></ion-input>
            <span class="error">${this.errors.name ?? ''}</span>
          </div>
          <div class="field">
            <ion-input
              class="control"
              name="email"
              type="email"
              inputmode="email"
              label=${this.t.emailLabel}
              label-placement="stacked"
              fill="outline"
              .value=${this.values.email}
              ?data-invalid=${!!this.errors.email}
              @ionInput=${this.onInput('email')}
            ></ion-input>
            <span class="error">${this.errors.email ?? ''}</span>
          </div>
          <div class="field full">
            <ion-input
              class="control"
              name="subject"
              label=${this.t.subjectLabel}
              label-placement="stacked"
              fill="outline"
              .value=${this.values.subject}
              @ionInput=${this.onInput('subject')}
            ></ion-input>
          </div>
          <div class="field full">
            <ion-textarea
              class="control"
              name="message"
              label=${this.t.messageLabel}
              label-placement="stacked"
              fill="outline"
              auto-grow
              rows="5"
              .value=${this.values.message}
              ?data-invalid=${!!this.errors.message}
              @ionInput=${this.onInput('message')}
            ></ion-textarea>
            <span class="error">${this.errors.message ?? ''}</span>
          </div>
          <div class="actions">
            <ion-button type="submit" ?disabled=${this.sending}>
              ${this.sending ? this.t.sending : this.submitLabel}
            </ion-button>
          </div>
        </form>
      </div>
    `;
  }
}

define('ok-contact-form', OkContactForm);

declare global {
  interface HTMLElementTagNameMap {
    'ok-contact-form': OkContactForm;
  }
}
