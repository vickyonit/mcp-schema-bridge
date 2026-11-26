# Changelog

## [0.1.0](https://github.com/vickyonit/mcp-schema-bridge/compare/v0.0.1...v0.1.0) (2026-11-26)


### Features

* add argument round-trip (denormalize_args) and root wrapping (T14) ([a0a4cdd](https://github.com/vickyonit/mcp-schema-bridge/commit/a0a4cdd093043e8f8a05ce42cd55ad0127e82b29))
* add normalize_schema skeleton with options, fingerprint, report and emission ([4ea1d12](https://github.com/vickyonit/mcp-schema-bridge/commit/4ea1d1292af6d1a5ae8410b4b19f5fac4a15b14d))
* add normalize_tools with name checks, per-request budgets and strict fallback (T17, T18) ([ac8c715](https://github.com/vickyonit/mcp-schema-bridge/commit/ac8c715067e8e35e795557a24f456d4632a8a5a1))
* add opt-in argument repairs and round-trip/totality properties ([25420ef](https://github.com/vickyonit/mcp-schema-bridge/commit/25420ef85733347fdd6e4f8a82805da469929666))
* add SDK payload adapters (to_sdk_payload) ([d55546e](https://github.com/vickyonit/mcp-schema-bridge/commit/d55546ebaa526aa0dfa2c7a798a4105902cef103))
* add ToolsetResult.get() and .summary() (Python and TypeScript) ([115d670](https://github.com/vickyonit/mcp-schema-bridge/commit/115d67080cd0dda109b80038e471bdcc9ed52632))
* **cli:** add 'proxy' to serve any MCP server's tools normalized for a target ([ee37c36](https://github.com/vickyonit/mcp-schema-bridge/commit/ee37c366d8aaa6129d1f7c29aa63c729b79d29c4))
* **cli:** add check and normalize commands ([0d92b29](https://github.com/vickyonit/mcp-schema-bridge/commit/0d92b29f30ba4684c235ab53607a00c29e7950cb))
* **core:** add error hierarchy and strict I-JSON input parsing (S0) ([2925149](https://github.com/vickyonit/mcp-schema-bridge/commit/2925149ff8b940fbc63798ef01423baf815aa55c))
* **core:** add lossiness report model with total deterministic ordering ([30c3de9](https://github.com/vickyonit/mcp-schema-bridge/commit/30c3de9df77989cd97b36fd29a4c94d1050f530a))
* **core:** add provenance-tracking schema tree with position-aware walking ([13b39a9](https://github.com/vickyonit/mcp-schema-bridge/commit/13b39a950c31ed7f7349aba856c59e385855112b))
* **core:** add RFC 6901 JSON Pointer helpers ([e6612b8](https://github.com/vickyonit/mcp-schema-bridge/commit/e6612b885be0e029a2841eb250412a3443e1fd11))
* **core:** add RFC 8785 JSON canonicalization encoder ([fdb127a](https://github.com/vickyonit/mcp-schema-bridge/commit/fdb127a490b5577e24e7b77a93531b85dfa2eaf9))
* **core:** add syntactic regex feature scanner with shared vectors (T16) ([10780a9](https://github.com/vickyonit/mcp-schema-bridge/commit/10780a95498a86d76ce91d060ab8cb330b775b36))
* **core:** analyse recursion and inline references (S4, T2a, T2b) ([39bdb62](https://github.com/vickyonit/mcp-schema-bridge/commit/39bdb62709e40774b5ebcb0e43703c9a13ee33e8))
* **core:** canonicalize dialect differences (S2, T3) ([0dc9eff](https://github.com/vickyonit/mcp-schema-bridge/commit/0dc9eff2b93fcff231b6121b09525d817beb040d))
* **core:** close objects on strict targets (S7, T10) ([83bc0bc](https://github.com/vickyonit/mcp-schema-bridge/commit/83bc0bcd0a5161b9cec33ce5dbf1a194c1899517))
* **core:** filter keywords per target (S9: T1, T12, T13, T15, T16) ([18506b3](https://github.com/vickyonit/mcp-schema-bridge/commit/18506b3126f751de19ba365276e17bde50ce9b3d))
* **core:** make optional properties required+nullable for openai-strict (S8, T11) ([b896455](https://github.com/vickyonit/mcp-schema-bridge/commit/b8964552d490dc8c826d836e409656047c036346))
* **core:** merge allOf into a single schema (S3, T7) ([dc2c996](https://github.com/vickyonit/mcp-schema-bridge/commit/dc2c996c09f5dfccfe98f4b08d29fd7f07644eae))
* **core:** resolve $ref, $id, $anchor and dialects (S1, T2c) ([e14fa77](https://github.com/vickyonit/mcp-schema-bridge/commit/e14fa77b6f93c108583497af57d57ac9103c8243))
* **core:** restate dropped constraints as description hints (S10) ([be17c57](https://github.com/vickyonit/mcp-schema-bridge/commit/be17c57c1eeecff8554db6ff1381d341ae88d21b))
* **core:** shape unions for each target (S6: T4, T5, T8, T9) ([388b147](https://github.com/vickyonit/mcp-schema-bridge/commit/388b147e69a0077cd974b442510ecdd2c881645e))
* **core:** validate output limits, property keys and array items (S11, T18) ([88662f8](https://github.com/vickyonit/mcp-schema-bridge/commit/88662f83244cc65fde2e57dc2468b1b434af3621))
* friendlier checks for MCP server builders ([025e463](https://github.com/vickyonit/mcp-schema-bridge/commit/025e463f5310153de0253712f3cdd23526104931))
* **rules:** add provider rules tables, rules schema and package loader ([d02833d](https://github.com/vickyonit/mcp-schema-bridge/commit/d02833d58db295101b28c716b19ae12f95847d0e))
* **scripts:** add live provider probe harness for Phase 0 evidence ([8d55d93](https://github.com/vickyonit/mcp-schema-bridge/commit/8d55d934f14dab01f0dfd47e0b7132cbc8ef0eb0))
* **scripts:** record live verdicts and check them offline ([00d280e](https://github.com/vickyonit/mcp-schema-bridge/commit/00d280efcb67831d085e27dc70a78de48b1c0210))
* support strict_fallback in normalize_schema ([8d6cf93](https://github.com/vickyonit/mcp-schema-bridge/commit/8d6cf93595f09ccf587f9712ed9e98c6218379cb))
* **ts:** add denormalizeArgs, SDK payloads and the public API ([9093469](https://github.com/vickyonit/mcp-schema-bridge/commit/909346908732bc1728ebca495c44c468aa29a937))
* **ts:** add order-preserving JSON parser and serializer ([73c9211](https://github.com/vickyonit/mcp-schema-bridge/commit/73c9211ff8d49e1b74c91af0d9ccc5c948835469))
* **ts:** port data model (errors, parse, report, rules, options, tree, context) ([1134de9](https://github.com/vickyonit/mcp-schema-bridge/commit/1134de92142ba454c8ac60e30f2b33d7ece4a0aa))
* **ts:** port the normalization pipeline; byte-identical to Python on the corpus ([b1f4177](https://github.com/vickyonit/mcp-schema-bridge/commit/b1f4177ad97fa6ee526fc737708011c1fdec66fd))
* **ts:** scaffold TypeScript package; port JCS, pointer and regex scanner ([6f79f23](https://github.com/vickyonit/mcp-schema-bridge/commit/6f79f2374a039776541e888f0305613536127db8))
* **ts:** typed SDK payloads; client-builder examples in Python and TypeScript ([4b36fb8](https://github.com/vickyonit/mcp-schema-bridge/commit/4b36fb803470fcde6d1dbfd4eb0cee766d280da7))


### Bug fixes

* **core:** keep the source path of report entries on emptied nodes ([bddd384](https://github.com/vickyonit/mcp-schema-bridge/commit/bddd38497ff4343c644d7bde51896d683a20053a))
* **core:** report big integers rounded under big_int="round" ([a3c3b63](https://github.com/vickyonit/mcp-schema-bridge/commit/a3c3b6372ffd244f887478cd8fa895796b5a7f67))
* **core:** report every value an allOf merge changes ([04011ad](https://github.com/vickyonit/mcp-schema-bridge/commit/04011ad91c5753ce5f28b1a8804332e37d6bee38))
* **core:** report the type change made when folding OpenAPI nullable ([558d252](https://github.com/vickyonit/mcp-schema-bridge/commit/558d252315b42dd8065a51e90a028d20d8851917))
* **core:** track visited nodes by identity, not reusable id()s ([85a9a1f](https://github.com/vickyonit/mcp-schema-bridge/commit/85a9a1fd7646d372c028396aaec814a82bce03db))
* OpenAI strict verified live; flatten unsupported tuples correctly ([8f6488a](https://github.com/vickyonit/mcp-schema-bridge/commit/8f6488a5279ad52fb1485cfa05c631cf5a02593c))
* read and write all text files as UTF-8 ([c763849](https://github.com/vickyonit/mcp-schema-bridge/commit/c763849b6d6299af210dca77ce33751a046bf160))
* summary explains tools demoted to non-strict by strict_fallback ([5062cb1](https://github.com/vickyonit/mcp-schema-bridge/commit/5062cb1e39fb7f5d1def95a6c2081c8ee84d1322))
* treat optional nullable properties with default null as reversible ([5ca77af](https://github.com/vickyonit/mcp-schema-bridge/commit/5ca77af545f8a649c798f6267590165c371b2252))
* **ts:** mention demoted tools in summary() like Python ([b5f80a7](https://github.com/vickyonit/mcp-schema-bridge/commit/b5f80a7b7aff367cd20a9451389046e3ba8d61f1))
* **types:** satisfy strict pyright in as_tool_dict ([b9daed8](https://github.com/vickyonit/mcp-schema-bridge/commit/b9daed8e0a5ffc2a6fde2d2e477093f3450ce457))
* work around two Gemini behaviours found by live verdicts ([6c9a238](https://github.com/vickyonit/mcp-schema-bridge/commit/6c9a238fb9065a9d3f185494b0e63422ed7a9a7a))


### Documentation

* add ADRs for build decision and Apache-2.0 license ([f04a413](https://github.com/vickyonit/mcp-schema-bridge/commit/f04a413d86bde59113e44209b7a43790da82e900))
* add benchmark, framework-author guide and implementation notes ([f97eb49](https://github.com/vickyonit/mcp-schema-bridge/commit/f97eb49402cada7bafe65095c606afd22b630c01))
* add launch checklist with remaining maintainer actions ([23f3ea5](https://github.com/vickyonit/mcp-schema-bridge/commit/23f3ea540b4f1ca91a3d4def2bdd7d428a9b49c1))
* describe the TypeScript package and cross-language parity ([a5af803](https://github.com/vickyonit/mcp-schema-bridge/commit/a5af803405d895e3013b2adb158670fbd47c6c2e))
* **examples:** end-user walkthrough: proxy fixes a server that breaks gemini-cli ([260ac4f](https://github.com/vickyonit/mcp-schema-bridge/commit/260ac4f0ca6f3641a28e68e830569c23c21d543a))
* how-to guide for MCP server builders, client builders and users ([cdee6d4](https://github.com/vickyonit/mcp-schema-bridge/commit/cdee6d4ce35a61c3131cd566a3416f15be10c350))
* **spec:** publish JSON Schemas for report, normalized tool and reverse map ([bf97c38](https://github.com/vickyonit/mcp-schema-bridge/commit/bf97c38bbb5f7f9fe816bbfbc31641c4c60f811f))
* update launch checklist after making the repository public ([5b486b9](https://github.com/vickyonit/mcp-schema-bridge/commit/5b486b93eb1c0d56c7b6b6b4b4e0d5646e1d9040))
* write README, rule catalog, examples and verification docs ([0e36ef2](https://github.com/vickyonit/mcp-schema-bridge/commit/0e36ef2437a0bb325a49afff303a25d5e44cafd5))

## Changelog

All notable changes are documented here. The project follows [Semantic Versioning](https://semver.org/)
(see [docs/PLAN.md §10](docs/PLAN.md)). Changes that only update provider rules are listed under
"Provider rule updates".
