// API pública del shell de dashboard compartido (@erplora/dashboard-shell).
//
//   <DashboardShell menu={…} branding={…} identity={…} headerActions={…}>
//     {/* <Route> de la app */}
//   </DashboardShell>
//
// Las páginas usan <PageScaffold> (IonPage + cabecera + contenido); la cabecera lee las
// acciones inyectadas en <DashboardShell>. El paquete NO trae auth, asistente, marca ni
// rutas: todo se inyecta. CSS de la chrome: importar '@erplora/dashboard-shell/styles.css'.
export { DashboardShell, type DashboardShellProps } from './DashboardShell';
export { PageScaffold } from './PageScaffold';
export { PageHeader } from './PageHeader';
export { Avatar } from './Avatar';
export {
  getLocalAvatar,
  setLocalAvatar,
  fileToAvatarDataUrl,
  useLocalAvatar,
} from './localAvatar';
export type {
  NavItem,
  NavSection,
  HeaderAction,
  ShellUser,
  ShellIdentity,
  ShellBranding,
} from './types';
