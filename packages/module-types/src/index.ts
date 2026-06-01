// @erplora/module-types — contrato compartido (tipos TS).
// OBJETIVO: generar estos tipos desde ../../schemas/module.schema.json (fuente única).
// HOY: mínimos a mano para que el SDK/CLI tipen. ARQUITECTURA.md §7.2.

export interface NavigationItem {
  id: string;
  label: string;
  icon?: string;
  component: string; // custom element a montar
}

export interface ModuleManifest {
  id: string;
  name: string;
  version: string;
  depends_on?: string[];
  permissions?: string[];
  role_permissions?: Record<string, string[]>;
  navigation?: NavigationItem[];
  ui: { entry: string };
  // queries/commands/events/ai_tools/network/scheduled_tasks → ver schemas/module.schema.json
}

// Envelope de transporte (schemas/envelope.schema.json) — §7.6
export interface WireRequest { id: string; kind: 'query' | 'command'; name: string; params?: unknown; }
export interface WireResponse { id: string; ok: boolean; data?: unknown; error?: { code: string; message: string }; }
export interface WireEvent { name: string; payload?: unknown; }
