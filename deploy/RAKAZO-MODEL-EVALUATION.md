# Rakazo free-model evaluation - 23 November 2026

Use Auto for this quality-first priority pool:

1. Groq - `openai/gpt-oss-120b`
2. OpenRouter - `nvidia/nemotron-3.5-lightning:free`
3. NVIDIA NIM - `nvidia/nemotron-3.5-super-vl-120b-a12b`
4. Kiro - `glm-5`
5. Gemini - `gemini-3.1-flash-lite`

Keep explicit provider prefixes in stored combo targets, including `openrouter/nvidia/...:free` and `nvidia/nvidia/...`. Use the existing pinned connections and restricted `agent-free` key. No account permissions, provider-wide filters, billing settings or token allowances changed in this evaluation. The router's private database holds the applied pool; this document records the decision and evidence.

## Scope and method

Reviewed all 10 connected providers and screened 27 model candidates across nine. Ollama Cloud's current public pricing describes per-token billing; no zero-price route was confirmed, so no paid inference was attempted there. Candidate discovery used the connected account's catalog, official pricing and the existing strict free-only gate. Catalog availability alone does not establish that an account can execute a model.

All prompts and tool responses were synthetic. Test tools were inert; no notes, reminders, orders or user files were changed. Used one temporary route and a restricted expiring key, then deleted both and revoked the management credential. Private response evidence and before/after pool snapshots stay outside Git.

The initial screening prompt allowed ambiguous reasoning formatting. Do not use its numerical quality scores. The comparable confirmation round instead used two explicit-schema variants with:

- Seven reasoning answers each: percentage arithmetic, sampling probability, dependency scheduling, SQL NULL/distinct semantics, logical entailment and successive price changes.
- Four evidence-grounded facts each: newest-source precedence, port, region and abstention when a CEO is not named. This measures grounding in supplied evidence, not broad real-world factual knowledge.
- Ninety records per variant. Retrieve exactly the records matching three conditions, resist an instruction embedded in a quoted record, and avoid duplicates. Precision = correct unique IDs / returned IDs; recall = correct unique IDs / expected IDs; F1 is their harmonic mean.
- Structured output compliance, streaming completion, tool selection, argument correctness and continuation after a tool result.

Composite score = 40% reasoning accuracy + 30% retrieval F1 + 20% grounded factual accuracy + 10% strict JSON compliance. Content inside JSON fences can earn accuracy points but loses strict-format points. An absent/invalid answer contributes zero to the end-to-end score; transport/account failures are reported separately and do not prove weak reasoning. Each finalist also received a third, numerically different holdout and an approval-before-save tool test.

These are small acceptance tests, not statistical rankings or claims of universal model superiority. Candidates are not guaranteed to perform the same on open-ended research, coding, images or your actual documents. The two-round table is comparable; selected finalists have additional evidence below. Mean times include response generation, not just first-token latency. Existing connection/startup timeouts can reject a slow candidate; they are not token quotas.

## Comparable confirmation results

| Provider / model | Reasoning / 14 | Grounded facts / 8 | Precision | Recall | End-to-end score / 100 | Mean seconds | Tool continuation in screening |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| groq / `openai/gpt-oss-120b` | 14 | 8 | 100.0% | 100.0% | 100.0 | 4.5 | failed; finalist retest passed |
| groq / `openai/gpt-oss-20b` | 6 | 4 | 50.0% | 50.0% | 47.0 | 2.6 | pass |
| groq / `qwen/qwen3.8-27b` | 8 | 8 | 100.0% | 100.0% | 83.0 | 0.5 | pass |
| gemini / `gemini-3.1-flash-lite` | 10 | 8 | 92.9% | 100.0% | 87.5 | 1.2 | pass |
| gemini / `gemini-3-flash-preview` | 7 | 4 | 50.0% | 50.0% | 50.0 | 17.2 | pass |
| kiro / `claude-haiku-4.5` | 5 | 8 | 100.0% | 100.0% | 64.5 | 2.6 | pass |
| kiro / `claude-sonnet-4.5` | 11 | 8 | 100.0% | 100.0% | 81.5 | 2.6 | pass |
| kiro / `deepseek-3.2` | 9 | 8 | 100.0% | 100.0% | 85.5 | 4.5 | pass |
| kiro / `qwen3-coder-next` | 5 | 8 | 100.0% | 91.7% | 72.5 | 1.8 | pass |
| nvidia / `nvidia/nemotron-3.5-super-vl-120b-a12b` | 14 | 8 | 100.0% | 100.0% | 100.0 | 19.1 | pass |
| openrouter / `nvidia/nemotron-3.5-lightning:free` | 14 | 8 | 100.0% | 100.0% | 100.0 | 29.0 | pass |
| openrouter / `baidu/ernie-5.5-flash-preview:free` | 14 | 8 | 100.0% | 100.0% | 100.0 | 4.6 | pass |
| kiro / `glm-5` | 9 | 8 | 100.0% | 100.0% | 86.0 | 3.5 | pass |

## Promotion decisions

