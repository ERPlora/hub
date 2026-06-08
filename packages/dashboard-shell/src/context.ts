// Distribución interna de la chrome a los <PageHeader> que renderiza cada página.
// Es un detalle de implementación del shell (NO un contexto de auth): el consumidor
// inyecta las acciones una sola vez en <DashboardShell> y aquí las repartimos a las
// cabeceras de las páginas (que viven dentro del IonRouterOutlet).
import { createContext, useContext } from 'react';
import type { HeaderAction } from './types';

export interface ShellChrome {
  headerActions: HeaderAction[];
}

export const ShellChromeContext = createContext<ShellChrome>({ headerActions: [] });

export function useShellChrome(): ShellChrome {
  return useContext(ShellChromeContext);
}
