// Entry del bundle único de CDN (`@erplora/outfitkit/cdn` → dist/outfitkit.js). Importar este
// fichero auto-registra TODOS los componentes ok-* que OutfitKit aporta. Pensado para cargarlo de
// una vez en una página (Django/landing/showcase) con un solo <script type="module">.
// `lit` queda external → en CDN sirve un import-map que apunte "lit" a su CDN.
//
// OutfitKit EXTIENDE Ionic: los primitivos (botón, icono, input…) son `ion-*` nativos, los registra
// el host; aquí solo van los huecos que OutfitKit cubre.

// Compuestos / dashboard
import './components/ok-data-table/ok-data-table.js';
// App launcher
import './components/ok-app-launcher/ok-app-launcher.js';
// Dashboard / métricas (pantalla /system)
import './components/ok-gauge/ok-gauge.js';
import './components/ok-kpi/ok-kpi.js';
import './components/ok-stat/ok-stat.js';
import './components/ok-sparkline/ok-sparkline.js';
import './components/ok-status-pill/ok-status-pill.js';
import './components/ok-empty-state/ok-empty-state.js';
// Landing chrome
import './components/ok-navbar/ok-navbar.js';
import './components/ok-footer/ok-footer.js';
import './components/ok-container/ok-container.js';
import './components/ok-container-full/ok-container-full.js';
import './components/ok-hero/ok-hero.js';
