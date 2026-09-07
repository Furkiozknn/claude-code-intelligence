# OTel GenAI semantik kuralları ↔ Claude Code ↔ platform birleşik modeli

Kaynak: `open-telemetry/semantic-conventions-genai` (sığ klon, 2026-09-07;
weaver v0.26.1). **Tüm öznitelikler `stability: development`** — kararlı
değil; alan adları değişebilir (sürümleme gerekçesi).

## Kayıt defteri (`model/gen-ai/registry.yaml`) — ilgili anahtarlar
- Sağlayıcı/model: `gen_ai.provider.name` (enum: openai, gcp.gen_ai,
  gcp.vertex_ai, gcp.gemini, **anthropic**, cohere, azure.ai.inference,
  azure.ai.openai, ibm.watsonx.ai, aws.bedrock, perplexity, x_ai, deepseek,
  groq, mistral_ai, moonshot_ai), `gen_ai.request.model`, `gen_ai.response.model`,
  `gen_ai.response.id`, `gen_ai.response.finish_reasons`, `gen_ai.response.status`,
  `gen_ai.response.time_to_first_chunk`.
- İstek: `gen_ai.operation.name`, `gen_ai.request.max_tokens`, `.temperature`,
  `.top_p`, `.top_k`, `.stream`, **`gen_ai.request.reasoning.level`**,
  `gen_ai.request.previous_response.id`, `gen_ai.output.type`.
- **Kullanım:** `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
  **`gen_ai.usage.cache_read.input_tokens`**, **`gen_ai.usage.cache_write.input_tokens`**,
  `gen_ai.usage.reasoning.output_tokens`, modalite kırılımları
  (`gen_ai.usage.{text,image,audio}.{input,output}_tokens`,
  `gen_ai.usage.{text,image,audio}.cache_read.input_tokens`).
  Not: `input_tokens` **cache'li tokenları da içerir** (belge: "SHOULD include
  all types of input tokens, including cached tokens") — Anthropic transcript'te
  `input_tokens` cache'siz kısımdır → dönüşümde **toplama** gerekir.
- `gen_ai.token.type` yalnız **`input` | `output`** (cache türü yok → metrikte
  cache ayrımı yapılamaz; span özniteliklerinde yapılır).
- Konuşma/ajan/araç: `gen_ai.conversation.id`, **`gen_ai.conversation.compacted`**
  (compaction sinyali!), `gen_ai.agent.{id,name,description,version}`,
  `gen_ai.tool.{name,type,description,call.id,definitions}`,
  `gen_ai.tool.call.{arguments,result}` (opt-in, hassas), `gen_ai.workflow.name`,
  `gen_ai.data_source.id`, `gen_ai.prompt.{name,version,variable}`.
- **İçerik (Opt-In, PII uyarısı):** `gen_ai.input.messages`, `gen_ai.output.messages`,
  `gen_ai.system_instructions`, `gen_ai.tool.definitions`, `gen_ai.prompt.variable`.
  Belge: "likely to contain sensitive information including user/PII data."
- Değerlendirme: `gen_ai.evaluation.{name,score.value,score.label,explanation}`.

## Anthropic sayfası (`docs/gen-ai/anthropic.md`) — gereksinim seviyeleri
Required: `gen_ai.operation.name`. Conditionally required: `conversation.id`,
`output.type`, `request.model`, `request.choice.count`, `request.seed`,
`request.stream`, `prompt.name/version`. Recommended: `response.id/model/
finish_reasons/time_to_first_chunk`, tüm `usage.*` (cache_read/cache_write
dahil), `request.*` ayarları, `conversation.compacted`. Opt-In: içerik.

## Metrikler (`docs/gen-ai/gen-ai-metrics.md`)
| Metrik | Tür | Birim |
|---|---|---|
| `gen_ai.client.token.usage` | Histogram | `{token}` (öznitelik: `gen_ai.token.type`) |
| `gen_ai.client.operation.duration` | Histogram | `s` |
| `gen_ai.client.operation.time_to_first_chunk` | Histogram | `s` |
| `gen_ai.client.operation.time_per_output_chunk` | Histogram | `s` |
| `gen_ai.server.request.duration` / `time_per_output_token` / `time_to_first_token` | Histogram | `s` |

Olay: `gen_ai.client.inference.operation.details` (içerik opt-in ile).
Maliyet için **standart yok**.

## Eşleme tablosu
| Claude Code (OTel) | Transcript | GenAI semconv | Platform alanı |
|---|---|---|---|
| `token.usage{type=input}` | `usage.input_tokens` | `gen_ai.usage.input_tokens` (**cache dahil**) | `tokens.input` (cache hariç) + türetilmiş `tokens.input_total` |
| `type=output` | `usage.output_tokens` | `gen_ai.usage.output_tokens` | `tokens.output` |
| `type=cacheRead` | `cache_read_input_tokens` | `gen_ai.usage.cache_read.input_tokens` | `tokens.cache_read` |
| `type=cacheCreation` | `cache_creation_input_tokens` (+ `ephemeral_5m/1h`) | `gen_ai.usage.cache_write.input_tokens` | `tokens.cache_write_5m`, `tokens.cache_write_1h` |
| — | (yok) | `gen_ai.usage.reasoning.output_tokens` | `tokens.reasoning` (Codex/Gemini için) |
| `model` | `message.model` | `gen_ai.request.model` / `response.model` | `model.id` |
| `effort` | — | `gen_ai.request.reasoning.level` | `request.effort` |
| `speed` | `usage.speed` | — | `request.speed` |
| `session.id` | `sessionId` | `gen_ai.conversation.id` | `session.id` |
| PreCompact/PostCompact hook | — | `gen_ai.conversation.compacted` | `session.compaction_count` |
| `agent.name`, `skill.name`, `mcp_server.name`, `mcp_tool.name` | `attributionAgent/Skill/McpServer/McpTool` | `gen_ai.agent.name`, `gen_ai.tool.name` | `attribution.*` |
| `api_request.request_id` | `requestId` | `gen_ai.response.id` | `request.id` |
| `cost_usd` (estimated) | — | (standart yok) | `cost.usd` + `evidence_class` |
| `tool_result.duration_ms` | — | `gen_ai.client.operation.duration` (araç için değil) | `tool.duration_ms` |

## Kararlar (Faz 7'ye girdi)
1. Birleşik model alan adları semconv'a **anlamca** hizalı, adlar platforma
   özgü kısa (`tokens.cache_read`); dışa aktarımda (Aşama 4) semconv adlarına
   birebir çeviri tablosu.
2. `input_tokens` anlam farkı (cache dahil/hariç) **her sağlayıcı adaptöründe
   açıkça belgelenir**; birleşik modelde iki alan.
3. `token.type`'ta cache olmadığı için metrik düzeyinde dışa aktarım kayıplı;
   span/olay düzeyi tercih.
4. İçerik öznitelikleri allow-list dışı; platform bunları hiçbir modda
   toplamaz (Research Mode dahil — orada ham gövde ayrı, işaretli depoda).
