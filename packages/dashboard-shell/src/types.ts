// Contrato público del shell de dashboard. Todo lo específico del producto (Hub o Cloud)
// entra por estos tipos: nada de rutas, auth ni marca hardcodeadas en el paquete.
import type { ReactNode } from 'react';
import type { IconType } from 'react-icons';

/** Un ítem de navegación del menú lateral: ruta + etiqueta + icono. */
export interface NavItem {
  path: string;
  label: string;
  Icon: IconType;
}

/** Una sección del menú lateral (título + ítems). */
export interface NavSection {
  label: string;
  items: NavItem[];
}

/** Una acción de la cabecera (asistente, apps, apariencia, notificaciones…). */
export interface HeaderAction {
  /** Identificador estable (key de React). */
  id: string;
  label: string;
  Icon: IconType;
  onClick?: () => void;
  /** Si es `true`, siempre visible y NO colapsa en el menú overflow móvil. */
  pinned?: boolean;
}

/** Usuario activo mostrado en el footer del menú. El shell no sabe de auth. */
export interface ShellUser {
  id: string;
  name: string;
  email?: string | null;
  avatarUrl?: string | null;
}

/** Identidad + acciones de cuenta inyectadas por el consumidor. */
export interface ShellIdentity {
  user: ShellUser | null;
  onLogout: () => void;
  onOpenSettings: () => void;
}

/** Marca de la cabecera del menú. */
export interface ShellBranding {
  /** Logo (p. ej. `<Logo/>`). */
  logo: ReactNode;
  /** Slot opcional bajo el logo (p. ej. un segmento Hub/Cloud). */
  switcher?: ReactNode;
}
