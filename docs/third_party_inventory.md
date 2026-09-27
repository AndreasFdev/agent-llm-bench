# Third-Party Inventory

Status: initial inventory with locally verified revisions where available.

## Verified External Inputs

| Project | Intended Role in V0.3 | Upstream | License/Metadata | Local revision state |
|---|---|---|---|---|
| local-agent-benchmark | primary agentic quick-suite input | https://github.com/Exxact-Software/local-agent-benchmark | MIT, repo metadata present locally | embedded `.git`, `HEAD=335b04c30b1e4414615e6cafebcdebb7d659bda3` |
| local_agentic_llm | selected coding-task source | https://github.com/ywchiu/local_agentic_llm | MIT per upstream README | directory present locally, no embedded `.git` metadata |
| BFCL (gorilla/berkeley-function-call-leaderboard) | tool-calling baseline subset | https://github.com/ShishirPatil/gorilla | upstream repo metadata present locally | embedded `.git`, `HEAD=6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` |
| IFEval / IFBench | instruction-following subset | locally vendored benchmark inputs | revision and license still to verify | not yet fully inventoried |
| Harbor | optional deep-eval backend | harbor-framework/harbor | upstream reference only for now | not vendored locally in V0.3 |
| MetriLLM | inspiration / optional lightweight adapter | MetriLLM/metrillm | upstream reference only for now | not vendored locally in V0.3 |

## Notes

- `local_agentic_llm` is present as a working source tree but does not expose a
  local `.git` directory in this workspace snapshot. Upstream commit pinning
  must therefore be resolved by policy before publication.
- No upstream code was copied into the V0.3 package implementation in this
  initialization step.
- A later Prompt 0 continuation still needs to capture local modifications,
  benchmark-specific patch status and any additional vendored dependencies.