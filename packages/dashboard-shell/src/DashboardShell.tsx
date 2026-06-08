// Chrome del dashboard: IonSplitPane (menú lateral desktop / drawer móvil) + IonRouterOutlet
// con las rutas que inyecta el consumidor como children. Sin lógica de producto: menú, marca,
// identidad y acciones de cabecera entran por props (reutilizable por Hub y Cloud).
import type { ReactNode } from 'react';
import { IonSplitPane, IonRouterOutlet } from '@ionic/react';
import { SideMenu } from './SideMenu';
import { ShellChromeContext } from './context';
import type { HeaderAction, NavSection, ShellBranding, ShellIdentity } from './types';

export interface DashboardShellProps {
  /** Secciones del menú lateral (datos inyectados por el consumidor). */
  menu: NavSection[];
  /** Marca: logo + slot opcional bajo el logo. */
  branding: ShellBranding;
  /** Identidad del usuario activo + acciones de cuenta. */
  identity: ShellIdentity;
  /** Acciones de la cabecera (asistente, apps, apariencia, notificaciones…). */
  headerActions?: HeaderAction[];
  /** Contenido enrutado: los <Route> del consumidor, envueltos en IonRouterOutlet. */
  children: ReactNode;
}

export function DashboardShell({
  menu,
  branding,
  identity,
  headerActions = [],
  children,
}: DashboardShellProps) {
  return (
    <ShellChromeContext.Provider value={{ headerActions }}>
      <IonSplitPane contentId="main" when="lg">
        <SideMenu menu={menu} branding={branding} identity={identity} />
        <IonRouterOutlet id="main">{children}</IonRouterOutlet>
      </IonSplitPane>
    </ShellChromeContext.Provider>
  );
}