- Groq GPT-OSS 120B: 21/21 reasoning answers, 12/12 grounded facts and 100% retrieval precision/recall across three variants; approximately 4.5 seconds per scored response. Passed the final tool continuation and approval checks. The initial strict continuation check failed, so it was retested with the response saved; the final retest passed. Groq's provider-side 8,000 TPM allowance still makes it unsuitable for some large requests, which must fall through.
- OpenRouter Nemotron 3.5 Lightning: perfect scored variants and final tool/approval checks; about 29 seconds for the reasoning packets. Large-context tool calls were much faster: roughly 3.7 seconds in the isolated check, with 76,603 input tokens. Keep it despite slower long-form reasoning because its large-context tool behavior was consistent in this rehearsal.
- NVIDIA Nemotron Super VL: perfect scored variants and final tool/approval checks; roughly 23 seconds across the three scored packets. The large-context tool check took 5.1 seconds with 76,603 input tokens. Preserve it as an accurate independent fallback.
- Kiro GLM-5: highest measured Kiro composite across the scored variants and holdout (about 88.7/100), with 15/21 reasoning answers, all grounded facts and perfect retrieval. Passed approval, continuation and a roughly 66,104-token tool check. Sonnet had more correct reasoning answers (17/21) but repeatedly violated strict output formatting; the small score difference is not proof that GLM is universally stronger. Keep Kiro below the perfect-scoring candidates.
- Gemini Flash-Lite: fast (roughly 1.6 seconds across scored packets), with a composite around 87/100. Passed tools, continuation and approval, but made reasoning mistakes and returned extra records in two variants. Keep it as the final availability fallback rather than prioritizing speed over accuracy.

OpenRouter ERNIE 5.5 Flash Preview scored perfectly and averaged about 4.8 seconds across the scored variants. A live large-context test then returned a successful stream without the requested tool call; a retry passed. It was briefly applied during validation and replaced by Lightning before finalizing the rollout. Do not choose it as the primary long-task fallback based only on its faster short-test score.

## Provider coverage and exclusions

| Connected provider | Candidates screened | Outcome |
| --- | --- | --- |
| Groq | GPT-OSS 120B, GPT-OSS 20B, Qwen 3.8 27B | Keep 120B. 20B returned an empty answer in one confirmation; Qwen made reasoning errors. |
| Gemini | 3.1 Flash-Lite, 3 Flash Preview, 2.5 Flash | Keep Flash-Lite. Preview hit the existing startup timeout once; 2.5 returned 404. |
| Kiro | Haiku 4.5, Sonnet 4.5, DeepSeek 3.2, Qwen3 Coder Next, GLM-5, MiniMax M2.5 | Replace Haiku with GLM-5; MiniMax timed out. Other results appear above. |
| NVIDIA | Nemotron 3.5 Super VL, Gemma 4 31B | Keep Nemotron. Gemma hit startup timeout before content. |
| OpenRouter | Nemotron Lightning, Gemma 4 31B, ERNIE 5.5 Flash Preview, Nemotron Ultra, Particle-1 | Keep Lightning. Gemma returned 429, Ultra timed out, Particle returned service-unavailable, and ERNIE was inconsistent on the long tool check. |
| SambaNova | Llama 3.3 70B, GPT-OSS 120B | Payment-method-required 402, then unavailable/skipped. No billing change. |
| HuggingChat | DeepSeek V4 Flash, Gemma 4 31B | Adapter received HTML instead of JSON (502), then unavailable/skipped. Not ranked for reasoning. |
| OpenCode Zen | MiMo V2.6 Flash Free, Nemotron Lightning Free | Upstream free-usage refusal/429, including a message restricting free usage to OpenCode. No workaround attempted. |
| Vercel AI Gateway | Nemotron Lightning Free, Flint v1.0 | Upstream 403 requires a card on file even for these zero-priced catalog entries. No card added. |
| Ollama Cloud | Catalog/pricing review only | Current published cloud pricing is per-token; no confirmed zero-price candidate. Excluded without inference. |

## Final live checks

The final `agent-free` pool returned a complete large-context stream and a valid tool call through OpenRouter with 76,559 reported input tokens, in about 5.6 seconds. Groq was skipped on this final request; do not describe it as a new observed 413. Earlier tests established Groq 413 fallback behavior. A separate small production-key request succeeded; raw `auto` and a paid model request remained blocked with HTTP 403.

Rakazo's token-quota and usage-quota tables remain empty, key rate limits remain empty, compression remains disabled, and strict free-only policy remains enabled. The benchmark requests supplied no token-budget fields. Existing MFA, approvals, sandbox isolation, Stop and CPU/RAM protections are unchanged. No application image or service restart was needed.

## Catalog and pricing sources

- [Groq model catalog](https://console.groq.com/docs/models) and [rate limits](https://console.groq.com/docs/rate-limits).
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).
- [Kiro available models](https://kiro.dev/docs/models/available-models/) and the connected account's model discovery response.
- [NVIDIA hosted API access](https://docs.api.nvidia.com/nim/docs/product).
- [OpenRouter live catalog](https://openrouter.ai/api/v1/models): selected variants advertised zero prompt/completion pricing and tool support.
- [OpenCode free-model terms](https://opencode.ai/docs/console/models/).
- [Vercel live catalog](https://ai-gateway.vercel.sh/v1/models): zero-price entries do not remove account eligibility requirements.
- [Ollama pricing](https://ollama.com/pricing).

Recheck catalogs and free-tier eligibility before replacing a target. Keep a private before-state snapshot, use a restricted temporary test key, score failures separately from content quality, run long-context/tool checks before final promotion, and revoke all test credentials afterward.
