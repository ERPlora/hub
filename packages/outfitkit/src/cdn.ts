// Entry para el bundle único de CDN (`@erplora/outfitkit/cdn` → dist/outfitkit.js).
// Importar este fichero auto-registra todos los componentes ok-*. Pensado para cargarlo
// de una vez en una página (Django/landing) con un solo <script type="module">.
// `lit` queda external → en CDN sirve un import-map que apunte "lit" a su CDN.
import './components/ok-data-table/ok-data-table.js';
import './components/ok-navbar/ok-navbar.js';
import './components/ok-footer/ok-footer.js';
import './components/ok-container/ok-container.js';
import './components/ok-container-full/ok-container-full.js';
import './components/ok-hero/ok-hero.js';
