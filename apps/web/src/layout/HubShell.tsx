// Shell del Hub: compone el dashboard compartido (@erplora/dashboard-shell) con lo
// específico del Hub — rutas/páginas, menú (NAV), marca (Logo + segmento Hub/Cloud),
// identidad (useAuth) y las acciones de cabecera (asistente, apps, apariencia, notif).
import { useState } from 'react';
import { Route, useHistory } from 'react-router-dom';
import { IonSegment, IonSegmentButton, IonLabel } from '@ionic/react';
import { LuBell, LuGrid2X2, LuSparkles, LuSun, LuMoon } from 'react-icons/lu';
import { DashboardShell, type HeaderAction, type ShellIdentity } from '@erplora/dashboard-shell';
import { AssistantProvider, useAssistant } from '../lib/assistant';
import { AppSwitcherProvider, useAppSwitcher } from '../lib/appswitcher';
import { useAuth } from '../lib/auth';
import { useTheme } from '../lib/theme';
import { Logo } from '../ui/Logo';
import { ThemeModal } from '../components/ThemeModal';
import { NAV } from './nav';
import { DashboardPage } from '../pages/DashboardPage';
import { EmployeesPage } from '../pages/EmployeesPage';
import { EmployeeFormPage } from '../pages/EmployeeFormPage';
import { BillingPage } from '../pages/BillingPage';
import { MarketplacePage } from '../pages/MarketplacePage';
import { SettingsPage } from '../pages/SettingsPage';
import { SystemPage } from '../pages/SystemPage';
import { ModuleView } from '../pages/ModuleView';

// Segmento Hub/Cloud que va bajo el logo en la cabecera del menú (marca del Hub).
function HubBrandSwitcher() {
  return (
    <IonSegment mode="ios" value="hub">
      <IonSegmentButton value="hub">
        <IonLabel>Hub</IonLabel>
      </IonSegmentButton>
      <IonSegmentButton value="cloud">
        <IonLabel>Cloud</IonLabel>
      </IonSegmentButton>
    </IonSegment>
  );
}

function HubShellInner() {
  const { user, logout } = useAuth();
  const { open: openAssistant } = useAssistant();
  const { open: openApps } = useAppSwitcher();
  const { dark } = useTheme();
  const history = useHistory();
  const [themeOpen, setThemeOpen] = useState(false);

  const headerActions: HeaderAction[] = [
    // Notificaciones: única acción time-sensitive → siempre visible.
    { id: 'notifications', label: 'Notificaciones', Icon: LuBell, pinned: true },
    { id: 'apps', label: 'Apps', Icon: LuGrid2X2, onClick: openApps },
    { id: 'theme', label: 'Apariencia', Icon: dark ? LuSun : LuMoon, onClick: () => setThemeOpen(true) },
    { id: 'assistant', label: 'Asistente', Icon: LuSparkles, onClick: openAssistant },
  ];

  const identity: ShellIdentity = {
    user: user
      ? { id: user.id, name: user.name, email: user.email, avatarUrl: user.avatarUrl }
      : null,
    onLogout: logout,
    onOpenSettings: () => history.push('/settings'),
  };

  return (
    <>
      <DashboardShell
        menu={NAV}
        branding={{ logo: <Logo size="sm" />, switcher: <HubBrandSwitcher /> }}
        identity={identity}
        headerActions={headerActions}
      >
        <Route exact path="/" component={DashboardPage} />
        <Route exact path="/employees" component={EmployeesPage} />
        <Route exact path="/employees/new" component={EmployeeFormPage} />
        <Route exact path="/employees/:id" component={EmployeeFormPage} />
        <Route exact path="/billing" component={BillingPage} />
        <Route exact path="/marketplace" component={MarketplacePage} />
        <Route exact path="/system" component={SystemPage} />
        <Route exact path="/settings" component={SettingsPage} />
        <Route exact path="/m/:moduleId" component={ModuleView} />
      </DashboardShell>
      <ThemeModal isOpen={themeOpen} onClose={() => setThemeOpen(false)} />
    </>
  );
}

export function HubShell() {
  return (
    <AssistantProvider>
      <AppSwitcherProvider>
        <HubShellInner />
      </AppSwitcherProvider>
    </AssistantProvider>
  );
}
