// Shell autenticado con Ionic real: IonSplitPane (menú lateral desktop / drawer móvil) +
// IonRouterOutlet con las páginas.
import { IonSplitPane, IonRouterOutlet } from '@ionic/react';
import { Route } from 'react-router-dom';
import { AssistantProvider } from '../lib/assistant';
import { AppSwitcherProvider } from '../lib/appswitcher';
import { SideMenu } from './SideMenu';
import { DashboardPage } from '../pages/DashboardPage';
import { EmployeesPage } from '../pages/EmployeesPage';
import { EmployeeFormPage } from '../pages/EmployeeFormPage';
import { BillingPage } from '../pages/BillingPage';
import { MarketplacePage } from '../pages/MarketplacePage';
import { SettingsPage } from '../pages/SettingsPage';
import { SystemPage } from '../pages/SystemPage';
import { ModuleView } from '../pages/ModuleView';

export function HubShell() {
  return (
    <AssistantProvider>
    <AppSwitcherProvider>
    <IonSplitPane contentId="main" when="lg">
      <SideMenu />
      <IonRouterOutlet id="main">
        <Route exact path="/" component={DashboardPage} />
        <Route exact path="/employees" component={EmployeesPage} />
        <Route exact path="/employees/new" component={EmployeeFormPage} />
        <Route exact path="/employees/:id" component={EmployeeFormPage} />
        <Route exact path="/billing" component={BillingPage} />
        <Route exact path="/marketplace" component={MarketplacePage} />
        <Route exact path="/system" component={SystemPage} />
        <Route exact path="/settings" component={SettingsPage} />
        <Route exact path="/m/:moduleId" component={ModuleView} />
      </IonRouterOutlet>
    </IonSplitPane>
    </AppSwitcherProvider>
    </AssistantProvider>
  );
}
