# Changelog

## [0.12.4](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.12.3...v0.12.4) (2026-11-10)


### Bug Fixes

* read the launchd pid without an early-exiting reader under pipefail ([83aab4c](https://github.com/thewoolleyman/livespec-driver-codex/commit/83aab4c95c0b59692c52b1f61b773736082ffa2e))

## [0.12.3](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.12.2...v0.12.3) (2026-11-10)


### Bug Fixes

* **tests:** witness that a bare --cov run combines branch and statement data ([8e1c2e1](https://github.com/thewoolleyman/livespec-driver-codex/commit/8e1c2e104c3ece1789bf59a528dc2b6b46896faa))

## [0.12.2](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.12.1...v0.12.2) (2026-11-07)


### Bug Fixes

* exclude Codex-curated plugin caches ([210a43a](https://github.com/thewoolleyman/livespec-driver-codex/commit/210a43aebcac18a62fac508c08476c248fc3a0cc))
* report retained Codex cache aliases ([32b2f47](https://github.com/thewoolleyman/livespec-driver-codex/commit/32b2f4727445d0ecc19f4dbb507008f20477e10b))

## [0.12.1](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.12.0...v0.12.1) (2026-11-04)


### Bug Fixes

* require observer restart after clean exits ([592b6f1](https://github.com/thewoolleyman/livespec-driver-codex/commit/592b6f117a1aad1605504dadc02a09635fbbff4d))

## [0.12.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.11.5...v0.12.0) (2026-11-04)


### Features

* verify released hook bytes before trusting ([46e20f3](https://github.com/thewoolleyman/livespec-driver-codex/commit/46e20f3078001fe2b3914feb81b7370c678ae06a))


### Bug Fixes

* bound release verification and state the trust repair latency ([c5fe451](https://github.com/thewoolleyman/livespec-driver-codex/commit/c5fe45175ef91a2f22904cb7e6270753a2759464))
* fingerprint payload files so same-version rewrites are observed ([8578571](https://github.com/thewoolleyman/livespec-driver-codex/commit/8578571b64c03ef2e021bd206260bb2376efe474))
* reject fields under unkeyed Codex hook state ([a5c067f](https://github.com/thewoolleyman/livespec-driver-codex/commit/a5c067f6bcf4f5eb0a16f9c89a60db4c00d945df))
* repair aliases before release lookup and fetch the release only when trust is stale ([be41e6f](https://github.com/thewoolleyman/livespec-driver-codex/commit/be41e6fcc8c5fe4c4c63717bfa2e22d120ef371b))
* replace stale Codex hook trust records ([e1341eb](https://github.com/thewoolleyman/livespec-driver-codex/commit/e1341eb021c8e06216d30e6776b1f2ecf0539f0f))
* restore hook trust for plugins with no versioned hook entrypoint ([943fc36](https://github.com/thewoolleyman/livespec-driver-codex/commit/943fc3629a38890b991026effd40e8866b9e85c4))
* retain trust only for current verified hooks ([ae7fa8e](https://github.com/thewoolleyman/livespec-driver-codex/commit/ae7fa8e6d4948e772738ec368f0839f5e1c49761))
* serialize and atomically replace Codex config.toml writes ([9430249](https://github.com/thewoolleyman/livespec-driver-codex/commit/9430249c48d5f56fec134140862252b1d46f1ad7))


### Refactoring

* split hook cache alias state ([4bd5c0e](https://github.com/thewoolleyman/livespec-driver-codex/commit/4bd5c0e9cfbf5e2f14e2a0ba1b20231c25eb9547))

## [0.11.5](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.11.4...v0.11.5) (2026-11-03)


### Bug Fixes

* **hooks:** scope supervisor completion to the owning session (livespec-driver-codex-waq5mp) ([f8862c1](https://github.com/thewoolleyman/livespec-driver-codex/commit/f8862c1bf9c460af8c7c4cb901e5e48c280ce32f))

## [0.11.4](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.11.3...v0.11.4) (2026-11-03)


### Bug Fixes

* cover unmanaged inline hook aliases ([ea7cf0d](https://github.com/thewoolleyman/livespec-driver-codex/commit/ea7cf0d286446af39127ef5f289e49582178ac57))
* keep hook cache reconciler under LLOC limit ([7fd2933](https://github.com/thewoolleyman/livespec-driver-codex/commit/7fd2933a93f49d98285a203948b9e94789253068))

## [0.11.3](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.11.2...v0.11.3) (2026-11-03)


### Bug Fixes

* cover wrapped inline Codex hooks ([44b7f44](https://github.com/thewoolleyman/livespec-driver-codex/commit/44b7f44b8e1b0f90cc41a47bb44cd3623712f447))
* report inline non-command hook declarations ([814595b](https://github.com/thewoolleyman/livespec-driver-codex/commit/814595ba685f08a23c273f646388d0c5e2508c9b))

## [0.11.2](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.11.1...v0.11.2) (2026-11-03)


### Bug Fixes

* compare wall-clock observer records ([923cb9d](https://github.com/thewoolleyman/livespec-driver-codex/commit/923cb9d7be04847efdad8a70f3f47e1b5dbb0653))
* mark observer exports explicitly ([6328f08](https://github.com/thewoolleyman/livespec-driver-codex/commit/6328f081060996ca316be643d52692ac2bcb0993))
* prefer a newer provisioner reconcile ([6c2d284](https://github.com/thewoolleyman/livespec-driver-codex/commit/6c2d2840bd29ab58632dc8c9068df11a05517b90))
* record observer reconcile completion time ([e71a146](https://github.com/thewoolleyman/livespec-driver-codex/commit/e71a146113f7ac09e1259ed311ac0dfbb9989907))
* reject unusable observer completion times ([58bfaf4](https://github.com/thewoolleyman/livespec-driver-codex/commit/58bfaf42e50e141599b64144a58dde2e26c9801d))
* report unsupervised Linux observer ([74ea9e1](https://github.com/thewoolleyman/livespec-driver-codex/commit/74ea9e12bbcd7f24393c4e19b516818f1dfb466e))
* restore explicit observer export list and split health reporting out ([70fd15d](https://github.com/thewoolleyman/livespec-driver-codex/commit/70fd15dc63f4b6e8586159615c7aee8e6f1feadd))
* retain formatter-compatible observer export list ([2c3564c](https://github.com/thewoolleyman/livespec-driver-codex/commit/2c3564ccde6be3e5436736fa63c4fc1c59d26062))
* stamp each covered plugin's own reconcile completion time ([f71d4fa](https://github.com/thewoolleyman/livespec-driver-codex/commit/f71d4faca79ba8c9f582733e75099651d0f738d4))

## [0.11.1](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.11.0...v0.11.1) (2026-11-03)


### Bug Fixes

* **tests:** wait for producer exec ([d737039](https://github.com/thewoolleyman/livespec-driver-codex/commit/d73703903a824e1b452a41b0d1d6e3f960416fee))

## [0.11.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.10.1...v0.11.0) (2026-11-03)


### Features

* ship a portable macOS observer LaunchAgent ([0ca7a0e](https://github.com/thewoolleyman/livespec-driver-codex/commit/0ca7a0e7372cc604ebdabcf615fb59502b658da1))


### Bug Fixes

* preserve LaunchAgent interpreter search paths ([e716155](https://github.com/thewoolleyman/livespec-driver-codex/commit/e71615525e654fa62dc254a51fdc97cce7544a68))
* report macOS observer errors without takeover ([0a8da55](https://github.com/thewoolleyman/livespec-driver-codex/commit/0a8da55c66ad23fb02a33f5d79130d0193ff3967))
* require a completed observer reconcile for health ([a4f5191](https://github.com/thewoolleyman/livespec-driver-codex/commit/a4f51913515bd55e3beb351065f6b4491448eade))
* require a running macOS LaunchAgent observer ([7beb294](https://github.com/thewoolleyman/livespec-driver-codex/commit/7beb294121f5f4ff15f5c05127af8f25ec729bbe))

## [0.10.1](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.10.0...v0.10.1) (2026-11-03)


### Bug Fixes

* reject missing manifest-declared hooks file ([2f57ce9](https://github.com/thewoolleyman/livespec-driver-codex/commit/2f57ce906a6d6ab158e00645a337f49ad0811e5b))

## [0.10.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.9.0...v0.10.0) (2026-11-03)


### Features

* avoid busy all-plugin observer polling ([08f3729](https://github.com/thewoolleyman/livespec-driver-codex/commit/08f3729be6bcc59ed3fa45584280a3a1bfe64314))
* cover all registered hook cache plugins ([7411da8](https://github.com/thewoolleyman/livespec-driver-codex/commit/7411da81ae4a26131e99a76d20416ccead5ebfd8))
* isolate hook cache plugin failures ([49612da](https://github.com/thewoolleyman/livespec-driver-codex/commit/49612da6d58f3fe6fbd7c8c074ab4e4e2a05c8c4))
* supervise the hook cache observer ([00ba0e4](https://github.com/thewoolleyman/livespec-driver-codex/commit/00ba0e47032ea2416d5989d172ee62e6f2755964))


### Bug Fixes

* isolate codex hook cache observer state ([420effb](https://github.com/thewoolleyman/livespec-driver-codex/commit/420effb0d632767e82b1180d04740dc1cb8aee70))

## [0.9.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.8.4...v0.9.0) (2026-11-02)


### Features

* delegate the pre-commit aggregate ([4d5f5b7](https://github.com/thewoolleyman/livespec-driver-codex/commit/4d5f5b784b2a9effc7b09ada8cb5bdebe6c8461d))
* enable delegated pre-commit ([ec3ef02](https://github.com/thewoolleyman/livespec-driver-codex/commit/ec3ef0289556770bdd9bf0939276d7101a832619))

## [0.8.4](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.8.3...v0.8.4) (2026-10-30)


### Bug Fixes

* **release:** release the delegated-revise wording fix as v0.8.4 ([bccfba7](https://github.com/thewoolleyman/livespec-driver-codex/commit/bccfba790f94db7fdbcd337ca1d7276e4c7dce56))

## [0.8.3](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.8.2...v0.8.3) (2026-10-25)


### Bug Fixes

* **config:** declare claude-sonnet-5-5 in the model catalog for the Codex-first fallbacks ([415b20f](https://github.com/thewoolleyman/livespec-driver-codex/commit/415b20faf4772f92a3205bd6a95a06ec0c33ab4c))

## [0.8.2](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.8.1...v0.8.2) (2026-10-23)


### Bug Fixes

* **hooks:** auto-memory guard refuses a &gt;| clobber redirect ([c5a9935](https://github.com/thewoolleyman/livespec-driver-codex/commit/c5a9935697f88e742c66460dff01223c4fc55c35))
* **hooks:** auto-memory guard refuses a here-document-fed interpreter write ([e25bd03](https://github.com/thewoolleyman/livespec-driver-codex/commit/e25bd03ef3012ba6be348d0e67afc163e6a631f1))

## [0.8.1](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.8.0...v0.8.1) (2026-10-18)


### Bug Fixes

* **hooks:** refuse shell writes into an agent memory directory (livespec-driver-codex-qi5gkw) ([dbdc0fc](https://github.com/thewoolleyman/livespec-driver-codex/commit/dbdc0fc06c1c4219b3c93ce604c07e90bb638cab))

## [0.8.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.7.6...v0.8.0) (2026-09-30)


### Features

* **hooks:** intercept a raw bd create with a PreToolUse deny ([97e9026](https://github.com/thewoolleyman/livespec-driver-codex/commit/97e9026cb25fa01ead8fba35c96c3ba985768ad3))
* **hooks:** route the denied bd create to capture-work-item ([16afff4](https://github.com/thewoolleyman/livespec-driver-codex/commit/16afff4bb73cfedc4686d7225b24779884f977c9))
* **hooks:** tokenize the command so quoted bd create data passes through ([cede7a9](https://github.com/thewoolleyman/livespec-driver-codex/commit/cede7a907299ffe6f3a61718e36c64ff681fa242))

## [0.7.6](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.7.5...v0.7.6) (2026-09-30)


### Bug Fixes

* **dispatcher:** declare prepare_toolchain.mise so sandbox setup trusts .mise.toml (livespec-driver-codex-26mutz) ([d90fc12](https://github.com/thewoolleyman/livespec-driver-codex/commit/d90fc12f813c1bc5bec2df89bb3baa0e1584d66c))

## [0.7.5](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.7.4...v0.7.5) (2026-09-10)


### Bug Fixes

* declare canonical git author policy ([d0f4119](https://github.com/thewoolleyman/livespec-driver-codex/commit/d0f4119436f4b37dc79b5854a01706e564b08ee9))

## [0.7.4](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.7.3...v0.7.4) (2026-08-29)


### Bug Fixes

* emit Codex-compatible Stop hook block payload ([aeec5f2](https://github.com/thewoolleyman/livespec-driver-codex/commit/aeec5f20feeca1ba02fa81787cb97ce3dd8d7bef))

## [0.7.3](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.7.2...v0.7.3) (2026-08-23)


### Bug Fixes

* **hooks:** stop laundering a failed git probe into "not a primary checkout" ([eac27c4](https://github.com/thewoolleyman/livespec-driver-codex/commit/eac27c42119b1c0cff79cde25a2dab6c2ef5e439))

## [0.7.2](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.7.1...v0.7.2) (2026-08-20)


### Bug Fixes

* **skill:** carry --only-topic in the revise invocation forms ([2122fc9](https://github.com/thewoolleyman/livespec-driver-codex/commit/2122fc96af7770dd39ff44f3253acc69aea9e63d))

## [0.7.1](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.7.0...v0.7.1) (2026-08-17)


### Bug Fixes

* **check:** coverage dedup hardening — clean-env producer + consume-once consumer ([e36fd5e](https://github.com/thewoolleyman/livespec-driver-codex/commit/e36fd5e33d522486a82a3c05a9837329f69681d4))

## [0.7.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.6.1...v0.7.0) (2026-08-14)


### Features

* cover supervisor completion Stop gate ([116558a](https://github.com/thewoolleyman/livespec-driver-codex/commit/116558a5562703a439edca5ef1f57c8c21d598d7))
* **dev-tooling:** reconcile the Codex hook cache across Driver upgrades ([6161209](https://github.com/thewoolleyman/livespec-driver-codex/commit/6161209d40f65adc0da65cd1daad8663ad9fbc25))

## [0.6.1](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.6.0...v0.6.1) (2026-08-14)


### Bug Fixes

* allow literal runtime log variables in primary guard ([1ce82ef](https://github.com/thewoolleyman/livespec-driver-codex/commit/1ce82efa90d9bba4d05d7d81df571164f4e6dc6e))

## [0.6.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.11...v0.6.0) (2026-08-13)


### Features

* allow supervisor runtime state in primary checkout ([0129b05](https://github.com/thewoolleyman/livespec-driver-codex/commit/0129b0539c9062c474dc3d3a05259f538c76bb66))

## [0.5.11](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.10...v0.5.11) (2026-08-13)


### Bug Fixes

* **ci:** unshallow self-hosted checkout so origin/master..HEAD ranges resolve ([af36f13](https://github.com/thewoolleyman/livespec-driver-codex/commit/af36f131136ae75df00a37f380864b840a321c0a))

## [0.5.10](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.9...v0.5.10) (2026-08-13)


### Bug Fixes

* **ci:** add MISE_HTTP_RETRIES alongside UV_HTTP_RETRIES ([f7efedc](https://github.com/thewoolleyman/livespec-driver-codex/commit/f7efedc586f16d00d5cbb5c240217d1a2c9c7123))

## [0.5.9](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.8...v0.5.9) (2026-08-05)


### Bug Fixes

* make per-file coverage self-contained ([9874dfe](https://github.com/thewoolleyman/livespec-driver-codex/commit/9874dfe0bd96afaabfe34674d90a5f430164585d))

## [0.5.8](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.7...v0.5.8) (2026-07-26)


### Bug Fixes

* **config:** describe the current role-key regime, not the retired fallback ([1cdc1f9](https://github.com/thewoolleyman/livespec-driver-codex/commit/1cdc1f91cbadf7ab24c3c9ac811e9b96e07194b9))

## [0.5.7](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.6...v0.5.7) (2026-07-24)


### Bug Fixes

* restore hook lint backstop ([3c26389](https://github.com/thewoolleyman/livespec-driver-codex/commit/3c26389f61a5844b71c7c65a0003da56802c7623))

## [0.5.6](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.5...v0.5.6) (2026-07-24)


### Bug Fixes

* route growing jq inputs to stdin in the CI telemetry export ([6b8e5cf](https://github.com/thewoolleyman/livespec-driver-codex/commit/6b8e5cf609718596771ea225729b75490356af7f))

## [0.5.5](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.4...v0.5.5) (2026-07-23)


### Bug Fixes

* pin no-shadow-ledger body byte-identity to the packaged canonical ([dd1b5e6](https://github.com/thewoolleyman/livespec-driver-codex/commit/dd1b5e6a160a39f0823a47f903a6ba4b9df364eb))

## [0.5.4](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.3...v0.5.4) (2026-07-19)


### Bug Fixes

* **hooks:** scan every token position for a tmux command head ([77850af](https://github.com/thewoolleyman/livespec-driver-codex/commit/77850af037ae12136020d5292919cabd774ea1e7))

## [0.5.3](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.2...v0.5.3) (2026-07-19)


### Bug Fixes

* **hooks:** close demonstrated tmux fleet-kill guard bypasses ([8e56c59](https://github.com/thewoolleyman/livespec-driver-codex/commit/8e56c59f4f4ffa67f4102c00ee2760ea83221c21))

## [0.5.2](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.1...v0.5.2) (2026-07-19)


### Bug Fixes

* narrow footgun primary checkout probe failures ([cc017ee](https://github.com/thewoolleyman/livespec-driver-codex/commit/cc017ee966c023619dc666dafc90c1f98705e43e))

## [0.5.1](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.5.0...v0.5.1) (2026-07-19)


### Bug Fixes

* make shipped Codex hooks self-contained under the install layout ([7979da2](https://github.com/thewoolleyman/livespec-driver-codex/commit/7979da209cae7fc07c7b719ac0679b5846d01a1c))

## [0.5.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.4.0...v0.5.0) (2026-07-19)


### Features

* require hook railway policy ([3dc8174](https://github.com/thewoolleyman/livespec-driver-codex/commit/3dc81746a5fa8de771c3492d74950224b0318a3b))


### Bug Fixes

* put no-shadow hook on railway ([46b6524](https://github.com/thewoolleyman/livespec-driver-codex/commit/46b6524a36d1ba6204eed5425b9f5aa7face4915))


### Reverts

* keep no-shadow hook canonical ([8225656](https://github.com/thewoolleyman/livespec-driver-codex/commit/8225656e8b5f079817b1212cbc7fd46325765891))

## [0.4.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.3.4...v0.4.0) (2026-07-19)


### Features

* cover codex tmux default socket guard ([10452d4](https://github.com/thewoolleyman/livespec-driver-codex/commit/10452d4389c5fa47451fcd75e114c123e48051e2))

## [0.3.4](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.3.3...v0.3.4) (2026-07-13)


### Bug Fixes

* make Codex hook bodies importable ([9d7a78d](https://github.com/thewoolleyman/livespec-driver-codex/commit/9d7a78d85d805dee9ead5151ca3e04f925d08adc))

## [0.3.3](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.3.2...v0.3.3) (2026-07-12)


### Refactoring

* **hooks:** decompose footgun guard into cohesive modules; arm file_lloc hard gate ([d23c065](https://github.com/thewoolleyman/livespec-driver-codex/commit/d23c06540ff57f694915f378b16c0ff06de0839d))

## [0.3.2](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.3.1...v0.3.2) (2026-07-12)


### Refactoring

* **hooks:** make footgun guard structurally coverage-clean ([5e86a8a](https://github.com/thewoolleyman/livespec-driver-codex/commit/5e86a8aaa3e37b2a0136fa92cb2bd4534bd46e79))

## [0.3.1](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.3.0...v0.3.1) (2026-07-03)


### Bug Fixes

* cover fd duplication redirections in footgun guard ([28f39ad](https://github.com/thewoolleyman/livespec-driver-codex/commit/28f39ad8c442abb8aa896eed8921b062ab1bace4))

## [0.3.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.2.0...v0.3.0) (2026-07-01)


### Features

* **hooks:** apply_patch coverage for Codex auto-memory guard (co9h) ([65db189](https://github.com/thewoolleyman/livespec-driver-codex/commit/65db189918cea63ab26c0e76eaec6a9e0327bd2b))
* **hooks:** Codex auto-memory-write guard (co9h) ([beadcfa](https://github.com/thewoolleyman/livespec-driver-codex/commit/beadcfa7a29150925f26626b3436c7a7cf01c1cf))


### Bug Fixes

* point plugin-structure recipe at driver_checks + bump dt pin to v0.25.1 (livespec-2exa) ([4500b33](https://github.com/thewoolleyman/livespec-driver-codex/commit/4500b336002b3692cd88d4f4194938de9f69764b))


### Refactoring

* consume check_plugin_structure from the livespec-dev-tooling package; drop vendored copy (zs22.7.9.2) ([7a8efe0](https://github.com/thewoolleyman/livespec-driver-codex/commit/7a8efe0af0e7f29f5adbfbb44f8176a8e0554784))

## [0.2.0](https://github.com/thewoolleyman/livespec-driver-codex/compare/v0.1.0...v0.2.0) (2026-06-25)


### Features

* bootstrap livespec-driver-codex — Codex Driver plugin + family infra ([948f904](https://github.com/thewoolleyman/livespec-driver-codex/commit/948f904f917ef18c9f8e2c7054e88a5baa0c030e))


### Bug Fixes

* make footgun-guard primary-checkout tests hermetic (CI-portable) ([976eae3](https://github.com/thewoolleyman/livespec-driver-codex/commit/976eae327674838c9f906ba1bae2d09ba0410901))

## Changelog

All notable changes to this plugin are recorded here. This file is
auto-maintained by release-please; do not edit it by hand.
