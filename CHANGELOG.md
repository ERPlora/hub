# CHANGELOG


## v0.14.0-rc.1 (2025-11-30)

### Bug Fixes

* fix: conditionally import debug_toolbar only when in INSTALLED_APPS

Prevents RuntimeError when DEBUG=True but debug_toolbar is not installed
(e.g., in CI environments using desktop_linux settings) ([`de8e178`](https://github.com/ERPlora/hub/commit/de8e1781d13b50a5ab66f0302d6d8eee532609da))

* fix: exempt /ht/ health check endpoint from SSO middleware ([`c58211e`](https://github.com/ERPlora/hub/commit/c58211e1d26b308c6364a27bf9944dd5641baf82))

* fix: correct ionicons static path

Change from ionicons/dist/ionicons/ionicons.esm.js to ionicons/dist/esm/ionicons.js
to match actual file structure in static folder. ([`a2ca7ba`](https://github.com/ERPlora/hub/commit/a2ca7baad41f7c32c028dfb025f5556e76ad2db2))

* fix: prevent dark theme flash on page refresh

Apply dark class server-side using Django template tag to prevent
flash of light theme while Alpine.js initializes. ([`989aa12`](https://github.com/ERPlora/hub/commit/989aa125f2c2c6fef3bc2d3faf85f62db5d6e499))

* fix: add WhiteNoise for static files in web/Docker deployment

Added whitenoise middleware to serve static files in production.
Without WhiteNoise, Gunicorn doesn't serve static files and returns 404
for JS/CSS assets.

- Added whitenoise to dependencies
- Added WhiteNoiseMiddleware to web settings
- Configured CompressedManifestStaticFilesStorage for caching ([`2265779`](https://github.com/ERPlora/hub/commit/22657799d9ee5783e2247462e3b8f80333d5eb46))

* fix: remove duplicate auth routes from core/urls.py

The setup-pin, verify-pin, cloud-login, logout and login routes were
duplicated in both apps/core/urls.py and apps/accounts/urls.py.

The core version of setup_pin had @require_http_methods(['POST']) which
caused 405 errors when the SSO middleware redirected users there via GET.

Removed duplicate routes from core/urls.py - accounts/urls.py now handles
all authentication routes correctly (supports both GET and POST for setup-pin). ([`9f074af`](https://github.com/ERPlora/hub/commit/9f074af307ac191cd5c81061033c9329366a5419))

* fix(sso): resolve session cookie conflict with Cloud

Problem: Hub and Cloud both used 'sessionid' cookie name, causing
Django's SessionMiddleware in Hub to invalidate Cloud's session
(different SECRET_KEY). Every link click redirected back to login.

Solution:
- Hub now uses 'hubsessionid' for its own session (SESSION_COOKIE_NAME)
- SSO middleware reads Cloud's 'sessionid' only for verification
- Hub session scoped to subdomain only (no cookie domain sharing)

Additional changes:
- LocalUser.cloud_user_id now nullable (DEMO_MODE support)
- Middleware passes full user_data dict (email, user_id, name)
- Added 26 unit tests for SSO middleware
- Added e2e tests for complete SSO flow

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`462cb56`](https://github.com/ERPlora/hub/commit/462cb56d3621da2eb6efd263191b2afde561543b))

* fix(sso): resolve session cookie conflict with Cloud

Problem: Hub and Cloud both used 'sessionid' cookie name, causing
Django's SessionMiddleware in Hub to invalidate Cloud's session
(different SECRET_KEY). Every link click redirected back to login.

Solution:
- Hub now uses 'hubsessionid' for its own session (SESSION_COOKIE_NAME)
- SSO middleware reads Cloud's 'sessionid' only for verification
- Hub session scoped to subdomain only (no cookie domain sharing)

Additional changes:
- LocalUser.cloud_user_id now nullable (DEMO_MODE support)
- Middleware passes full user_data dict (email, user_id, name)
- Added 26 unit tests for SSO middleware
- Added e2e tests for complete SSO flow ([`6db1ac5`](https://github.com/ERPlora/hub/commit/6db1ac53351c8d3c07375ef8fb83b5f0702219d2))

* fix(sso): add authentication URLs to SSO exempt list

Add login, cloud-login, setup-pin, verify-pin, and logout URLs to the
EXEMPT_URLS list in CloudSSOMiddleware so these endpoints work without
requiring SSO verification first. ([`92442db`](https://github.com/ERPlora/hub/commit/92442dbe1bda6f74d0d0cd76c18c23ba05efa67c))

* fix: use two_factor login URL directly (/account/login/)

- Change from /accounts/login/ to /account/login/
- Avoids extra redirect since two_factor uses /account/ not /accounts/ ([`5791c6e`](https://github.com/ERPlora/hub/commit/5791c6eaa78441f5fc88524c6c609f4355da6f75))

* fix: correct SSO login redirect URL and force HTTPS

- Change login path from /login/ to /accounts/login/ (allauth)
- Force HTTPS in next parameter when in web deployment mode ([`2c906f0`](https://github.com/ERPlora/hub/commit/2c906f03e1374e813bd58b5ba43064886e87ea3b))

* fix: move PLUGIN_DATA_ROOT outside PLUGINS_DIR

- Fix web.py, desktop_linux.py, desktop_macos.py, desktop_windows.py
- Changed from PLUGINS_DIR/data to DATA_DIR/plugin_data
- This prevents 'data' folder from being detected as a plugin
- Added plugin data storage documentation to plugins/README.md ([`858efc3`](https://github.com/ERPlora/hub/commit/858efc312d18c2b49d40f59f33c2002bf59bc5d3))

* fix: add INT and PRE environment subdomains to ALLOWED_HOSTS

- Add *.int.erplora.com for INT environment (demo.int.erplora.com)
- Add *.pre.erplora.com for PRE environment
- Update CSRF_TRUSTED_ORIGINS accordingly ([`cb96c2d`](https://github.com/ERPlora/hub/commit/cb96c2d22f6bc13c16a238970022d7e9a716498c))

* fix: include docs/README.md in Docker build

pyproject.toml references docs/README.md for package metadata.
The file was being excluded by .dockerignore causing build failure. ([`2c2aacc`](https://github.com/ERPlora/hub/commit/2c2aacc2eb1843ad74f12c9d47ab2c3240c6f9ac))

* fix: remove editable install from Dockerfile

uv pip install -e . requires source code but COPY . . was after the install step.
Changed to regular install without -e flag for production builds. ([`b9bf0a3`](https://github.com/ERPlora/hub/commit/b9bf0a3a7e45b70bcb26def5c096e7898e6f38c7))

* fix: remove editable install from Dockerfile

uv pip install -e . requires source code but COPY . . was after the install step.
Changed to regular install without -e flag for production builds.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`d4c2c1e`](https://github.com/ERPlora/hub/commit/d4c2c1ee0a7961fbf71fe1f7e602bf95eebe9322))

* fix: .env local para web ([`d3d9be3`](https://github.com/ERPlora/hub/commit/d3d9be34cb6fd56ecd79ba0e5276121b5f43e28f))

* fix: plugin loader ([`1d35882`](https://github.com/ERPlora/hub/commit/1d35882565d6b5f415a39ce035afa75e60cd9c36))

* fix: correct model imports in apps/core/views.py

Models were refactored to separate apps:
- HubConfig, StoreConfig → apps.configuration.models
- LocalUser → apps.accounts.models
- TokenCache → apps.sync.models ([`9804793`](https://github.com/ERPlora/hub/commit/9804793c9d43acb68bc6de85ba20b124d818f9d4))

* fix: move CloudSSOMiddleware to middleware package and add core urls ([`82e74a1`](https://github.com/ERPlora/hub/commit/82e74a10bea2c9b2261e712e5d3cecf15832dd07))

### Features

* feat: add Django Debug Toolbar for local development

- Add debug_toolbar to INSTALLED_APPS and MIDDLEWARE in local.py
- Configure INTERNAL_IPS and DEBUG_TOOLBAR_CONFIG
- Add debug toolbar URL patterns in urls.py
- Add django-debug-toolbar dependency ([`a902d3e`](https://github.com/ERPlora/hub/commit/a902d3e2936cda7f35aa900b390691f8c08ba52e))

* feat: add Cloud sync service with JWT authentication

Implement Hub-side of "Arquitectura Unificada Opción A":

- Add CloudAPIService for Hub-to-Cloud communication
- Add HeartbeatService with background threads:
  - Heartbeat every 60s (configurable)
  - Command polling every 5min (configurable)
- Add hub_jwt and cloud_public_key fields to HubConfig
- Initialize JWT from environment on startup (web mode)
- Add command handlers for plugin management
- Add unit and e2e tests ([`7d8f18a`](https://github.com/ERPlora/hub/commit/7d8f18ac882e6f3ef6b62cf544cfaae3bffa2919))

* feat: add django-health-check for Hub monitoring

- Add django-health-check>=3.18.0 to dependencies
- Configure health_check apps (db, cache, storage) in INSTALLED_APPS
- Add /ht/ endpoint for Cloud to verify Hub online status
- Enables real-time status checking from Cloud dashboard

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`8859a57`](https://github.com/ERPlora/hub/commit/8859a5777ca4564db6d234da891e709d64714cfc))

* feat(sso): add PARENT_DOMAIN config for cookies and CORS

- Configure SESSION_COOKIE_DOMAIN based on PARENT_DOMAIN env var
- Add CORS headers middleware and configuration
- Use SameSite=None for cross-subdomain SSO
- Support CORS_BASE_DOMAINS for multiple domain families ([`4573436`](https://github.com/ERPlora/hub/commit/4573436cc11889acb485a16d49742d16c14b7f01))

* feat(sso): complete SSO flow with LocalUser creation and PIN setup

- SSO middleware now creates LocalUser when user authenticates via Cloud
- If user has no PIN, redirects to /setup-pin/ to configure
- setup_pin view now supports GET for showing PIN setup form
- login.html template accepts show_pin_setup and pending_user from backend
- Session is established after PIN is configured
- Reactivates inactive users and resets their PIN ([`d067ad9`](https://github.com/ERPlora/hub/commit/d067ad92a0cb3dec205ff89878494da051ce4c88))

* feat: improve CloudSSOMiddleware for demo mode

- Use settings instead of decouple for configuration
- Add DEMO_MODE support: any authenticated user can access demo Hubs
- Deny access on network errors (instead of allowing fallback)
- Check 'authenticated' field in Cloud API response
- Add favicon.ico to exempt URLs ([`2ee1a5c`](https://github.com/ERPlora/hub/commit/2ee1a5c47c98796be9c2ac45613080e1d74dc06d))

* feat: make ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS configurable via env

- ALLOWED_HOSTS can be set as comma-separated list in environment
- CSRF_TRUSTED_ORIGINS can be set as comma-separated list in environment
- Falls back to sensible defaults if not set ([`e0be07d`](https://github.com/ERPlora/hub/commit/e0be07db84cfacf019e7a57aa5fd4168129e24d1))

* feat: add DEMO_MODE for non-persistent demo deployments

- Add DEMO_MODE env variable to web.py settings
- When DEMO_MODE=true, data stored in /app/data/ (inside container)
- No external volume needed, avoids permission issues
- Data is non-persistent (lost on container restart)
- Create /app/data directory in Dockerfile with proper permissions
- Update Dockerfile header documentation ([`0d53f87`](https://github.com/ERPlora/hub/commit/0d53f877b62a6d4333b4e31023bebeb47cbc29dc))

* feat: add local.py settings for development environment

- Create config/settings/local.py with development-specific config
- Load plugins from project directory (./plugins/) in local mode
- Use OS-specific DATA_DIR for database and logs
- Restore Plugin model to apps/core/models.py (was missing after refactor)
- Fix Plugin imports in apps/core/views.py
- Update settings/__init__.py to default to 'local' when HUB_ENV is not set
- Update .env.example with all available environments documentation ([`730db27`](https://github.com/ERPlora/hub/commit/730db27d8ff6ccf685a65050cafbf3e819346657))

* feat: individual settings per environment ([`6be3762`](https://github.com/ERPlora/hub/commit/6be3762fdda16afdb49efdb04b115734c4b6763d))

### Unknown

* chore: update documentation ([`0a0519e`](https://github.com/ERPlora/hub/commit/0a0519e4f44f403459845808d9fe13eb03af6aa3))

* merge: resolve conflicts from develop

- Keep skip decorator on TestCloudSSOMiddlewareWebMode
- Remove duplicate test_sso_flow_e2e.py (e2e tests are in tests/e2e/) ([`15aa9bf`](https://github.com/ERPlora/hub/commit/15aa9bfe4e5b382eca69622a3eded881007f5b7a))

* test(e2e): add end-to-end tests for Cloud SSO flow

- Add login/session flow tests (force_login for 2FA bypass)
- Add session verification endpoint tests
- Add hub creation and user registration tests
- Add protected routes access tests
- Add CORS and cross-origin SSO tests
- Add user profile flow tests

Note: Logout tests skipped due to allauth form requirements ([`fc87c07`](https://github.com/ERPlora/hub/commit/fc87c07c109e6708e72d2d40245c0de784c39dc5))

* test: add comprehensive unit tests for Hub accounts and configuration

- Add LocalUser model tests (26 tests)
  - PIN hashing and verification
  - User creation and management
  - Role colors and initials
  - Django compatibility methods

- Add accounts views tests (13 tests)
  - Login, verify-pin, setup-pin, logout
  - Employee CRUD API endpoints

- Add HubConfig and StoreConfig tests (10 tests)
  - Singleton pattern validation
  - Default values and caching
  - get/set value methods

- Update CloudSSOMiddleware tests
  - Skip session-dependent tests (require additional setup)
  - Add tests for Cloud API verification
  - Add tests for local user creation flow

- Remove outdated test files (test_models.py, test_paths.py, test_sso_flow_e2e.py) ([`2817fdf`](https://github.com/ERPlora/hub/commit/2817fdf2b0d9019a41be4052069c9aa656cf9070))

* chore: update uv.lock with django-cors-headers ([`fabe5a3`](https://github.com/ERPlora/hub/commit/fabe5a3de7ead82fe9e58d3b64d3983347df6639))

* chore: limit push to branch ([`bb44296`](https://github.com/ERPlora/hub/commit/bb44296706ce1d35b403c093b1c298f382d9f45e))


## v0.13.1 (2025-11-28)

### Bug Fixes

* fix: use DATA_PATHS.plugins_dir instead of DATA_PATHS / plugins ([`8ba72c3`](https://github.com/ERPlora/hub/commit/8ba72c3e3faf4c56f68f29a925a840265507a744))

### Unknown

* chore: merge CODEOWNERS update from main ([`871c402`](https://github.com/ERPlora/hub/commit/871c402b796621cf19215c295aee9fb29b553240))

* chore: merge CODEOWNERS update from main ([`c09dc86`](https://github.com/ERPlora/hub/commit/c09dc864f7a235e718de78f0cf4d75832c760104))

* chore: add 1oan-Beilic as code owner ([`98f4878`](https://github.com/ERPlora/hub/commit/98f48784212fa68787f72769bc5903bf51bcbe5e))

* chore: add CODEOWNERS file for PR approvals ([`7afab1d`](https://github.com/ERPlora/hub/commit/7afab1dc45e09a76466c4b940b3219dabe28565f))


## v0.12.1 (2025-11-28)

### Bug Fixes

* fix: update Dockerfile for production deployment ([`8eaf264`](https://github.com/ERPlora/hub/commit/8eaf2644297f2bd4471f28dad12dc5cacf62b741))

* fix: build ([`617aaf2`](https://github.com/ERPlora/hub/commit/617aaf2bd9f8540234bf5bfb576b01aa18359ba8))

* fix: frp client ([`1f6a7fc`](https://github.com/ERPlora/hub/commit/1f6a7fc85a10e70b2acc5e80d0db6ba024fddc8f))

* fix: update system ([`b0392d5`](https://github.com/ERPlora/hub/commit/b0392d5cfc84fb30b2a84b9408145762710e85d7))

* fix: add raw string to base_dir docstring to prevent unicode escape error ([`b8ef380`](https://github.com/ERPlora/hub/commit/b8ef380fd6dfe8f14f493a863469107664b9f227))

* fix: unicode escape error in paths.py docstring

Use raw string (r""") to prevent Python from interpreting backslashes
as escape sequences in Windows path examples. ([`9c12b74`](https://github.com/ERPlora/hub/commit/9c12b745b2ffe88d9e11fbf7c4271008073a3766))

* fix: update plugin loader for external directory with dynamic PYTHONPATH

Plugins are Django apps that now live in external data directory.
This update ensures they can be loaded dynamically:

Changes:
- Plugin directory uses settings.PLUGINS_DIR (external location)
- Automatically adds plugins/ to sys.path for imports
- Plugins persist across app updates/reinstalls
- Enhanced logging for plugin loading process
- Updated documentation with plugin loading details

How it works:
1. Plugins stored in external dir (e.g., ~/Library/Application Support/CPOSHub/plugins/)
2. PluginLoader adds this dir to PYTHONPATH on init
3. Django can import plugins as regular Python modules
4. Plugins added to INSTALLED_APPS dynamically
5. Migrations run automatically

Benefits:
- Plugins survive app updates
- No need to reinstall plugins on update
- Plugin data persists (config, media, cache)
- Follows Django app conventions ([`40b97e1`](https://github.com/ERPlora/hub/commit/40b97e11ed9109cc147eb32642220c11a4163263))

* fix: remove emojis for Windows cp1252 compatibility ([`cd0fdfd`](https://github.com/ERPlora/hub/commit/cd0fdfdbd5556e5fe8fcd07681d8b068979b73c9))

### Features

* feat: hub deply wip ([`c93b4c4`](https://github.com/ERPlora/hub/commit/c93b4c4b7772ca3e5c2db2c1f927b26a18f19584))

* feat: plugin middleware ([`e5ee5f8`](https://github.com/ERPlora/hub/commit/e5ee5f855320a583a2069884352c2c56e01762f9))

* feat: plugin middleware ([`8196843`](https://github.com/ERPlora/hub/commit/8196843b3083622915daeb05e9fa4c127a30abc1))

* feat: deploy ([`fb7f9d9`](https://github.com/ERPlora/hub/commit/fb7f9d9eaee97f4f34c9aebe88c709147c70806b))

* feat: deploy ([`6b13dec`](https://github.com/ERPlora/hub/commit/6b13dec6a221673d8794359cf7aa16dc97eb5081))

* feat: deploy ([`9a4fbbc`](https://github.com/ERPlora/hub/commit/9a4fbbc5b2e2bb0f1de66c9f3f71c364585c7314))

* feat: deploy ([`96dd052`](https://github.com/ERPlora/hub/commit/96dd052c4460f00648cb350a3c9ee74a198a1187))

* feat: include global configuration ([`7dbc357`](https://github.com/ERPlora/hub/commit/7dbc357a26f460c285d10201b486c7d60368ab20))

* feat: deploy ([`1581047`](https://github.com/ERPlora/hub/commit/158104783fa1781750cb0539a0434e0349647135))

* feat: deploy ([`097d938`](https://github.com/ERPlora/hub/commit/097d938fce09a3a98e4e195ce2742e3f0f4f45a1))

* feat: clean hub ([`1aa477e`](https://github.com/ERPlora/hub/commit/1aa477e34b6dca6c64a376635999b8a42ae66de6))

* feat: clean hub ([`52a1ccf`](https://github.com/ERPlora/hub/commit/52a1ccf699c243d01fc8b72cdef739ff0a4f9260))

* feat: plugin and activate ok ([`f5d2574`](https://github.com/ERPlora/hub/commit/f5d2574a1d769c6ac24f9a88556744f2de378554))

* feat: plugin and activate ([`02b13a4`](https://github.com/ERPlora/hub/commit/02b13a4aa538f85b3ca1ccc965635c68453176e5))

* feat: restart app when plugin si activate ([`cf27189`](https://github.com/ERPlora/hub/commit/cf2718928872cc89365f7574769c9c4567bbfc6c))

* feat: removed table plugins_admin ([`668360d`](https://github.com/ERPlora/hub/commit/668360dcef079fe28041769fd8f24948cb62bcc3))

* feat: plugin directory baset ([`da2048c`](https://github.com/ERPlora/hub/commit/da2048cbd169b71ffdff676bb165fabadadbd789))

* feat: plugins menu ([`6fbf4ed`](https://github.com/ERPlora/hub/commit/6fbf4ed93c1464b485fbdb814884193992448137))

* feat: django-components ([`58c7330`](https://github.com/ERPlora/hub/commit/58c73301dc565958fcb71a3399ba928806aa9fe8))

* feat: plugins wip ([`2a7c1f9`](https://github.com/ERPlora/hub/commit/2a7c1f98607c1ee9f2dc8e7475c46809d1a7a751))

* feat: update documentation ([`4801c97`](https://github.com/ERPlora/hub/commit/4801c9745a2c9a023dc5cea97b4c15743057c6ec))

* feat: tuneling ([`e57b8dc`](https://github.com/ERPlora/hub/commit/e57b8dc105e76e4825f89feb1767c931c08dee87))

* feat: logo ([`05e7089`](https://github.com/ERPlora/hub/commit/05e7089241ee741faca3e44f6f32f1751bab31f5))

* feat: card shadow ([`0428d27`](https://github.com/ERPlora/hub/commit/0428d27acb9119f0c4c4d960331702bd1c7ae4bb))

* feat: update color palete ([`cb8a7fc`](https://github.com/ERPlora/hub/commit/cb8a7fc2c231ee883b6362807491681dabfe24ca))

* feat: update inported library ([`2309f4f`](https://github.com/ERPlora/hub/commit/2309f4f8af32514b1573ba799311d6d700cd5a8b))

* feat: plugin system ([`a737895`](https://github.com/ERPlora/hub/commit/a7378952d8397aeb965b55ac9b944dd992ce163a))

* feat: full screen ([`137cd29`](https://github.com/ERPlora/hub/commit/137cd29d99d27c078fad18fc2176c3ec5b0abe03))

* feat: implement sync-on-access user verification system

- Add SyncQueue model for offline operations
- Add SyncService for processing sync queue
- Implement verify_user_access_with_cloud() helper for on-demand user verification
- Add detailed logging to Cloud Login flow for debugging
- Update PIN verification to check Cloud access on-demand
- Implement automatic user reactivation when deleted users do Cloud Login
- Add JWT validation tests
- Reorganize middleware into separate modules ([`05bf5c0`](https://github.com/ERPlora/hub/commit/05bf5c00d883a2fcccf6b04d64cd5038e958ce66))

* feat: websoket ([`4f05705`](https://github.com/ERPlora/hub/commit/4f057056cf834c8f24cdb9e01960e088430f3930))

* feat: Hub Registration and FRP Tunnel Implementation Complete ([`12396e7`](https://github.com/ERPlora/hub/commit/12396e73b6b388c7307719db1f9d2cb8a5dcd930))

* feat: generate native installers (AppImage, InnoSetup, DMG) with GPG signing

- Windows: InnoSetup installer (.exe) with autostart option
- Linux: AppImage with automatic autostart configuration
- macOS: Professional DMG (drag & drop to Applications)
- GPG signature (.asc) for each installer
- Auto-detect version from pyproject.toml ([`6a79ce3`](https://github.com/ERPlora/hub/commit/6a79ce376a1ffb1f1c16890f5809453eb4c90d7e))

* feat: move user data to external platform-specific locations

Data now persists outside the app for clean updates:

Platform-specific locations:
- Windows: C:\Users\<user>\AppData\Local\CPOSHub\
- macOS: ~/Library/Application Support/CPOSHub/ (hidden)
- Linux: ~/.cpos-hub/ (hidden)

Features:
- Database (SQLite) external
- Media files (uploads) external
- Plugins and their data external
- Reports (PDF/Excel) external
- Logs with rotation external
- Automatic backups external
- Automatic legacy migration on first run

Benefits:
- Data survives app updates/reinstalls
- Easier backups (one folder)
- Follows platform conventions
- Separates code from data

Documentation: docs/DATA_LOCATIONS.md ([`f7031a7`](https://github.com/ERPlora/hub/commit/f7031a7cf669bf88f84c73da3fe2502c9c6e42eb))

* feat: add native installers for all platforms

- Windows: InnoSetup installer (.exe) with autostart option
- macOS: Signed DMG with drag & drop (no autostart)
- Linux: AppImage with automatic autostart configuration

Installers:
- Windows: Program Files installation + Start Menu + autostart
- macOS: DMG with code signing (Developer ID)
- Linux: Portable AppImage + ~/.config/autostart

CI/CD: Updated GitHub Actions workflow to build native installers ([`07036f5`](https://github.com/ERPlora/hub/commit/07036f50f83173593a495f8e8c472cc2336b36da))

* feat: add GPG signing for release artifacts

- Add script to generate GPG key (scripts/generate-gpg-key.sh)
- Add script to sign releases (scripts/sign-release.sh)
- Update build-release.yml to sign all artifacts
- Add comprehensive verification guide (SIGNATURE_VERIFICATION.md)
- Add GPG setup guide for developers (GPG_SETUP.md)
- Update README with security section for GPG signatures
- All releases now include .asc signature files
- Supports Windows, macOS, and Linux artifacts ([`d6411b7`](https://github.com/ERPlora/hub/commit/d6411b780e8420b5c960e34f0df875f73edeb912))

* feat: add BUSL-1.1 license to protect against competitive clones

- Add Business Source License 1.1
- Allows free use for businesses and individuals
- Prohibits creating competing POS services
- Converts to Apache 2.0 in 2029
- Update pyproject.toml with license info
- Add license documentation to README ([`8cbcffd`](https://github.com/ERPlora/hub/commit/8cbcffdc249f767f25736ffa3ab27b579d3eee6e))

* feat: add BUSL-1.1 license to protect against competitive clones

- Add Business Source License 1.1
- Allows free use for businesses and individuals
- Prohibits creating competing POS services
- Converts to Apache 2.0 in 2029
- Update pyproject.toml with license info
- Add license documentation to README ([`3d0ea42`](https://github.com/ERPlora/hub/commit/3d0ea420784381ffb9ce8de594ab097be6586585))

### Performance Improvements

* perf: add dependency caching to release workflow (staging/main)

- Add pip cache to Python setup
- Add uv dependencies cache (.venv + ~/.cache/uv)
- Reduces build time by ~50% on cache hit
- Applies to both staging and main releases ([`76549f1`](https://github.com/ERPlora/hub/commit/76549f104f1f31d5bd2df3f202db51ef2deaf829))

* perf: optimize GitHub Actions to stay within 2000 min/month limit

OPTIMIZATIONS (reduces usage by 85%):

1. Remove macOS from develop builds (77% savings)
   - macOS is 10x more expensive than Linux
   - macOS only in final releases (build-release.yml)
   - Before: 52 min/build → After: 12 min/build

2. Add dependency caching (50% time reduction)
   - Cache Python pip packages
   - Cache uv virtual environments
   - Reduces install time from ~2min to ~30sec

3. Ignore non-code changes (30% fewer builds)
   - Skip builds for: *.md, docs/**, LICENSE, .gitignore
   - Only build when actual code changes

4. Cancel duplicate builds (20% waste elimination)
   - Auto-cancel previous builds on new push
   - Concurrency group per branch

ESTIMATED MONTHLY USAGE:
- Before: 7,800 min/month (390% of limit)
- After:  1,200 min/month (60% of limit) ✅

Leaves 800 min/month buffer for staging/production releases. ([`2b6aeca`](https://github.com/ERPlora/hub/commit/2b6aeca97f15bfb892fa1cc059185714273a2922))

### Refactoring

* refactor: convert base_dir docstring to comments to avoid raw string ([`df7be36`](https://github.com/ERPlora/hub/commit/df7be3693421775a92023f83ca0d70b5821743d2))

### Unknown

* chore: remove cache files from git and update gitignore ([`4e41665`](https://github.com/ERPlora/hub/commit/4e4166526c235e5bab944c980067358ec6915d1f))

* chore: refactor ([`84f8c97`](https://github.com/ERPlora/hub/commit/84f8c97635e92f7717758926dc971a306b6820cb))

* translation, and font ([`04c54ae`](https://github.com/ERPlora/hub/commit/04c54ae9fc3da8bd0a66207c2713f5dbd2477161))

* fix build ([`7dd183b`](https://github.com/ERPlora/hub/commit/7dd183bdeb1753d32afdbf628a118a00240d7cd8))

* chore: update documentation ([`f1d4019`](https://github.com/ERPlora/hub/commit/f1d4019c3aa283ca7cb320484c95053c2031f66d))

* test: add unit tests for core models and paths (61 tests)

Added comprehensive unit tests:

1. test_paths.py (27 tests)
   - DataPaths initialization and platform detection
   - Base directory for each OS (Windows, macOS, Linux)
   - All subdirectories (database, media, plugins, etc.)
   - Plugin-specific paths
   - Temp cleanup functionality
   - Module-level functions

2. test_models.py (34 tests) ✅ 100% passing
   - HubConfig model (5 tests)
     - Singleton pattern
     - Configuration fields
     - Timestamps
   - LocalUser model (15 tests)
     - PIN hashing and verification
     - User roles and colors
     - Initials generation
     - Email/cloud_id uniqueness
   - StoreConfig model (9 tests)
     - Singleton pattern
     - Completeness validation
     - Business configuration
   - Plugin model (5 tests)
     - Plugin registration
     - Menu ordering
     - Unique plugin_id

Results:
- 34/34 models tests passing (100%)
- 23/27 paths tests passing (85%)
- Total: 57/61 passing (93%)

Dependencies added: pytest, pytest-django ([`e06e410`](https://github.com/ERPlora/hub/commit/e06e4107551e06a2e55e0314e00fac9ea89edf0d))

* Revert "feat: generate native installers (AppImage, InnoSetup, DMG) with GPG signing"

This reverts commit d9ba35fa9a1371ecc1fa786d6dcfb6ffd8adba78. ([`07dadcf`](https://github.com/ERPlora/hub/commit/07dadcf444af3ac8784a0ca18e939cc19a63587b))

* chore: add GPG public key for release verification ([`ac37980`](https://github.com/ERPlora/hub/commit/ac379805079cd9dde4ccb8f06ea3c7a774270962))

* chore: merge main into develop (5 year license period) ([`07c85e8`](https://github.com/ERPlora/hub/commit/07c85e8d34cfd79fa42e951c8615cd9742c8986e))

* chore: update BUSL license period from 4 to 5 years

- Change Date: 2030-01-07 (5 years)
- Provides longer competitive advantage protection
- Each version protected for 5 years before converting to Apache 2.0 ([`001a8b1`](https://github.com/ERPlora/hub/commit/001a8b1f217d691573c64244d6db4cb7d4673d70))


## v0.8.0 (2025-11-07)

### Bug Fixes

* fix: finalize release 0.8.0 ([`7043a03`](https://github.com/ERPlora/hub/commit/7043a03e1a37cafea1a5123b10830d5949b5be8d))

### Features

* feat: build wip ([`ccf8932`](https://github.com/ERPlora/hub/commit/ccf893278805d209d0c47a2ebc966d0f22307372))

* feat: build wip ([`21c892a`](https://github.com/ERPlora/hub/commit/21c892a815d49445184ad455d71e3647ffd9f387))

* feat: build wip ([`a5d4bda`](https://github.com/ERPlora/hub/commit/a5d4bda9a747afe84dc65a2a41ef2ddf48da80c5))

* feat: build wip ([`8e88f43`](https://github.com/ERPlora/hub/commit/8e88f43a13b16e1f8261f3e156989f97303e1449))

* feat: build wip ([`565488f`](https://github.com/ERPlora/hub/commit/565488fe71b39cc5215f5e33e3b3449f1f731628))

* feat: build wip ([`83e5797`](https://github.com/ERPlora/hub/commit/83e57976b9047b2d6d0ee30b9237123564e59b57))

* feat: add 25 library to app ([`2f9969d`](https://github.com/ERPlora/hub/commit/2f9969d2b7ff4392ff2d2e56cb89bb590e5b8551))

* feat: build local ok ([`46b0727`](https://github.com/ERPlora/hub/commit/46b0727aca97ac2920d06c983851e4010dfa80d9))

* feat: build local ok ([`5419d37`](https://github.com/ERPlora/hub/commit/5419d37fce4fee9caeec24945faf2b93b831d0b3))

* feat: build local ok ([`b7e4797`](https://github.com/ERPlora/hub/commit/b7e4797d7a04e6085d0631b36058b905b9e3d47b))

* feat: build action ([`7d9615b`](https://github.com/ERPlora/hub/commit/7d9615b7e9b75e9c01d94e3f6337b24a05c3e06d))

* feat: build action ([`6a2428e`](https://github.com/ERPlora/hub/commit/6a2428ee119e17c5e4b430deb0617e3d8b5db439))

* feat: build action ([`2cd500a`](https://github.com/ERPlora/hub/commit/2cd500a136e70f794aba1b30494cd8616b484dc3))

* feat: build action ([`e2d65b3`](https://github.com/ERPlora/hub/commit/e2d65b3b28fd1d3e58b292a9d57e03c69c18623d))

* feat: build action ([`b3befcc`](https://github.com/ERPlora/hub/commit/b3befccb49c17ba0da1e0036886004c11c02f7b7))

* feat: build action ([`8a2c771`](https://github.com/ERPlora/hub/commit/8a2c771ef8de6c7b1d2d83d5a3bcf63529b34c98))

* feat: build action ([`c094dff`](https://github.com/ERPlora/hub/commit/c094dffffcc7a7dba33df59cfaaf6a5fbcfa0505))

* feat: build action ([`26513b9`](https://github.com/ERPlora/hub/commit/26513b9c3d8683f0c19d12df0c8b6c029a649977))

* feat: build action ([`83494a5`](https://github.com/ERPlora/hub/commit/83494a5947a7940f7a8e7fcd619531c7cf7fd471))

* feat: build action ([`cd84bd3`](https://github.com/ERPlora/hub/commit/cd84bd320d3b57f2c83e7bc070f72d8d087db032))

* feat: build action ([`02e8487`](https://github.com/ERPlora/hub/commit/02e8487cb3595b204a05f848876449aca5e9b646))

* feat: build action ([`58b070f`](https://github.com/ERPlora/hub/commit/58b070f9149966b1427fffb7520113118c7865df))

* feat: build action ([`24848db`](https://github.com/ERPlora/hub/commit/24848db9fac6535275cf32cdbe03b12da8e7ad67))

* feat: uv and python semantic realese ([`c886880`](https://github.com/ERPlora/hub/commit/c8868805a09a503581bd3ee886c9168ee81c7206))

* feat: actions and build ([`bef4f44`](https://github.com/ERPlora/hub/commit/bef4f440027afba8e7d9b6df32eefb081f71493d))

* feat: remove plugin zip ([`a9cf55c`](https://github.com/ERPlora/hub/commit/a9cf55c419c4aa37900b5cb0d1f86a3882d1d493))

* feat: plugin loader ([`6636340`](https://github.com/ERPlora/hub/commit/6636340668b83286a3d085a58ed7afa25a392918))

* feat(core):  theme ([`873266c`](https://github.com/ERPlora/hub/commit/873266c18151b54d054cd47cd81099b26234cc89))

* feat(auth):  login and pin ([`bb431f7`](https://github.com/ERPlora/hub/commit/bb431f70ab69392474be2bf7443ab904115f7ea0))

* feat(base): inital commit ([`26d3834`](https://github.com/ERPlora/hub/commit/26d3834298c9c3d75eefbb331edf6c4f281444bf))

### Unknown

* chore: trigger release 0.8.0 ([`20289a6`](https://github.com/ERPlora/hub/commit/20289a63be745885a8710714a5110104a5b273a2))
