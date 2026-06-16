import { LitElement, html, svg, css, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-org-chart — organigrama jerárquico (nodo-y-conector), distinto del ok-tree indentado.
// Render REAL con layout calculado (tidy-tree): cada nodo recibe coordenadas x/y; los
// conectores se dibujan como rutas SVG vectoriales y los nodos como HTML absolutamente
// posicionado (conservan el estilo `.node`, el `:hover` y el theming por tokens --ion-*/--ok-*).
// Un organigrama no cabe en ancho de móvil, así que NO se intenta hacer "responsive": se monta
// en un viewport con pan (arrastrar) + zoom (rueda/pinch + botones) y "ajustar a pantalla".
// Presentacional respecto a los datos: recibe el árbol por `root` y lo dibuja recursivamente.

/** Un nodo del organigrama (recursivo vía `children`). */
export interface OrgNode {
  /** Identificador único (opcional, útil para keys). */
  id?: string;
  /** Nombre de la persona/unidad. */
  name: string;
  /** Rol o cargo (línea secundaria muted). */
  role?: string;
  /** URL de avatar del propio nodo (no usada en el stack de equipo). */
  avatar?: string;
  /** Tamaño del equipo que reporta a este nodo → genera el stack de avatares (+N). */
  team?: number;
  /** Hijos directos en la jerarquía. */
  children?: OrgNode[];
}

/** Nodo ya posicionado por el layout (coordenadas del "mundo", en px). */
interface PlacedNode {
  node: OrgNode;
  x: number;
  y: number;
  depth: number;
}

/** Resultado del layout: nodos posicionados, rutas de conectores y tamaño del lienzo. */
interface Layout {
  nodes: PlacedNode[];
  links: string[];
  width: number;
  height: number;
}

// Geometría fija del lienzo (en px del "mundo"; el zoom escala todo por igual).
const NODE_W = 184;
const NODE_H = 120;
const H_GAP = 28; // separación horizontal entre hojas hermanas
const V_GAP = 56; // separación vertical entre niveles
const LEAF_STEP = NODE_W + H_GAP;
const LEVEL_H = NODE_H + V_GAP;

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));
const MIN_K = 0.2;
const MAX_K = 2.5;

