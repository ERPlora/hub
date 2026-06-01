import { IonApp } from '@ionic/react';
import { IonReactRouter } from '@ionic/react-router';
import { Redirect, Route, Switch } from 'react-router-dom';
import { useAuth } from './lib/auth';
import { LoginPage } from './pages/auth/LoginPage';
import { HubShell } from './layout/HubShell';

export function App() {
  const { ready, user } = useAuth();

  // Evita parpadeo hasta restaurar la sesión de localStorage.
  if (!ready) return <IonApp />;

  return (
    <IonApp>
      <IonReactRouter>
        <Switch>
          <Route exact path="/login">
            {user ? <Redirect to="/" /> : <LoginPage />}
          </Route>
          <Route path="/">
            {user ? <HubShell /> : <Redirect to="/login" />}
          </Route>
        </Switch>
      </IonReactRouter>
    </IonApp>
  );
}
