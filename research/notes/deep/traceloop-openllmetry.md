# Derin analiz · traceloop/openllmetry (semantik kurallar odaklı)

**Okunan (web):** `opentelemetry-semantic-conventions-ai/.../semconv_ai/__init__.py`.
Repo'nun enstrümantasyon paketleri kapsam dışı; ilgi alanı **öznitelik adları**
(OTel GenAI resmi kuralları ile karşılaştırma için `notes/03-otel-genai-semconv.md`).

## openllmetry öznitelikleri (kesin dizeler)
| Grup | Adlar |
|---|---|
| Token | `gen_ai.usage.prompt_tokens`, `gen_ai.usage.completion_tokens`, `gen_ai.usage.total_tokens`, `gen_ai.usage.reasoning_tokens`, **`gen_ai.usage.cache_creation_input_tokens`**, **`gen_ai.usage.cache_read_input_tokens`** |
| Model | `gen_ai.request.model`, `gen_ai.response.model` |
| Sistem | `gen_ai.system` (eski; OTel'de `gen_ai.provider.name`), enum: openai, anthropic, cohere, mistralai, ollama, groq, azure, aws, google, langchain, crewai |
| İstek | `llm.request.type` (completion/chat/rerank/embedding/unknown), `gen_ai.is_streaming` |
| Traceloop | `traceloop.workflow.name`, `traceloop.entity.name`, `traceloop.entity.input`, `traceloop.entity.output` (**içerik!**), `traceloop.span.kind` |
| Metrik | `gen_ai.client.token.usage`, `gen_ai.client.operation.duration` |

## Claude Code OTel ile eşleme
| Claude Code | openllmetry / OTel GenAI |
|---|---|
| `claude_code.token.usage{type=input}` | `gen_ai.client.token.usage{gen_ai.token.type=input}` |
| `type=output` | `…=output` |
| `type=cacheRead` / `cacheCreation` | span özniteliği `gen_ai.usage.cache_read_input_tokens` / `…cache_creation_input_tokens` (OTel resmi token.type'ta cache değeri var mı → notes/03) |
| `model` | `gen_ai.request.model` / `gen_ai.response.model` |
| `api_request` olayı `cost_usd_micros` | karşılığı yok (maliyet semconv'da yok) |

## Platforma aktarılacaklar
1. Birleşik kullanım modeli alan adlarını **OTel GenAI** ile hizalı tut
   (`input_tokens`, `output_tokens`, `cache_read_input_tokens`,
   `cache_creation_input_tokens`, `reasoning_tokens`, `provider.name`,
   `request.model`/`response.model`) — dışa aktarma (Aşama 4) ücretsiz olur.
2. `traceloop.entity.input/output` gibi içerik özniteliklerini **asla**
   toplama; allow-list'te yok.
3. Maliyet için semconv yok → kendi `cost.*` alanları, `evidence_class` ile.