export class OkOrgChart extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #fff));
      --node-bg: var(--ok-card-background, var(--ion-card-background, #f7f8fa));
      --root-bg-top: var(--ok-surface-2, var(--ion-color-light, #eef0f4));
      --line: var(--ok-border-color, var(--ion-border-color, #d7dade));
      --line-2: var(--ok-border-color, var(--ion-border-color, #c9ccd2));
      --brand: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
      --brand-soft-line: var(--ok-color-primary-tint, var(--ion-color-primary-tint, #5a98ff));
      --name-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --role-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --avatar-bg: var(--ok-surface-3, var(--ion-color-light-shade, #d7dade));
      --avatar-fg: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --radius: var(--ok-radius-md, 10px);
      --dur: 160ms;
      --ease: cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* Viewport: recorta el lienzo y captura los gestos de pan/zoom. */
    .wrap {
      position: relative;
      width: 100%;
      overflow: hidden;
      background: var(--bg);
      border-radius: var(--radius);
      touch-action: none; /* gestionamos pan/zoom nosotros */
      cursor: grab;
      box-sizing: border-box;
    }
    .wrap.grabbing {
      cursor: grabbing;
    }

    /* Lienzo del "mundo": se mueve/escala con transform (origen 0,0). */
    .canvas {
      position: absolute;
      top: 0;
      left: 0;
      transform-origin: 0 0;
      will-change: transform;
    }

    /* Capa de conectores (SVG vectorial), bajo los nodos. */
    .links {
      position: absolute;
      top: 0;
      left: 0;
      overflow: visible;
      pointer-events: none;
    }
    .link {
      fill: none;
      stroke: var(--line-2);
      stroke-width: 1.25;
    }

    .node {
      position: absolute;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
      background: var(--node-bg);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 10px 14px;
      box-sizing: border-box;
      text-align: center;
      transition: border-color var(--dur) var(--ease), transform var(--dur) var(--ease),
        box-shadow var(--dur) var(--ease);
    }
    .node:hover {
      border-color: var(--brand);
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
      z-index: 1;
    }
    .node.root {
      background: linear-gradient(180deg, var(--root-bg-top), var(--node-bg));
      border-color: var(--brand-soft-line);
    }

    /* Avatar del propio nodo: imagen si la hay, si no las iniciales del nombre. */
    .node-avatar {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: var(--avatar-bg);
      color: var(--avatar-fg);
      font-size: 14px;
      font-weight: 700;
      letter-spacing: -0.02em;
      overflow: hidden;
      flex-shrink: 0;
      border: 1px solid var(--line);
      box-sizing: border-box;
    }
    .node.root .node-avatar {
      border-color: var(--brand-soft-line);
    }
    .node-avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    /* Botón recoger/expandir, anclado al borde inferior del nodo con hijos. */
    .toggle {
      position: absolute;
      bottom: -11px;
      left: 50%;
      transform: translateX(-50%);
      width: 22px;
      height: 22px;
      border-radius: 50%;
      border: 1px solid var(--line);
      background: var(--node-bg);
      color: var(--name-color);
      font-size: 11px;
      font-weight: 700;
      line-height: 1;
      display: grid;
      place-items: center;
      cursor: pointer;
      padding: 0;
      z-index: 2;
      transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease),
        color var(--dur) var(--ease);
    }
    .toggle:hover {
      border-color: var(--brand);
    }
    /* Colapsado: resaltado en color de marca y mostrando cuántos oculta. */
    .toggle.is-collapsed {
      background: var(--brand);
      color: #fff;
      border-color: var(--brand);
    }

    .name {
      font-size: 13px;
      font-weight: 600;
      color: var(--name-color);
      line-height: 1.2;
    }
    .role {
      font-size: 11px;
      color: var(--role-color);
      line-height: 1.2;
    }

    /* Stack de avatares solapados para el tamaño de equipo. */
    .team {
      display: inline-flex;
      align-items: center;
      margin-top: 4px;
    }
    .avatar {
      display: inline-grid;
      place-items: center;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--avatar-bg);
      color: var(--avatar-fg);
      font-size: 9px;
      font-weight: 600;
      letter-spacing: -0.02em;
      overflow: hidden;
      flex-shrink: 0;
      border: 1px solid var(--bg);
      box-sizing: border-box;
    }
    .avatar + .avatar {
      margin-left: -4px;
    }
    .avatar.more {
      background: var(--avatar-bg);
      color: var(--role-color);
    }
    .avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    /* Controles flotantes (zoom / ajustar). */
    .ctrls {
      position: absolute;
      top: 10px;
      right: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      z-index: 2;
    }
    .ctrls button {
      width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--node-bg);
      color: var(--name-color);
      font-size: 16px;
      line-height: 1;
      cursor: pointer;
      padding: 0;
      transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease);
    }
    .ctrls button:hover {
      border-color: var(--brand);
    }
    .empty {
      display: grid;
      place-items: center;
      width: 100%;
      height: 100%;
      color: var(--role-color);
      font-size: 13px;
    }
  `;

  /** Nodo raíz del organigrama (con `children` recursivos). */
  @property({ attribute: false }) root: OrgNode | null = null;

  /** Máximo de avatares mostrados en el stack antes del «+N» (resto). */
  @property({ type: Number }) maxAvatars = 3;

  /** Alto del viewport en px (el organigrama vive dentro y se navega con pan/zoom). */
  @property({ type: Number }) height = 460;

  // Estado de la cámara (transform del lienzo).
  @state() private tx = 0;
  @state() private ty = 0;
  @state() private k = 1;
  @state() private grabbing = false;

  // Ramas recogidas (por referencia de nodo). Mutar = reasignar para que Lit reaccione.
  @state() private collapsed = new Set<OrgNode>();

  // Tamaño del último layout (para "ajustar a pantalla").
  private contentW = 0;
  private contentH = 0;
  private fitted = false;

  // Gestos: punteros activos + estado de pan/pinch.
  private pointers = new Map<number, { x: number; y: number }>();
  private panStart: { x: number; y: number; tx: number; ty: number } | null = null;
  private pinchStart:
    | { dist: number; k: number; cx: number; cy: number; tx: number; ty: number }
    | null = null;
  private wrapEl: HTMLElement | null = null;
  private ro: ResizeObserver | null = null;
  // Auto-encuadre hasta que el usuario navegue manualmente (pan/zoom).
  private userMoved = false;

  // ---- Layout tidy-tree: x/y por nodo + rutas de conectores ----
  private layout(root: OrgNode): Layout {
    const nodes: PlacedNode[] = [];
    const placed = new Map<OrgNode, PlacedNode>();
    let cursor = 0;
    let maxDepth = 0;

    // Post-orden: las hojas avanzan un cursor; cada padre se centra sobre sus hijos.
    // Un nodo recogido se trata como hoja (sus hijos no se posicionan ni dibujan).
    const place = (n: OrgNode, depth: number): PlacedNode => {
      maxDepth = Math.max(maxDepth, depth);
      const kids = this.collapsed.has(n) ? [] : n.children ?? [];
      let x: number;
      if (!kids.length) {
        x = cursor * LEAF_STEP;
        cursor += 1;
      } else {
        const kp = kids.map((c) => place(c, depth + 1));
        x = (kp[0].x + kp[kp.length - 1].x) / 2;
      }
      const p: PlacedNode = { node: n, x, y: depth * LEVEL_H, depth };
      nodes.push(p);
      placed.set(n, p);
      return p;
    };
    place(root, 0);

    // Conectores: caída del padre → barra horizontal centro-a-centro → caída a cada hijo.
    const links: string[] = [];
    for (const p of nodes) {
      const kids = this.collapsed.has(p.node) ? [] : p.node.children ?? [];
      if (!kids.length) continue;
      const kp = kids.map((c) => placed.get(c)!);
      const parentCx = p.x + NODE_W / 2;
      const parentBottom = p.y + NODE_H;
      const busY = parentBottom + V_GAP / 2;
      links.push(`M${parentCx},${parentBottom}L${parentCx},${busY}`);
      const firstCx = kp[0].x + NODE_W / 2;
      const lastCx = kp[kp.length - 1].x + NODE_W / 2;
      if (kp.length > 1) links.push(`M${firstCx},${busY}L${lastCx},${busY}`);
      for (const c of kp) {
        const cx = c.x + NODE_W / 2;
        links.push(`M${cx},${busY}L${cx},${c.y}`);
      }
    }

    const maxX = nodes.reduce((m, p) => Math.max(m, p.x), 0);
    return { nodes, links, width: maxX + NODE_W, height: maxDepth * LEVEL_H + NODE_H };
  }

  /** Renderiza el stack de avatares (+N) para el tamaño de equipo de un nodo. */
  private renderTeam(node: OrgNode): unknown {
    const total = node.team ?? 0;
    if (total <= 0) return null;
    const shown = Math.min(this.maxAvatars, total);
    const rest = total - shown;
    const initials = (node.role ?? node.name)
      .replace(/[^A-Za-zÀ-ÿ ]/g, '')
      .split(/\s+/)
      .filter(Boolean);
    return html`
      <div class="team" aria-label="Equipo de ${total}">
        ${Array.from({ length: shown }, (_v, i) => {
          const seed = initials[i % Math.max(initials.length, 1)] ?? '';
          const label = seed ? seed.slice(0, 2).toUpperCase() : '·';
          return html`<span class="avatar" aria-hidden="true">${label}</span>`;
        })}
        ${rest > 0 ? html`<span class="avatar more" aria-hidden="true">+${rest}</span>` : null}
      </div>
    `;
  }

  /** Iniciales del nombre (1ª letra del primer y último término), para el avatar sin imagen. */
  private initialsOf(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '·';
    const first = parts[0][0] ?? '';
    const last = parts.length > 1 ? parts[parts.length - 1][0] ?? '' : '';
    return (first + last).toUpperCase();
  }

  /** Recoge/expande la rama de un nodo y emite `ok-node-toggle`. */
  private toggle(n: OrgNode): void {
    const next = new Set(this.collapsed);
    if (next.has(n)) next.delete(n);
    else next.add(n);
    this.collapsed = next;
    this.userMoved = true; // no reencuadrar al interactuar
    this.dispatchEvent(
      new CustomEvent('ok-node-toggle', {
        detail: { node: n, collapsed: next.has(n) },
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Renderiza un nodo posicionado (HTML absoluto en coordenadas del mundo). */
  private renderNode(p: PlacedNode): unknown {
    const n = p.node;
    const childCount = n.children?.length ?? 0;
    const isCollapsed = this.collapsed.has(n);
    return html`
      <div
        class="node ${p.depth === 0 ? 'root' : ''}"
        role="treeitem"
        aria-expanded=${childCount ? String(!isCollapsed) : nothing}
        style=${`left:${p.x}px;top:${p.y}px;width:${NODE_W}px;height:${NODE_H}px;`}
      >
        <span class="node-avatar">
          ${n.avatar
            ? html`<img src=${n.avatar} alt="" />`
            : html`<span aria-hidden="true">${this.initialsOf(n.name)}</span>`}
        </span>
        <span class="name">${n.name}</span>
        ${n.role ? html`<span class="role">${n.role}</span>` : null}
        ${this.renderTeam(n)}
        ${childCount
          ? html`<button
              type="button"
              class="toggle ${isCollapsed ? 'is-collapsed' : ''}"
              title=${isCollapsed ? `Expandir (${childCount})` : 'Recoger'}
              aria-label=${isCollapsed ? `Expandir ${childCount} subordinados` : 'Recoger rama'}
              @pointerdown=${(e: Event) => e.stopPropagation()}
              @click=${(e: Event) => {
                e.stopPropagation();
                this.toggle(n);
              }}
            >
              ${isCollapsed ? childCount : '−'}
            </button>`
          : null}
      </div>
    `;
  }

  // ---- Cámara: ajustar a pantalla y zoom ----
  /** Encuadra todo el organigrama en el viewport con un pequeño margen. */
  fit(): void {
    if (!this.wrapEl || !this.contentW || !this.contentH) return;
    const vw = this.wrapEl.clientWidth;
    const vh = this.wrapEl.clientHeight;
    const pad = 24;
    const k = clamp(
      Math.min((vw - pad * 2) / this.contentW, (vh - pad * 2) / this.contentH),
      MIN_K,
      1.2,
    );
    this.k = k;
    this.tx = (vw - this.contentW * k) / 2;
    this.ty = pad;
  }

  /** Recentra el organigrama en el viewport MANTENIENDO el zoom actual. */
  center(): void {
    if (!this.wrapEl || !this.contentW || !this.contentH) return;
    this.userMoved = true;
    const vw = this.wrapEl.clientWidth;
    const vh = this.wrapEl.clientHeight;
    this.tx = (vw - this.contentW * this.k) / 2;
    this.ty = Math.max(24, (vh - this.contentH * this.k) / 2);
  }

  // Zoom alrededor de un punto del viewport (mantiene ese punto fijo).
  private zoomAround(vx: number, vy: number, factor: number): void {
    const newK = clamp(this.k * factor, MIN_K, MAX_K);
    const wx = (vx - this.tx) / this.k;
    const wy = (vy - this.ty) / this.k;
    this.k = newK;
    this.tx = vx - wx * newK;
    this.ty = vy - wy * newK;
  }

  private zoomBy(factor: number): void {
    if (!this.wrapEl) return;
    this.userMoved = true;
    this.zoomAround(this.wrapEl.clientWidth / 2, this.wrapEl.clientHeight / 2, factor);
  }

  private onWheel = (e: WheelEvent): void => {
    e.preventDefault();
    this.userMoved = true;
    const rect = this.wrapEl!.getBoundingClientRect();
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    this.zoomAround(e.clientX - rect.left, e.clientY - rect.top, factor);
  };

  private onPointerDown = (e: PointerEvent): void => {
    this.userMoved = true;
    this.wrapEl!.setPointerCapture(e.pointerId);
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (this.pointers.size === 1) {
      this.panStart = { x: e.clientX, y: e.clientY, tx: this.tx, ty: this.ty };
      this.grabbing = true;
    } else if (this.pointers.size === 2) {
      this.panStart = null;
      const pts = [...this.pointers.values()];
      const rect = this.wrapEl!.getBoundingClientRect();
      this.pinchStart = {
        dist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1,
        k: this.k,
        cx: (pts[0].x + pts[1].x) / 2 - rect.left,
        cy: (pts[0].y + pts[1].y) / 2 - rect.top,
        tx: this.tx,
        ty: this.ty,
      };
    }
  };

  private onPointerMove = (e: PointerEvent): void => {
    if (!this.pointers.has(e.pointerId)) return;
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (this.pinchStart && this.pointers.size >= 2) {
      const pts = [...this.pointers.values()];
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1;
      const newK = clamp(this.pinchStart.k * (dist / this.pinchStart.dist), MIN_K, MAX_K);
      const wx = (this.pinchStart.cx - this.pinchStart.tx) / this.pinchStart.k;
      const wy = (this.pinchStart.cy - this.pinchStart.ty) / this.pinchStart.k;
      this.k = newK;
      this.tx = this.pinchStart.cx - wx * newK;
      this.ty = this.pinchStart.cy - wy * newK;
    } else if (this.panStart) {
      this.tx = this.panStart.tx + (e.clientX - this.panStart.x);
      this.ty = this.panStart.ty + (e.clientY - this.panStart.y);
    }
  };

  private onPointerUp = (e: PointerEvent): void => {
    this.pointers.delete(e.pointerId);
    if (this.pointers.size < 2) this.pinchStart = null;
    if (this.pointers.size === 0) {
      this.panStart = null;
      this.grabbing = false;
    } else {
      // Si queda un puntero, reanuda el pan desde su posición actual.
      const [, pos] = [...this.pointers.entries()][0];
      this.panStart = { x: pos.x, y: pos.y, tx: this.tx, ty: this.ty };
    }
  };

  protected firstUpdated(): void {
    this.wrapEl = this.renderRoot.querySelector('.wrap');
    this.fitted = true;
    // El viewport puede no tener tamaño aún (SPA/tab oculta): reencuadra cuando lo tenga,
    // mientras el usuario no haya navegado a mano.
    this.ro = new ResizeObserver(() => {
      if (!this.userMoved) this.fit();
    });
    if (this.wrapEl) this.ro.observe(this.wrapEl);
    this.fit();
  }

  protected updated(changed: Map<string, unknown>): void {
    // Al cambiar el árbol: limpia el estado de recogido y reactiva el auto-encuadre.
    if (changed.has('root')) {
      if (this.collapsed.size) this.collapsed = new Set();
      this.userMoved = false;
    }
    if ((changed.has('root') || changed.has('height')) && this.fitted) {
      this.fit();
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.ro?.disconnect();
    this.ro = null;
  }

  render(): unknown {
    if (!this.root) {
      return html`<div
        class="wrap"
        style=${`height:${this.height}px;`}
        role="tree"
        aria-label="Organigrama"
      >
        <div class="empty">Sin datos</div>
      </div>`;
    }

    const lay = this.layout(this.root);
    this.contentW = lay.width;
    this.contentH = lay.height;

    return html`
      <div
        class="wrap ${this.grabbing ? 'grabbing' : ''}"
        style=${`height:${this.height}px;`}
        role="tree"
        aria-label="Organigrama"
        @wheel=${this.onWheel}
        @pointerdown=${this.onPointerDown}
        @pointermove=${this.onPointerMove}
        @pointerup=${this.onPointerUp}
        @pointercancel=${this.onPointerUp}
      >
        <div
          class="canvas"
          style=${`transform: translate(${this.tx}px, ${this.ty}px) scale(${this.k});`}
        >
          <svg
            class="links"
            width=${lay.width}
            height=${lay.height}
            viewBox=${`0 0 ${lay.width} ${lay.height}`}
          >
            ${lay.links.map((d) => svg`<path class="link" d=${d}></path>`)}
          </svg>
          ${lay.nodes.map((p) => this.renderNode(p))}
        </div>

        <div class="ctrls">
          <button type="button" title="Acercar" aria-label="Acercar" @click=${() => this.zoomBy(1.2)}>
            +
          </button>
          <button
            type="button"
            title="Alejar"
            aria-label="Alejar"
            @click=${() => this.zoomBy(1 / 1.2)}
          >
            −
          </button>
          <button
            type="button"
            title="Centrar"
            aria-label="Centrar"
            @click=${() => this.center()}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <circle cx="12" cy="12" r="3.2" fill="currentColor" />
              <g stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <line x1="12" y1="3" x2="12" y2="7" />
                <line x1="12" y1="17" x2="12" y2="21" />
                <line x1="3" y1="12" x2="7" y2="12" />
                <line x1="17" y1="12" x2="21" y2="12" />
              </g>
            </svg>
          </button>
          <button
            type="button"
            title="Ajustar a pantalla"
            aria-label="Ajustar a pantalla"
            @click=${() => this.fit()}
          >
            ⤢
          </button>
        </div>
      </div>
    `;
  }
}

define('ok-org-chart', OkOrgChart);

declare global {
  interface HTMLElementTagNameMap {
    'ok-org-chart': OkOrgChart;
  }
}
