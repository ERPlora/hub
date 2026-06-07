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

// OutfitKit: registra los Web Components (Lit) que EXTIENDEN Ionic — hoy `ok-data-table`, usado por
// los listados de los módulos. Import por efecto secundario (se auto-registra con `define`, idempotente).
// Los módulos Lit también lo traen en su bundle auto-contenido; aquí lo dejamos disponible a nivel de
// shell. Ver MIGRACION-OUTFITKIT/02.
import '@erplora/outfitkit/ok-data-table';

// Chrome del dashboard compartido (menú lateral, cabecera, avatar). Antes que styles.css
// para que las personalizaciones de la app puedan ganar en empates de especificidad.
import '@erplora/dashboard-shell/styles.css';

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
