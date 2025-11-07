# CHANGELOG


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

CI/CD: Updated GitHub Actions workflow to build native installers ([`3f3d05e`](https://github.com/cpos-app/hub/commit/3f3d05e08b02d95e989c8a314f778fa1787b7b5d))

### Unknown

* chore: add GPG public key for release verification ([`24f58ce`](https://github.com/cpos-app/hub/commit/24f58ceaae2eff1fef9fe72d21ccd5af4dfb1db6))


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
- Supports Windows, macOS, and Linux artifacts ([`73e7038`](https://github.com/cpos-app/hub/commit/73e70387edaa101558a7e8b5bbf317d20a955737))

### Unknown

* chore: update BUSL license period from 4 to 5 years

- Change Date: 2030-01-07 (5 years)
- Provides longer competitive advantage protection
- Each version protected for 5 years before converting to Apache 2.0 ([`ad209f7`](https://github.com/cpos-app/hub/commit/ad209f779b1ccd9ec9a02bb589a32444acd10d12))


## v0.9.0 (2025-11-07)

### Features

* feat: add BUSL-1.1 license to protect against competitive clones

- Add Business Source License 1.1
- Allows free use for businesses and individuals
- Prohibits creating competing POS services
- Converts to Apache 2.0 in 2029
- Update pyproject.toml with license info
- Add license documentation to README ([`9a2463f`](https://github.com/cpos-app/hub/commit/9a2463f1ec8dfebd2ea262f9c8604ef408234206))


## v0.8.1 (2025-11-07)

### Bug Fixes

* fix: remove emojis for Windows cp1252 compatibility ([`17dc46d`](https://github.com/cpos-app/hub/commit/17dc46d7d7b7346f4177da0caece192f0b616c8e))


## v0.8.0 (2025-11-07)

### Bug Fixes

* fix: finalize release 0.8.0 ([`62a0053`](https://github.com/cpos-app/hub/commit/62a0053e3676e408d8791e71b7b0a4ac2bec46be))

### Unknown

* chore: trigger release 0.8.0 ([`a63e399`](https://github.com/cpos-app/hub/commit/a63e399b36fb84b6cd9f0a06ada75141b8a69021))


## v0.8.0-rc.4 (2025-11-06)

### Features

* feat: build wip ([`a3a57c3`](https://github.com/cpos-app/hub/commit/a3a57c3a93b7f3b18068140ba2d66e4636274748))


## v0.8.0-rc.3 (2025-11-06)

### Features

* feat: build wip ([`a4438df`](https://github.com/cpos-app/hub/commit/a4438df519b6965693afc1f9ef1502ffcb076236))


## v0.8.0-rc.2 (2025-11-06)

### Features

* feat: build wip ([`3d49477`](https://github.com/cpos-app/hub/commit/3d494770d199a4750345d64626c9c6b1613fb158))


## v0.8.0-rc.1 (2025-11-06)

### Features

* feat: build wip ([`8964bcc`](https://github.com/cpos-app/hub/commit/8964bcc7042367b246230ce7049a77523781428a))

* feat: build wip ([`c20364f`](https://github.com/cpos-app/hub/commit/c20364f8c298df99c7e3d1eec14f55e94e5af7fa))

* feat: build wip ([`7aefb0a`](https://github.com/cpos-app/hub/commit/7aefb0ad9a802e003a253840ebcb348ee66c0133))

* feat: add 25 library to app ([`b2ce44b`](https://github.com/cpos-app/hub/commit/b2ce44b5f141b286c578399b688a426254e180e2))

* feat: build local ok ([`f32a560`](https://github.com/cpos-app/hub/commit/f32a5604795df38be9c0be9fb3749bb7c8916349))

* feat: build local ok ([`a389c1a`](https://github.com/cpos-app/hub/commit/a389c1a11e561f894f17fb521a44aea852ea2c61))

* feat: build local ok ([`18da96f`](https://github.com/cpos-app/hub/commit/18da96fdd0ad2934107d65d9ccee4a1aa744cb7b))

* feat: build action ([`238c888`](https://github.com/cpos-app/hub/commit/238c888be753dbad31f0335cbad33a4ccd0f2d95))

* feat: build action ([`fd7ce5a`](https://github.com/cpos-app/hub/commit/fd7ce5a7f2d1c7545091ab52f4f646d0033ce8c4))


## v0.6.0 (2025-11-05)


## v0.5.0 (2025-11-05)


## v0.6.0-rc.1 (2025-11-05)

### Features

* feat: build action ([`a9e4e05`](https://github.com/cpos-app/hub/commit/a9e4e05d8347daeee07d9a2d6814a02f4ccc6337))


## v0.4.0 (2025-11-05)


## v0.4.0-dev.4 (2025-11-05)

### Features

* feat: build action ([`034824e`](https://github.com/cpos-app/hub/commit/034824e7c886d6233b7e63e1ebef4ca0ba88f50e))


## v0.4.0-dev.3 (2025-11-05)

### Features

* feat: build action ([`80e6a28`](https://github.com/cpos-app/hub/commit/80e6a28d1cfa10a744db2f96c0869ae7633d1fce))


## v0.3.0 (2025-11-05)


## v0.2.0 (2025-11-05)


## v0.4.0-dev.2 (2025-11-05)

### Features

* feat: build action ([`0dcd00a`](https://github.com/cpos-app/hub/commit/0dcd00a2eb7a755412227586c99cd5dc322a761a))


## v0.4.0-dev.1 (2025-11-05)

### Features

* feat: build action ([`4e87524`](https://github.com/cpos-app/hub/commit/4e8752464aaa9e98cfd3fa86bad3d869fb1feeb9))

* feat: build action ([`c040b1e`](https://github.com/cpos-app/hub/commit/c040b1ec6b7450530245812a4ffcf42f726bbdb6))

* feat: build action ([`ca9a05f`](https://github.com/cpos-app/hub/commit/ca9a05ff3fd1a57b1a6af5ef2f76125a7fa09333))


## v0.1.0 (2025-11-05)


## v0.1.0-dev.4 (2025-11-05)

### Features

* feat: build action ([`9f9d0d7`](https://github.com/cpos-app/hub/commit/9f9d0d79104681f7a03bd307b3a896f3b99a0137))


## v0.1.0-dev.3 (2025-11-05)

### Features

* feat: build action ([`6c95f56`](https://github.com/cpos-app/hub/commit/6c95f569e17d1d2d9afc88a0a379e6b876a99be6))


## v0.1.0-dev.2 (2025-11-05)

### Features

* feat: build action ([`5c388ac`](https://github.com/cpos-app/hub/commit/5c388ac22b6640710cef863b32ee3299ec35e559))


## v0.1.0-dev.1 (2025-11-05)

### Features

* feat: build action ([`aac3841`](https://github.com/cpos-app/hub/commit/aac384104b66316931a3ed86bb3a25249d938205))

* feat: uv and python semantic realese ([`b0f6b64`](https://github.com/cpos-app/hub/commit/b0f6b64e2e86d8e7edf87365d96477f0ddbae56b))

* feat: actions and build ([`9df3f77`](https://github.com/cpos-app/hub/commit/9df3f7777834977ad040be4f119180e167f0f4bf))

* feat: remove plugin zip ([`2f7df85`](https://github.com/cpos-app/hub/commit/2f7df85ff8ba92f54d8937586ee06acf2c095454))

* feat: plugin loader ([`7f00c40`](https://github.com/cpos-app/hub/commit/7f00c4066f2a23c7b8678d6e4480be7ed1b4b064))

* feat(core):  theme ([`3533f44`](https://github.com/cpos-app/hub/commit/3533f4480d119e23de6c975aa743b88e9266566a))

* feat(auth):  login and pin ([`7aeac38`](https://github.com/cpos-app/hub/commit/7aeac38b3f7df9aaf0fc8fa8443274b4753987c0))

* feat(base): inital commit ([`4e85690`](https://github.com/cpos-app/hub/commit/4e856909d38098b2848994113d1e5e935fb92be3))
