import React from 'react';
import { createRoot } from 'react-dom/client';
import { setupIonicReact } from '@ionic/react';

// CSS base de Ionic (core + utilidades). Orden: primero core de Ionic, luego Tailwind y
// el tema de marca (--ion-*). El dark mode por clase llega de palettes/dark.class.css.
import '@ionic/react/css/core.css';
import '@ionic/react/css/normalize.css';
import '@ionic/react/css/structure.css';
import '@ionic/react/css/typography.css';
import '@ionic/react/css/padding.css';
import '@ionic/react/css/flex-utils.css';
import '@ionic/react/css/palettes/dark.class.css';

import './styles.css';
import './theme/ionic-theme.css';

import { AuthProvider } from './lib/auth';
import { ThemeProvider } from './lib/theme';
import { App } from './App';

setupIonicReact({ mode: 'md' });

const root = document.getElementById('root');
if (!root) throw new Error('#root no encontrado');

createRoot(root).render(
  <React.StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
