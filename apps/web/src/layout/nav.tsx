// Navegación del Hub. Cada ítem mapea a una ruta + un icono de react-icons.
// El tipo NavSection lo define el shell compartido (@erplora/dashboard-shell); aquí sólo
// están los DATOS específicos del Hub, que se inyectan en <DashboardShell menu={NAV}>.
import {
  LuLayoutDashboard, LuUsers, LuFileText, LuStore, LuCpu, LuSettings,
} from 'react-icons/lu';
import type { NavSection } from '@erplora/dashboard-shell';

export const NAV: NavSection[] = [
  {
    label: 'Operación',
    items: [
      { path: '/', label: 'Dashboard', Icon: LuLayoutDashboard },
      // Roles ya no es entrada propia: vive como pestaña dentro de Empleados (último tab).
      { path: '/employees', label: 'Empleados', Icon: LuUsers },
      { path: '/billing', label: 'Billing', Icon: LuFileText },
      // "Mis módulos" ya no es entrada propia: es el primer tab dentro de Marketplace.
      { path: '/marketplace', label: 'Marketplace', Icon: LuStore },
    ],
  },
  {
    label: 'Sistema',
    items: [
      { path: '/system', label: 'Sistema', Icon: LuCpu },
      { path: '/settings', label: 'Ajustes', Icon: LuSettings },
    ],
  },
];
