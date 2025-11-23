# CHANGELOG


## v0.8.2-rc.7 (2025-11-23)

### Features

* feat: deploy ([`8e93db0`](https://github.com/ERPlora/hub/commit/8e93db09f38a9e4c565660c36cb7faf7619ed0b5))


## v0.8.2-rc.6 (2025-11-23)

### Features

* feat: deploy ([`3a481a8`](https://github.com/ERPlora/hub/commit/3a481a87fb498ecefae0e0ef2cdc80b1db9b0c62))


## v0.8.2-rc.5 (2025-11-23)

### Features

* feat: deploy ([`71e4241`](https://github.com/ERPlora/hub/commit/71e42418fcbf860bb4e0626bb8f34be22d4a01b8))


## v0.8.2-rc.4 (2025-11-23)

### Features

* feat: deploy ([`e35c90e`](https://github.com/ERPlora/hub/commit/e35c90e6722cfda22987ba0b1df0486ee74d8dab))


## v0.8.2-rc.3 (2025-11-23)

### Features

* feat: include global configuration ([`74cbf9f`](https://github.com/ERPlora/hub/commit/74cbf9f7077d4256fd06f38fd1aa5ec465cefd3f))

* feat: deploy ([`cf2c781`](https://github.com/ERPlora/hub/commit/cf2c781eef0bed1d8d65746d94a94e11f2ced21b))

* feat: deploy ([`c9efb47`](https://github.com/ERPlora/hub/commit/c9efb4729e56fe91b9b3f7ce4fae3a87e3a81686))


## v0.8.2-rc.2 (2025-11-23)

### Bug Fixes

* fix: build ([`730dedf`](https://github.com/ERPlora/hub/commit/730dedf209739089bac0a6f7847ce149147daf27))

* fix: frp client ([`41873ee`](https://github.com/ERPlora/hub/commit/41873ee0daf2025e67776e8d1e22ac76a2aab14f))

* fix: update system ([`844c989`](https://github.com/ERPlora/hub/commit/844c989990c3659e6db3773d870245dd92d898e7))

### Features

* feat: clean hub ([`ff19651`](https://github.com/ERPlora/hub/commit/ff196516512ceb4a9fa1467983578b8e6cdbb321))

* feat: clean hub ([`789f072`](https://github.com/ERPlora/hub/commit/789f0724c9267763b24d8c7049fe175880b6447c))

* feat: plugin and activate ok ([`95e6fbb`](https://github.com/ERPlora/hub/commit/95e6fbb023598c30d55dd75b32854e072a024cf6))

* feat: plugin and activate ([`9bbcbdf`](https://github.com/ERPlora/hub/commit/9bbcbdfbbd808e91c89b5a7b8cf42c46f54f413c))

* feat: restart app when plugin si activate ([`f331eba`](https://github.com/ERPlora/hub/commit/f331eba6319ecdb9ebd9832e01a5a22686764b44))

* feat: removed table plugins_admin ([`5c30725`](https://github.com/ERPlora/hub/commit/5c30725dc24443263c09b1b6f6f8ec76c4ba6603))

* feat: plugin directory baset ([`3f28d65`](https://github.com/ERPlora/hub/commit/3f28d65e2f675de2fa3accb38d228773b93ba1ea))

* feat: plugins menu ([`87f8900`](https://github.com/ERPlora/hub/commit/87f89006abed5f4e84fb24503e2bfc1bad4b7167))

* feat: django-components ([`1783e1a`](https://github.com/ERPlora/hub/commit/1783e1a13630867a9f0f4d7cb4901b13f34610bd))

* feat: plugins wip ([`3cf0532`](https://github.com/ERPlora/hub/commit/3cf0532ca06cf65c590bc6db447cc9360ab60d13))

* feat: update documentation ([`19a3efa`](https://github.com/ERPlora/hub/commit/19a3efab55064ed261f22f89729419adcaff9f55))

* feat: tuneling ([`29bbe83`](https://github.com/ERPlora/hub/commit/29bbe834ef5ab7afdd8f76467a3bcbe747532c41))

* feat: logo ([`beb1b81`](https://github.com/ERPlora/hub/commit/beb1b814532ffe2c5014f5369477a69a2ddd38a4))

* feat: card shadow ([`5265c43`](https://github.com/ERPlora/hub/commit/5265c437e45909f4de793dab6d8fab33902d1bcc))

* feat: update color palete ([`ca8c2a5`](https://github.com/ERPlora/hub/commit/ca8c2a55cf9ffb77b3a4999a86953763f751a1dd))

* feat: update inported library ([`61ccd82`](https://github.com/ERPlora/hub/commit/61ccd82b607f07d5c63585ba78706d2c91354c11))

* feat: plugin system ([`ac9b107`](https://github.com/ERPlora/hub/commit/ac9b107edb3743d3b21f6272b5fc96b86820d6b5))

* feat: full screen ([`0b31203`](https://github.com/ERPlora/hub/commit/0b312034d7ecce9b37dff10689132edae16d6e0b))

* feat: implement sync-on-access user verification system

- Add SyncQueue model for offline operations
- Add SyncService for processing sync queue
- Implement verify_user_access_with_cloud() helper for on-demand user verification
- Add detailed logging to Cloud Login flow for debugging
- Update PIN verification to check Cloud access on-demand
- Implement automatic user reactivation when deleted users do Cloud Login
- Add JWT validation tests
- Reorganize middleware into separate modules

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`593e1ee`](https://github.com/ERPlora/hub/commit/593e1ee4764fd0529a71684a413a115dc270c25c))

* feat: websoket ([`80d81ff`](https://github.com/ERPlora/hub/commit/80d81ff95e6d8d2bc351116b70517a141e1596cd))

* feat: Hub Registration and FRP Tunnel Implementation Complete ([`365c3ad`](https://github.com/ERPlora/hub/commit/365c3ad4f443a6fb53f9be52de101a2220e106c3))

### Performance Improvements

* perf: add dependency caching to release workflow (staging/main)

- Add pip cache to Python setup
- Add uv dependencies cache (.venv + ~/.cache/uv)
- Reduces build time by ~50% on cache hit
- Applies to both staging and main releases ([`f19da08`](https://github.com/ERPlora/hub/commit/f19da08550538cf73c520353e9c4264a2e1a12dd))

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

Leaves 800 min/month buffer for staging/production releases. ([`48070c3`](https://github.com/ERPlora/hub/commit/48070c390e7134489910b9e75450c710e7b0377e))

### Unknown

* chore: refactor ([`2b9a566`](https://github.com/ERPlora/hub/commit/2b9a566b4abe116ba5fafac9e199d2e3002775aa))

* translation, and font ([`34d0632`](https://github.com/ERPlora/hub/commit/34d0632f7593b823f2808312afd40a6a6d07b306))

* fix build ([`b2dd39d`](https://github.com/ERPlora/hub/commit/b2dd39d9d508ce900c2203e1f3c1b55255b8bc80))

* chore: update documentation ([`f895cac`](https://github.com/ERPlora/hub/commit/f895cac8b8c486db73d25f83e361678e7a592428))

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

Dependencies added: pytest, pytest-django ([`cdb7cf3`](https://github.com/ERPlora/hub/commit/cdb7cf34e6369afa6318b909f222c5f497eb16c9))

* Revert "feat: generate native installers (AppImage, InnoSetup, DMG) with GPG signing"

This reverts commit d9ba35fa9a1371ecc1fa786d6dcfb6ffd8adba78. ([`22c1d11`](https://github.com/ERPlora/hub/commit/22c1d11278dbcead7088141006044b444f16a334))


## v0.8.2-rc.1 (2025-11-07)

### Bug Fixes

* fix: add raw string to base_dir docstring to prevent unicode escape error ([`074337c`](https://github.com/ERPlora/hub/commit/074337c92870ca738645fffe3445ce7f450cec7c))

### Features

* feat: generate native installers (AppImage, InnoSetup, DMG) with GPG signing

- Windows: InnoSetup installer (.exe) with autostart option
- Linux: AppImage with automatic autostart configuration
- macOS: Professional DMG (drag & drop to Applications)
- GPG signature (.asc) for each installer
- Auto-detect version from pyproject.toml ([`d9ba35f`](https://github.com/ERPlora/hub/commit/d9ba35fa9a1371ecc1fa786d6dcfb6ffd8adba78))

### Refactoring

* refactor: convert base_dir docstring to comments to avoid raw string ([`5990517`](https://github.com/ERPlora/hub/commit/5990517a9a4bf97e9d8b45d893ad716a87a6a628))


## v0.12.1 (2025-11-07)

### Bug Fixes

* fix: unicode escape error in paths.py docstring

Use raw string (r""") to prevent Python from interpreting backslashes
as escape sequences in Windows path examples. ([`c048e93`](https://github.com/ERPlora/hub/commit/c048e930431eeb12fc67bf1ff5a22d4f72d133a3))

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
- Follows Django app conventions ([`0c54c5f`](https://github.com/ERPlora/hub/commit/0c54c5f70d68bf3f4996079b3b08113ce2c5cc43))


## v0.12.0 (2025-11-07)

### Features

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

Documentation: docs/DATA_LOCATIONS.md ([`fe5d513`](https://github.com/ERPlora/hub/commit/fe5d513e64e29d70f05306e4ab474b073d91f7ae))


## v0.11.0 (2025-11-07)

### Features

* feat: add native installers for all platforms

- Windows: InnoSetup installer (.exe) with autostart option
- macOS: Signed DMG with drag & drop (no autostart)
- Linux: AppImage with automatic autostart configuration

Installers:
- Windows: Program Files installation + Start Menu + autostart
- macOS: DMG with code signing (Developer ID)
- Linux: Portable AppImage + ~/.config/autostart

CI/CD: Updated GitHub Actions workflow to build native installers ([`3f3d05e`](https://github.com/ERPlora/hub/commit/3f3d05e08b02d95e989c8a314f778fa1787b7b5d))

### Unknown

* chore: add GPG public key for release verification ([`24f58ce`](https://github.com/ERPlora/hub/commit/24f58ceaae2eff1fef9fe72d21ccd5af4dfb1db6))


## v0.10.0 (2025-11-07)

### Features

* feat: add GPG signing for release artifacts

- Add script to generate GPG key (scripts/generate-gpg-key.sh)
- Add script to sign releases (scripts/sign-release.sh)
- Update build-release.yml to sign all artifacts
- Add comprehensive verification guide (SIGNATURE_VERIFICATION.md)
- Add GPG setup guide for developers (GPG_SETUP.md)
- Update README with security section for GPG signatures
- All releases now include .asc signature files
- Supports Windows, macOS, and Linux artifacts ([`73e7038`](https://github.com/ERPlora/hub/commit/73e70387edaa101558a7e8b5bbf317d20a955737))

### Unknown

* chore: merge main into develop (5 year license period) ([`475bde6`](https://github.com/ERPlora/hub/commit/475bde656663df41bb486b80c5eaa67a0a8df4ab))

* chore: update BUSL license period from 4 to 5 years

- Change Date: 2030-01-07 (5 years)
- Provides longer competitive advantage protection
- Each version protected for 5 years before converting to Apache 2.0 ([`ad209f7`](https://github.com/ERPlora/hub/commit/ad209f779b1ccd9ec9a02bb589a32444acd10d12))


## v0.9.0 (2025-11-07)

### Features

* feat: add BUSL-1.1 license to protect against competitive clones

- Add Business Source License 1.1
- Allows free use for businesses and individuals
- Prohibits creating competing POS services
- Converts to Apache 2.0 in 2029
- Update pyproject.toml with license info
- Add license documentation to README ([`9a2463f`](https://github.com/ERPlora/hub/commit/9a2463f1ec8dfebd2ea262f9c8604ef408234206))


## v0.8.1 (2025-11-07)

### Bug Fixes

* fix: remove emojis for Windows cp1252 compatibility ([`17dc46d`](https://github.com/ERPlora/hub/commit/17dc46d7d7b7346f4177da0caece192f0b616c8e))

### Features

* feat: add BUSL-1.1 license to protect against competitive clones

- Add Business Source License 1.1
- Allows free use for businesses and individuals
- Prohibits creating competing POS services
- Converts to Apache 2.0 in 2029
- Update pyproject.toml with license info
- Add license documentation to README ([`053b77f`](https://github.com/ERPlora/hub/commit/053b77fd4d3a20adffed823f71f1eb3a5dfa70ef))


## v0.8.0 (2025-11-07)

### Bug Fixes

* fix: finalize release 0.8.0 ([`62a0053`](https://github.com/ERPlora/hub/commit/62a0053e3676e408d8791e71b7b0a4ac2bec46be))

### Unknown

* chore: trigger release 0.8.0 ([`a63e399`](https://github.com/ERPlora/hub/commit/a63e399b36fb84b6cd9f0a06ada75141b8a69021))


## v0.8.0-rc.4 (2025-11-06)

### Features

* feat: build wip ([`a3a57c3`](https://github.com/ERPlora/hub/commit/a3a57c3a93b7f3b18068140ba2d66e4636274748))


## v0.8.0-rc.3 (2025-11-06)

### Features

* feat: build wip ([`a4438df`](https://github.com/ERPlora/hub/commit/a4438df519b6965693afc1f9ef1502ffcb076236))


## v0.8.0-rc.2 (2025-11-06)

### Features

* feat: build wip ([`3d49477`](https://github.com/ERPlora/hub/commit/3d494770d199a4750345d64626c9c6b1613fb158))


## v0.8.0-rc.1 (2025-11-06)

### Features

* feat: build wip ([`8964bcc`](https://github.com/ERPlora/hub/commit/8964bcc7042367b246230ce7049a77523781428a))

* feat: build wip ([`c20364f`](https://github.com/ERPlora/hub/commit/c20364f8c298df99c7e3d1eec14f55e94e5af7fa))

* feat: build wip ([`7aefb0a`](https://github.com/ERPlora/hub/commit/7aefb0ad9a802e003a253840ebcb348ee66c0133))

* feat: add 25 library to app ([`b2ce44b`](https://github.com/ERPlora/hub/commit/b2ce44b5f141b286c578399b688a426254e180e2))

* feat: build local ok ([`f32a560`](https://github.com/ERPlora/hub/commit/f32a5604795df38be9c0be9fb3749bb7c8916349))

* feat: build local ok ([`a389c1a`](https://github.com/ERPlora/hub/commit/a389c1a11e561f894f17fb521a44aea852ea2c61))

* feat: build local ok ([`18da96f`](https://github.com/ERPlora/hub/commit/18da96fdd0ad2934107d65d9ccee4a1aa744cb7b))

* feat: build action ([`238c888`](https://github.com/ERPlora/hub/commit/238c888be753dbad31f0335cbad33a4ccd0f2d95))

* feat: build action ([`fd7ce5a`](https://github.com/ERPlora/hub/commit/fd7ce5a7f2d1c7545091ab52f4f646d0033ce8c4))


## v0.6.0 (2025-11-05)


## v0.5.0 (2025-11-05)


## v0.6.0-rc.1 (2025-11-05)

### Features

* feat: build action ([`a9e4e05`](https://github.com/ERPlora/hub/commit/a9e4e05d8347daeee07d9a2d6814a02f4ccc6337))


## v0.4.0 (2025-11-05)


## v0.4.0-dev.4 (2025-11-05)

### Features

* feat: build action ([`034824e`](https://github.com/ERPlora/hub/commit/034824e7c886d6233b7e63e1ebef4ca0ba88f50e))


## v0.4.0-dev.3 (2025-11-05)

### Features

* feat: build action ([`80e6a28`](https://github.com/ERPlora/hub/commit/80e6a28d1cfa10a744db2f96c0869ae7633d1fce))


## v0.3.0 (2025-11-05)


## v0.2.0 (2025-11-05)


## v0.4.0-dev.2 (2025-11-05)

### Features

* feat: build action ([`0dcd00a`](https://github.com/ERPlora/hub/commit/0dcd00a2eb7a755412227586c99cd5dc322a761a))


## v0.4.0-dev.1 (2025-11-05)

### Features

* feat: build action ([`4e87524`](https://github.com/ERPlora/hub/commit/4e8752464aaa9e98cfd3fa86bad3d869fb1feeb9))

* feat: build action ([`c040b1e`](https://github.com/ERPlora/hub/commit/c040b1ec6b7450530245812a4ffcf42f726bbdb6))

* feat: build action ([`ca9a05f`](https://github.com/ERPlora/hub/commit/ca9a05ff3fd1a57b1a6af5ef2f76125a7fa09333))


## v0.1.0 (2025-11-05)


## v0.1.0-dev.4 (2025-11-05)

### Features

* feat: build action ([`9f9d0d7`](https://github.com/ERPlora/hub/commit/9f9d0d79104681f7a03bd307b3a896f3b99a0137))


## v0.1.0-dev.3 (2025-11-05)

### Features

* feat: build action ([`6c95f56`](https://github.com/ERPlora/hub/commit/6c95f569e17d1d2d9afc88a0a379e6b876a99be6))


## v0.1.0-dev.2 (2025-11-05)

### Features

* feat: build action ([`5c388ac`](https://github.com/ERPlora/hub/commit/5c388ac22b6640710cef863b32ee3299ec35e559))


## v0.1.0-dev.1 (2025-11-05)

### Features

* feat: build action ([`aac3841`](https://github.com/ERPlora/hub/commit/aac384104b66316931a3ed86bb3a25249d938205))

* feat: uv and python semantic realese ([`b0f6b64`](https://github.com/ERPlora/hub/commit/b0f6b64e2e86d8e7edf87365d96477f0ddbae56b))

* feat: actions and build ([`9df3f77`](https://github.com/ERPlora/hub/commit/9df3f7777834977ad040be4f119180e167f0f4bf))

* feat: remove plugin zip ([`2f7df85`](https://github.com/ERPlora/hub/commit/2f7df85ff8ba92f54d8937586ee06acf2c095454))

* feat: plugin loader ([`7f00c40`](https://github.com/ERPlora/hub/commit/7f00c4066f2a23c7b8678d6e4480be7ed1b4b064))

* feat(core):  theme ([`3533f44`](https://github.com/ERPlora/hub/commit/3533f4480d119e23de6c975aa743b88e9266566a))

* feat(auth):  login and pin ([`7aeac38`](https://github.com/ERPlora/hub/commit/7aeac38b3f7df9aaf0fc8fa8443274b4753987c0))

* feat(base): inital commit ([`4e85690`](https://github.com/ERPlora/hub/commit/4e856909d38098b2848994113d1e5e935fb92be3))
