# CHANGELOG


## v0.15.0-rc.1 (2025-12-03)

### Bug Fixes

* fix: update Dockerfile for production deployment ([`43c0e81`](https://github.com/ERPlora/hub/commit/43c0e818131f5d9e6bd7f917faa3768266a27768))

* fix: build ([`6700a76`](https://github.com/ERPlora/hub/commit/6700a7618949b4c13e54632214e7de6ddd5c5d1d))

* fix: frp client ([`954ad74`](https://github.com/ERPlora/hub/commit/954ad745375ec2e487d8b8d72e4b0aa7de529dfb))

* fix: update system ([`b4a721c`](https://github.com/ERPlora/hub/commit/b4a721c65f6e1ed533bd9b85bee2a6ffbee65c80))

* fix: add raw string to base_dir docstring to prevent unicode escape error ([`333b9f0`](https://github.com/ERPlora/hub/commit/333b9f0d44fead2f40c58bbceae4a5ab7c45de4d))

* fix: unicode escape error in paths.py docstring

Use raw string (r""") to prevent Python from interpreting backslashes
as escape sequences in Windows path examples. ([`fa3c483`](https://github.com/ERPlora/hub/commit/fa3c483d4f1de0af635b571f5bcf87586df442a0))

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
- Follows Django app conventions ([`9bc74fa`](https://github.com/ERPlora/hub/commit/9bc74fadea5e922bcbad9ceeec748dabc45425c3))

* fix: remove emojis for Windows cp1252 compatibility ([`633ff4a`](https://github.com/ERPlora/hub/commit/633ff4a3c2ab1e084baf11f1b8b075813c376af7))

* fix: finalize release 0.8.0 ([`dbaebf2`](https://github.com/ERPlora/hub/commit/dbaebf2effd962b6497beea75aa2b8a4504da1dd))

### Features

* feat: hub deply wip ([`1e537da`](https://github.com/ERPlora/hub/commit/1e537da584d327c7f998c066aaff7fe4cb94aa46))

* feat: plugin middleware ([`d656083`](https://github.com/ERPlora/hub/commit/d6560837dd2903f780c5f9940e7b222c4679b24b))

* feat: plugin middleware ([`af2cdcc`](https://github.com/ERPlora/hub/commit/af2cdcc63a923820e52dde22527f5f479b5a73a6))

* feat: deploy ([`69dcf45`](https://github.com/ERPlora/hub/commit/69dcf45810f4334ab3e5f0ebb5e3d08157b73749))

* feat: deploy ([`b25be9f`](https://github.com/ERPlora/hub/commit/b25be9f6259218c1406e3169c4f14c3d2dfa1f78))

* feat: deploy ([`e85dc57`](https://github.com/ERPlora/hub/commit/e85dc57a3d315c0f33a67e57792a5d778a5de0b3))

* feat: deploy ([`3051a1c`](https://github.com/ERPlora/hub/commit/3051a1cba3a86fc1c2294d6860419ec7050bb2b2))

* feat: include global configuration ([`0133d9d`](https://github.com/ERPlora/hub/commit/0133d9d15dc1bb957cbd725313f4c0f285ab7af0))

* feat: deploy ([`b240716`](https://github.com/ERPlora/hub/commit/b240716049d47e0e0d9ed1cab943cc2ec97a95c5))

* feat: deploy ([`f2244d2`](https://github.com/ERPlora/hub/commit/f2244d288107320b7f5855dbcf6dc7c325c4ca4c))

* feat: clean hub ([`8838a0f`](https://github.com/ERPlora/hub/commit/8838a0fefc8d8d1cb747b7aa463aa8a701db7040))

* feat: clean hub ([`394de74`](https://github.com/ERPlora/hub/commit/394de74b0e4bbd8e2fb537659fa4fd4c83fea0e7))

* feat: plugin and activate ok ([`31c24c6`](https://github.com/ERPlora/hub/commit/31c24c6705092c44a1a175f70290067dec473196))

* feat: plugin and activate ([`11f8d01`](https://github.com/ERPlora/hub/commit/11f8d010d6db55039020ebd9b7e5fdca0ca9eb61))

* feat: restart app when plugin si activate ([`9b89c48`](https://github.com/ERPlora/hub/commit/9b89c48fc27fe775dcaaf5a4ebde54aac92aead6))

* feat: removed table plugins_admin ([`ef3725b`](https://github.com/ERPlora/hub/commit/ef3725b3b1f7463aeb611d08ab09b238792c5617))

* feat: plugin directory baset ([`09b5a02`](https://github.com/ERPlora/hub/commit/09b5a02651cef01ec2e91959bd8e6866d34bed5f))

* feat: plugins menu ([`49dfc5c`](https://github.com/ERPlora/hub/commit/49dfc5ca63c7afd778fc11ac626b9d5050fc6e82))

* feat: django-components ([`b99ae9d`](https://github.com/ERPlora/hub/commit/b99ae9df4a98aefd9caee4b14248bb0dcb06753d))

* feat: plugins wip ([`ce6b018`](https://github.com/ERPlora/hub/commit/ce6b01875eef1ee62fe0a31263bceefbcfb1b133))

* feat: update documentation ([`5443b3e`](https://github.com/ERPlora/hub/commit/5443b3e21a2f7ba8a7cb86f2d741cf283e887b66))

* feat: tuneling ([`c733fd3`](https://github.com/ERPlora/hub/commit/c733fd3bb5c1ed6b86a84e30f74a31757a817b4a))

* feat: logo ([`4de9173`](https://github.com/ERPlora/hub/commit/4de917305cf8abe0f292c2988f4fef136e12f603))

* feat: card shadow ([`7a57bf8`](https://github.com/ERPlora/hub/commit/7a57bf87d9a390b800e0770934c6c412f61bac78))

* feat: update color palete ([`6423452`](https://github.com/ERPlora/hub/commit/6423452eca1db1c607bf61ac167a167001301e44))

* feat: update inported library ([`8c07dee`](https://github.com/ERPlora/hub/commit/8c07dee7ca690f079c9a580a58e0c350ebc5f315))

* feat: plugin system ([`4189fda`](https://github.com/ERPlora/hub/commit/4189fda07ef23f001fe9c39d0220c5c8baeb0ed7))

* feat: full screen ([`0a406ed`](https://github.com/ERPlora/hub/commit/0a406ed421e7edc012c60872bc530a6cfcbe6a3b))

* feat: implement sync-on-access user verification system

- Add SyncQueue model for offline operations
- Add SyncService for processing sync queue
- Implement verify_user_access_with_cloud() helper for on-demand user verification
- Add detailed logging to Cloud Login flow for debugging
- Update PIN verification to check Cloud access on-demand
- Implement automatic user reactivation when deleted users do Cloud Login
- Add JWT validation tests
- Reorganize middleware into separate modules ([`cc63b02`](https://github.com/ERPlora/hub/commit/cc63b026c135d26db68dd6f83f1b0fdc88033581))

* feat: websoket ([`c84a638`](https://github.com/ERPlora/hub/commit/c84a638a4854b3fcd24b67e65c553bb778976c60))

* feat: Hub Registration and FRP Tunnel Implementation Complete ([`8ed18b4`](https://github.com/ERPlora/hub/commit/8ed18b40c011fc13496112a92916bce6c05b27a9))

* feat: generate native installers (AppImage, InnoSetup, DMG) with GPG signing

- Windows: InnoSetup installer (.exe) with autostart option
- Linux: AppImage with automatic autostart configuration
- macOS: Professional DMG (drag & drop to Applications)
- GPG signature (.asc) for each installer
- Auto-detect version from pyproject.toml ([`e15d674`](https://github.com/ERPlora/hub/commit/e15d674996754bc4df1f98717a30e0f32f6a3ab9))

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

Documentation: docs/DATA_LOCATIONS.md ([`1bb8ed2`](https://github.com/ERPlora/hub/commit/1bb8ed22e49fa21827746d3bb13bf1feef7e6730))

* feat: add native installers for all platforms

- Windows: InnoSetup installer (.exe) with autostart option
- macOS: Signed DMG with drag & drop (no autostart)
- Linux: AppImage with automatic autostart configuration

Installers:
- Windows: Program Files installation + Start Menu + autostart
- macOS: DMG with code signing (Developer ID)
- Linux: Portable AppImage + ~/.config/autostart

CI/CD: Updated GitHub Actions workflow to build native installers ([`1f2106e`](https://github.com/ERPlora/hub/commit/1f2106ecd5383fa723e87f52a565375c22cecb2f))

* feat: add GPG signing for release artifacts

- Add script to generate GPG key (scripts/generate-gpg-key.sh)
- Add script to sign releases (scripts/sign-release.sh)
- Update build-release.yml to sign all artifacts
- Add comprehensive verification guide (SIGNATURE_VERIFICATION.md)
- Add GPG setup guide for developers (GPG_SETUP.md)
- Update README with security section for GPG signatures
- All releases now include .asc signature files
- Supports Windows, macOS, and Linux artifacts ([`e13be3c`](https://github.com/ERPlora/hub/commit/e13be3c7e1b63069fb18948dd8392b057f5d09e5))

* feat: add BUSL-1.1 license to protect against competitive clones

- Add Business Source License 1.1
- Allows free use for businesses and individuals
- Prohibits creating competing POS services
- Converts to Apache 2.0 in 2029
- Update pyproject.toml with license info
- Add license documentation to README ([`9fe54e8`](https://github.com/ERPlora/hub/commit/9fe54e8bfd9602fe410a27ca172e36e269f5e55c))

* feat: add BUSL-1.1 license to protect against competitive clones

- Add Business Source License 1.1
- Allows free use for businesses and individuals
- Prohibits creating competing POS services
- Converts to Apache 2.0 in 2029
- Update pyproject.toml with license info
- Add license documentation to README ([`e285be1`](https://github.com/ERPlora/hub/commit/e285be1b8927b25d400b14525a27ad9f0a8205a8))

* feat: build wip ([`9752e76`](https://github.com/ERPlora/hub/commit/9752e76f07c3ccaa696a2a6b7b3e1860c8044bb9))

* feat: build wip ([`64b0a74`](https://github.com/ERPlora/hub/commit/64b0a74168b4fc42c529599c203d00c8ad246ac2))

* feat: build wip ([`5921db9`](https://github.com/ERPlora/hub/commit/5921db919f32d37276d428ca138cc1b488a06cbe))

* feat: build wip ([`c0b790b`](https://github.com/ERPlora/hub/commit/c0b790bf2b236f5eb9f2158479d78c43e1d03346))

* feat: build wip ([`61de742`](https://github.com/ERPlora/hub/commit/61de7423d5fdc37534f4569859d76eb175ce14a0))

* feat: build wip ([`bba7ede`](https://github.com/ERPlora/hub/commit/bba7eded962722a4bc8a8ad4f55c91a5060557d4))

* feat: add 25 library to app ([`a095e07`](https://github.com/ERPlora/hub/commit/a095e07a46ce76d54ab6f317896bd3b58e271d78))

* feat: build local ok ([`8f91b43`](https://github.com/ERPlora/hub/commit/8f91b4394e15a14c16b0c6af40514eb46c033814))

* feat: build local ok ([`2b783e5`](https://github.com/ERPlora/hub/commit/2b783e535f3b911fd390fbe7bd18a3d1eee25b3a))

* feat: build local ok ([`0d1173e`](https://github.com/ERPlora/hub/commit/0d1173e7b5d8faa3b1fb0ed2ecc071f7413c5759))

* feat: build action ([`e13b920`](https://github.com/ERPlora/hub/commit/e13b920a1c4390076aa40dfa9242385aa3e11c0d))

* feat: build action ([`a3ec3fd`](https://github.com/ERPlora/hub/commit/a3ec3fd2d1872acb0529e474b09fe4e800118969))

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

### Performance Improvements

* perf: add dependency caching to release workflow (staging/main)

- Add pip cache to Python setup
- Add uv dependencies cache (.venv + ~/.cache/uv)
- Reduces build time by ~50% on cache hit
- Applies to both staging and main releases ([`35f06f6`](https://github.com/ERPlora/hub/commit/35f06f6e6b293605c512df24889c98e5869b4c35))

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

Leaves 800 min/month buffer for staging/production releases. ([`95cee79`](https://github.com/ERPlora/hub/commit/95cee799f9e47a29094265712a2bdfa3b64722c8))

### Refactoring

* refactor: convert base_dir docstring to comments to avoid raw string ([`b5ebf65`](https://github.com/ERPlora/hub/commit/b5ebf658a9d7e665a47dbb784d1003e0c7d5a4fb))

### Unknown

* chore: merge CODEOWNERS update from main ([`7cfec74`](https://github.com/ERPlora/hub/commit/7cfec746e709c785f7418735ec4f4b91132f662b))

* chore: merge CODEOWNERS update from main ([`72a3014`](https://github.com/ERPlora/hub/commit/72a30148546357c52ea778cac59af8914b51b38c))

* chore: add 1oan-Beilic as code owner ([`eff5d71`](https://github.com/ERPlora/hub/commit/eff5d71aa610b61aec75b2cf5f2ff796ef80616c))

* chore: add CODEOWNERS file for PR approvals ([`b64b300`](https://github.com/ERPlora/hub/commit/b64b30021cccf9358f863d619ab2c99706b0134f))

* chore: remove cache files from git and update gitignore ([`1e8a4ae`](https://github.com/ERPlora/hub/commit/1e8a4aedd96b0c712be0ae7a80b27773e977d22c))

* chore: refactor ([`0e73c83`](https://github.com/ERPlora/hub/commit/0e73c830bc84e458c259206560045c7b6dd5d7d6))

* translation, and font ([`6487918`](https://github.com/ERPlora/hub/commit/6487918187e0dbc86f7ca1d1cdbe853e8c9b1d07))

* fix build ([`5dfe60e`](https://github.com/ERPlora/hub/commit/5dfe60e4ac251617b376f42ff8a108cf42de193f))

* chore: update documentation ([`01a96c4`](https://github.com/ERPlora/hub/commit/01a96c4820e1c55d7187fad40709fee9f019e1a3))

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

Dependencies added: pytest, pytest-django ([`04f1633`](https://github.com/ERPlora/hub/commit/04f16330ead5d84eabef407da01cd74d3d542f92))

* Revert "feat: generate native installers (AppImage, InnoSetup, DMG) with GPG signing"

This reverts commit d9ba35fa9a1371ecc1fa786d6dcfb6ffd8adba78. ([`801a5c9`](https://github.com/ERPlora/hub/commit/801a5c9f4bc08bf177f11151460e5c928303ecd1))

* chore: add GPG public key for release verification ([`3b549ba`](https://github.com/ERPlora/hub/commit/3b549baea5e7e2e11e547326d316858e7a4c91ee))

* chore: merge main into develop (5 year license period) ([`29c333a`](https://github.com/ERPlora/hub/commit/29c333a903d4ce83d0c9150061887c5b919bafe1))

* chore: update BUSL license period from 4 to 5 years

- Change Date: 2030-01-07 (5 years)
- Provides longer competitive advantage protection
- Each version protected for 5 years before converting to Apache 2.0 ([`2c8d73f`](https://github.com/ERPlora/hub/commit/2c8d73fe673c3f5aed43ec31ac6c3bbe28afd0c5))

* chore: trigger release 0.8.0 ([`65bb386`](https://github.com/ERPlora/hub/commit/65bb3863b4e7e7552f09bd4fce2718e370c3424d))
