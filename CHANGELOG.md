# Changelog

## [1.2.0](https://github.com/mylastresort/thingsboard/compare/thingsboard-v1.1.0...thingsboard-v1.2.0) (2026-07-18)


### Features

* **go-toolbox:** update dash with dynamic device handling ([6b7144a](https://github.com/mylastresort/thingsboard/commit/6b7144ab152b5db94b62eab96649175904542d95))
* **pdm:** add model storage service with MinIO and PostgreSQL backends ([2ee9b75](https://github.com/mylastresort/thingsboard/commit/2ee9b755a8f12ba9e23b159f7bd44b25cdfc695b))
* **pdm:** add model storage service with MinIO and PostgreSQL backends ([ec754aa](https://github.com/mylastresort/thingsboard/commit/ec754aac96667b860258410ec395075b9a9b1145))
* **pdm:** parallelize forecast training/inference per sensor ([13a52d5](https://github.com/mylastresort/thingsboard/commit/13a52d5d3a0d0372cc1a4a7e0c92d94360845161))
* **pdm:** per-sensor fan-out, dynamic activation, prediction streaming ([91cb104](https://github.com/mylastresort/thingsboard/commit/91cb1044ca0b6af900ced33d86b2f5783ad4339f))
* **pdm:** Rust native inference engine with Python→ONNX training bridge ([b4a2cc6](https://github.com/mylastresort/thingsboard/commit/b4a2cc688d3eef84b768e70c8c141bf28811b4c3))


### Bug Fixes

* minio ([d957980](https://github.com/mylastresort/thingsboard/commit/d957980efe61336841bb06b218471238e0f0725a))

## [1.1.0](https://github.com/mylastresort/thingsboard/compare/thingsboard-v1.0.0...thingsboard-v1.1.0) (2026-07-18)


### Features

* add cassandra install and up Makefile rules ([d66d832](https://github.com/mylastresort/thingsboard/commit/d66d832ba9e33c5219f0c40ed5fef53e7295090b))
* add scoped ThingsBoard ops agent skills ([13f04ec](https://github.com/mylastresort/thingsboard/commit/13f04ec76eb01884ca0651aaea92b8dbfd66b5e7))
* **ai-agent:** add ADK eval test target and dependencies ([571bbf5](https://github.com/mylastresort/thingsboard/commit/571bbf576f6349f5c6e750f7b86441070a378826))
* **ai-agent:** add Langfuse observability for token tracking and cost monitoring ([1585c40](https://github.com/mylastresort/thingsboard/commit/1585c4096a8d643f7363bb9199e28975a6b75e0a))
* **ai-agent:** add Langfuse observability for token tracking and cost monitoring ([5ed62eb](https://github.com/mylastresort/thingsboard/commit/5ed62eba0fb8ca1b9080b17a15167cb943eec207))
* **ai-agent:** add pdm_agent with seed-train-infer-pdm skill ([ef9ba11](https://github.com/mylastresort/thingsboard/commit/ef9ba11ee887baa04b4e31134f333919333abfee))
* **ai-agent:** Langfuse observability and stateless Redis session persistence ([5d632ff](https://github.com/mylastresort/thingsboard/commit/5d632ffe665b5d4bcaf17e563a7c44398245b91a))
* **ai-agent:** persistent sessions via PostgreSQL ([ab748a6](https://github.com/mylastresort/thingsboard/commit/ab748a652d3bb4833cfafba216e8d191b5e86c67))
* **ai-agent:** persistent sessions via PostgreSQL ([8811ba7](https://github.com/mylastresort/thingsboard/commit/8811ba7f3809c0b3b5da10e29d86accb80de51db)), closes [#17](https://github.com/mylastresort/thingsboard/issues/17)
* **ai-agent:** prefix session schema with ai_agent namespace ([15480a2](https://github.com/mylastresort/thingsboard/commit/15480a2bfc53e2dc38a20e0920aac38d17eb460a))
* **chip-overflow:** optional showOverflowedTitle native tooltip ([8afc94c](https://github.com/mylastresort/thingsboard/commit/8afc94cfc97728cc8b58723511de90980a40d036))
* **html-container:** scoped error handler, action support, completion polish ([b84f58a](https://github.com/mylastresort/thingsboard/commit/b84f58a8af080cc5added74b74bd98dc85571194))
* **html-container:** split-pane settings layout, fullscreen, mode-aware completer ([13ae00a](https://github.com/mylastresort/thingsboard/commit/13ae00a6cde483f4455bd111b72620af37bf109a))
* **html-container:** tabbed settings UI, register widget, fill-height layout ([dc47918](https://github.com/mylastresort/thingsboard/commit/dc479185a4f5f481712f9e360f6b494d7bd68c0f))
* **iot-hub:** add "Add from IoT Hub" action to alarm rules table ([bed6caa](https://github.com/mylastresort/thingsboard/commit/bed6caa8bf9b262a3d639133d2a3ad64a415ddb5))
* **iot-hub:** add PhotoSwipe lightbox for markdown image galleries ([e0be202](https://github.com/mylastresort/thingsboard/commit/e0be2025f6216869caaecad6606efb14d38937ba))
* **iot-hub:** add YouTube link to creator profile ([456ef7e](https://github.com/mylastresort/thingsboard/commit/456ef7e7361dc0ba478437dcad43fdcec705ec84))
* **iot-hub:** empty-state Clear-all-filters and unified type list ([14e1f12](https://github.com/mylastresort/thingsboard/commit/14e1f12a23cdb3ede80138263b183c76443a7c29))
* **iot-hub:** expand markdown gallery, sanitised captions, shared photoswipe ([af9b582](https://github.com/mylastresort/thingsboard/commit/af9b5822a6d553cb6ebc25dbc2a6a724a0408f81))
* **iot-hub:** force markdown links to new tab + verified item-link card ([18232e9](https://github.com/mylastresort/thingsboard/commit/18232e9c8c7acc3ec0e84be93b7b4898b407d295))
* **iot-hub:** gate widget Add-from-IoT-Hub action by tenant, refresh widget JSON ([4a5e708](https://github.com/mylastresort/thingsboard/commit/4a5e708ef160863d6b93ade78a849010162e82b1))
* **iot-hub:** hardening + dao-level lookups ([a880a86](https://github.com/mylastresort/thingsboard/commit/a880a8635a03daef73959b8349301058cb24f9e8))
* **iot-hub:** introduce shared tb-iot-hub-markdown component ([ba8cef1](https://github.com/mylastresort/thingsboard/commit/ba8cef18a09550be0dbfbf570564fac38cfef544))
* **iot-hub:** listing-slug deep links + edition / version gates ([9c1e079](https://github.com/mylastresort/thingsboard/commit/9c1e07968572c2a7070aee9ccebad8b8ee50d73d))
* **iot-hub:** polish connectivity card selected/idle states ([94ceb36](https://github.com/mylastresort/thingsboard/commit/94ceb360cc78687a6137a1b06e05d1909a6f5e18))
* **iot-hub:** redesign device install connectivity selector ([ee22a5b](https://github.com/mylastresort/thingsboard/commit/ee22a5b5646374e5737f91303eef7cab00e79d2f))
* **iot-hub:** redesign home category cards and popular sections ([3dc897a](https://github.com/mylastresort/thingsboard/commit/3dc897a749311dd09059060c708e738c85d26706))
* **iot-hub:** redesign home hero — per-type clusters, glow blobs, scale anim ([7715849](https://github.com/mylastresort/thingsboard/commit/7715849c1cd228d1053cd636044c93a77437df3b))
* **iot-hub:** refresh items-page hero illustrations from design ([e8bf85f](https://github.com/mylastresort/thingsboard/commit/e8bf85fba8244fcca6af036fd62355094a00949e))
* **iot-hub:** set rule chain as default rule chain on profile during install ([ca62471](https://github.com/mylastresort/thingsboard/commit/ca62471d5c2b823dd4cbceead02a28fbc26fb6cf))
* **iot-hub:** set rule chain as Default rule chain on profile during install ([677ff70](https://github.com/mylastresort/thingsboard/commit/677ff70e6f33164faa354e25caf38649fcd24489))
* **iot-hub:** set rule chain as Default rule chain on profile during install (4.3) ([731c513](https://github.com/mylastresort/thingsboard/commit/731c5135abb5f152d68a35ce251d2351661512a1))
* **iot-hub:** show install time in installed-items table createdTime column ([bf3e405](https://github.com/mylastresort/thingsboard/commit/bf3e405ea2c23f2201ce80fc721f9876d9decb3c))
* **iot-hub:** single-step install dialog with rule chain profile toggle ([bb77113](https://github.com/mylastresort/thingsboard/commit/bb7711353d6577c2521581e517ce3325ddf6f990))
* **iot-hub:** single-step install dialog with rule chain profile toggle ([12905cb](https://github.com/mylastresort/thingsboard/commit/12905cb0d270b3d5f87a0d987d633e363b317d4d))
* **iot-hub:** single-step install dialog with rule chain profile toggle (4.3) ([8782083](https://github.com/mylastresort/thingsboard/commit/878208362696e68083271d02d8575aaee54b3cff))
* **iot-hub:** unified network-unavailable error state with debounced retry ([bb47013](https://github.com/mylastresort/thingsboard/commit/bb47013d1b99898b89be284d4487dd5cd9936770))
* **iot-hub:** unify empty/loading state in installed-items table ([bb28862](https://github.com/mylastresort/thingsboard/commit/bb28862df6241e91925ad3daaa5a4b1f6eb1de48))
* **js-executor:** support lz4 compression for Kafka producer ([f1c8147](https://github.com/mylastresort/thingsboard/commit/f1c8147b58d3d276674a4869ffeacb6943007c24))
* **js-executor:** support lz4 compression for Kafka producer ([7040646](https://github.com/mylastresort/thingsboard/commit/704064615a42617e61e10a468cbabf31c10f7260))
* **pdm:** add restart resilience, pause/unpause UI, periodic recovery, and worker disconnect detection ([e60747a](https://github.com/mylastresort/thingsboard/commit/e60747a94dd4371f56ddb28b27b600ddc8e34aa5))
* **pdm:** add train-existing-device skill and rename getAvailableModels to getAvailableAlgorithms ([f073a77](https://github.com/mylastresort/thingsboard/commit/f073a77a6b4e572e29d7c87d0dee74347b65565f))
* **pdm:** add unified WebSocket, Kafka event consumer, and Redis job state service ([bf83486](https://github.com/mylastresort/thingsboard/commit/bf834865b830dbb7a10ce8f8fee10eccc8544794))
* **pdm:** route workers through API clients and enhance UI ([6ec8b28](https://github.com/mylastresort/thingsboard/commit/6ec8b28806762553635dc13e396576b83035658c))
* **shared:** add AutocompleteAutoScrollRepositionDirective ([cab7c51](https://github.com/mylastresort/thingsboard/commit/cab7c5102769854b388147d39fcc99a82d816844))
* support JSON Schema structured output across AI providers ([ba7fbff](https://github.com/mylastresort/thingsboard/commit/ba7fbfffc15e19cbb76ff68170ee5effb3ca4337))
* **widget-select:** add icons to top-level Installed / IoT Hub toggle ([382de37](https://github.com/mylastresort/thingsboard/commit/382de37b16864e7b24ee70c132a786186a0ee115))
* wire up frequency and presence penalties for Gemini models ([ba40d61](https://github.com/mylastresort/thingsboard/commit/ba40d6135ce24a71acdb2e063e6ef77b1f6c2954))
* **worktree:** git worktree workflow for isolated PR testing ([51ad9da](https://github.com/mylastresort/thingsboard/commit/51ad9da184300cf23a8b5daeb6fc7754d483487b))
* **worktree:** git worktree workflow for isolated PR testing ([dd4bdec](https://github.com/mylastresort/thingsboard/commit/dd4bdec37b4c34f9c83c84ace7d52e2a786ebdd8))


### Bug Fixes

* **ai-agent:** align PdM tool ids with Quarkus MCP and add CI tests ([f056219](https://github.com/mylastresort/thingsboard/commit/f056219c4e3f2a1f8a88edf46f31a4751fba659a))
* **ai-agent:** build issue ([688ec84](https://github.com/mylastresort/thingsboard/commit/688ec844e5eaa4ea97df6e929eac416f603e64c4))
* anomaly notification show on page reload ([6ec8b28](https://github.com/mylastresort/thingsboard/commit/6ec8b28806762553635dc13e396576b83035658c))
* apply queue prefix when creating Kafka topics to prevent orphaned topics ([42a14ec](https://github.com/mylastresort/thingsboard/commit/42a14ec18ca229c41668a52d93c77d10ac6d2355))
* apply queue prefix when creating Kafka topics to prevent orphaned topics ([55307c1](https://github.com/mylastresort/thingsboard/commit/55307c1e1de80dfcc4fd94d81abb42cfef133d66))
* cancel stale duration check future on alarm rule REINIT ([38eeb28](https://github.com/mylastresort/thingsboard/commit/38eeb28e48e133e80781884c688abfd7b8b9a814))
* **cf:** prevent integer overflow in calculated field SUM output ([3aacc66](https://github.com/mylastresort/thingsboard/commit/3aacc6607463349a0bb287c2b7d85dd201c770d0))
* **cf:** prevent integer overflow in calculated field SUM output ([6f75542](https://github.com/mylastresort/thingsboard/commit/6f7554231515d2554ac8ca96f2ed8ca5113b6658))
* **cf:** prevent integer overflow in calculated field SUM output (lts-4.3) ([0c027bb](https://github.com/mylastresort/thingsboard/commit/0c027bbce707c9d68856dfc1827d30b75940b747))
* **csv:** assign result of replace in splitCSV else branch ([af659f3](https://github.com/mylastresort/thingsboard/commit/af659f36c055cdaaeba326b251ee9687608710d4))
* docker compose volume on docker-compose up ([7c46e98](https://github.com/mylastresort/thingsboard/commit/7c46e98be5dcef736cc2962721923de825b13a99))
* **home:** reset main-content scroll on route navigation so pages open at the top ([304904c](https://github.com/mylastresort/thingsboard/commit/304904cedb8ca006f8a06fe50880af5d9bed25cd))
* **iot-hub:** alarm rule prompt + open-detail route on install success ([f9ba909](https://github.com/mylastresort/thingsboard/commit/f9ba9098fd1946e0bfa8dc699af736c43f044537))
* **iot-hub:** append /preview suffix on card image URL when missing ([7002697](https://github.com/mylastresort/thingsboard/commit/7002697f69b989b5ae9ede5178c01572d66bc354))
* **iot-hub:** compensate orphaned entities when installed-item tracking save fails ([77c74d7](https://github.com/mylastresort/thingsboard/commit/77c74d7ccd70db15089dbbdf56c2d31ced76b54c))
* **iot-hub:** include webp in device package image extensions ([3053341](https://github.com/mylastresort/thingsboard/commit/30533414ae85c273b3a9ec9e563c0836e72482b9))
* **iot-hub:** include webp in device package image extensions ([d74496b](https://github.com/mylastresort/thingsboard/commit/d74496b44a1243b0e9fe0ff85c2efe76100a3138))
* **iot-hub:** let active-filters row grow when chips wrap so card grid doesn't overlap ([0db943f](https://github.com/mylastresort/thingsboard/commit/0db943f4422e6f65546c1b2a09c5715769067b3c))
* **iot-hub:** mobile detail-dialog stacks preview+description, hero shrinks on lt-sm, device install URL falls back to first created device ([78cfbf4](https://github.com/mylastresort/thingsboard/commit/78cfbf4b32e9ecf0660ac217c75dd8f4c6fb5953))
* **iot-hub:** polish rule chain install dialog layout and copy ([af1b888](https://github.com/mylastresort/thingsboard/commit/af1b888cf01a6b563fb9c100d230cb834be19270))
* **iot-hub:** preserve typed search text when picking an autocomplete result ([c7153a5](https://github.com/mylastresort/thingsboard/commit/c7153a5f567cdaab79134e5ca0d1fff32cbea2bb))
* **iot-hub:** resolve DEVICE installed-item url to its dashboard ([f8f7e00](https://github.com/mylastresort/thingsboard/commit/f8f7e00cce4a934cf333d38d9d625eba915b6d14))
* **iot-hub:** restrict installed-items list sort property to a server-side allow-list ([5fa837f](https://github.com/mylastresort/thingsboard/commit/5fa837fb0309a939a4b80925183fbee0486c5e1d))
* **iot-hub:** show connection-method selector step even when a single method is available ([a4e4f56](https://github.com/mylastresort/thingsboard/commit/a4e4f5615863f544acaf008fc0993f2b56574ebc))
* **iot-hub:** skip already-installed check for non-widget/solution-template root entries ([8cbac06](https://github.com/mylastresort/thingsboard/commit/8cbac06ffc7b1e7ef133e63f9420586462487226))
* **iot-hub:** surface dashboard save errors during device-package install/overwrite ([a8846fa](https://github.com/mylastresort/thingsboard/commit/a8846fad62cb8116137863a68b83d99a7b7ce013))
* **iot-hub:** tighten delete/update result handling and switch button spinners/icons to matButtonIcon ([f5a1052](https://github.com/mylastresort/thingsboard/commit/f5a1052a480f612e98fe6cde204e02e9fc1329c2))
* old forecast datapoints appear on new telemetry data ([9226caa](https://github.com/mylastresort/thingsboard/commit/9226caa47b23a90a94aa4716cabdd4889ffe76f0))
* pdm agent calls ([227a4bb](https://github.com/mylastresort/thingsboard/commit/227a4bb2983dccb6d7b5332e481b241f18f429bb))
* **solutions:** bound solution-template zip extraction to mitigate zip-bomb attacks ([93b50bd](https://github.com/mylastresort/thingsboard/commit/93b50bdf96eb9647e3b9aaaea171496951660a43))
* **solutions:** clamp solution-template installTimeoutMs to a configurable max ([62c1963](https://github.com/mylastresort/thingsboard/commit/62c1963507f450ad1430a28eafde5d68b34e90be))
* styling ([4404307](https://github.com/mylastresort/thingsboard/commit/44043074fbc761a9a7a7799f5b512d0cd224381a))
* **ui:** dark theme scss styles ([a05131c](https://github.com/mylastresort/thingsboard/commit/a05131c62c6fbedcfe7e2fec1ff15e3aaf73e279))
* **widget-select:** drop xs select fallback on top-level mode toggle ([f00e1d4](https://github.com/mylastresort/thingsboard/commit/f00e1d455884f221af6d2f5773b6aa05aa5ff3aa))


### Documentation

* add database per service rule to AGENTS.md ([a8e0479](https://github.com/mylastresort/thingsboard/commit/a8e0479f8635b2dcc5c03a02b0c035315501af3a))
* add database per service rule to AGENTS.md ([5d83a49](https://github.com/mylastresort/thingsboard/commit/5d83a49e5c035c1befd6565ceb0e9521f83e4354))
* add repository contributor guide ([84dcd2d](https://github.com/mylastresort/thingsboard/commit/84dcd2d2ce9cad9910c29cf723a77c8052b58b9d))
* add version scheme to AGENTS.md ([43122bd](https://github.com/mylastresort/thingsboard/commit/43122bd032aee4446c8fa66b184ac775042d389d))
* add version scheme to AGENTS.md ([4ed6450](https://github.com/mylastresort/thingsboard/commit/4ed6450400981b245c634bb320ca4ec371b9dfd8))


### Miscellaneous

* add lazydocker conf ([ae7c061](https://github.com/mylastresort/thingsboard/commit/ae7c061e96c0b1e18ec036e233c767a38914a46a))
* empty commit to make a draft PR ([86b196d](https://github.com/mylastresort/thingsboard/commit/86b196dacf2688ae25c094dae7cd03727d313e31))
* **iot-hub:** drop now-unused filter import from IotHubActionsService ([d3bc589](https://github.com/mylastresort/thingsboard/commit/d3bc589a510b995fbcaa8ae635974ec4915ba84e))
* **iot-hub:** drop unused IotHubApiService dependency from IotHubActionsService ([48e70f9](https://github.com/mylastresort/thingsboard/commit/48e70f9b0ddd83b7e34dca930ba6609cee65f061))
* **iot-hub:** swap "Add from IoT Hub" action icon from store to hub ([f4aaeff](https://github.com/mylastresort/thingsboard/commit/f4aaeff6d9790ea2dae2042e280081cd77577b22))
* picking more better model for reasoning ([abd551d](https://github.com/mylastresort/thingsboard/commit/abd551d38b81e5bf31d3687552f146f2c98e9e45))
* update favicon ([fd55111](https://github.com/mylastresort/thingsboard/commit/fd551110ef454eb6e470fc0de3fd529678d84e76))
