// The public website of a hub (apps/website): served under `script-src 'self'`, without a nonce, from the build's
// manifest (`{% hub_assets "frontend/website.ts" %}`). Bootstrap 5.3 styles every template and its collapse folds the
// top bar's menu on a phone (by its data attributes: the page has no inline script); site.css maps the palette onto
// Bootstrap's variables and holds the templates' type. A page in «Auto» follows the device's light or dark, and the
// catalog is refreshed live; both come from apps/website.
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/js/src/collapse.js';
import '../apps/website/frontend/public/site.css';

import { hydrateCatalog } from '../apps/website/frontend/public/catalog';
import { followColourMode } from '../apps/website/frontend/public/mode';

// A module script runs once the document is parsed: the catalog's block is already there.
followColourMode();
void hydrateCatalog();
