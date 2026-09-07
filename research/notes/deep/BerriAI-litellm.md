# Derin analiz · BerriAI/litellm — `model_prices_and_context_window.json`

**Okunan:** dosyanın kendisi (2.3 MB, **3 818 model**, 339 `claude` girdisi;
2026-09-07 indirildi). Repo'nun geri kalanı (proxy, gateway) kapsam dışı;
ekosistemin **fiyat kaynağı** olarak inceleniyor (toktrack, VibeBill, codeburn,
TokenTracker hepsi buradan besleniyor).

## Şema (claude girdilerinde görülen alanlar, sıklıkla)
| Alan | Not |
|---|---|
| `input_cost_per_token`, `output_cost_per_token` | USD/token (305/339) |
| `cache_read_input_token_cost` (253), `cache_creation_input_token_cost` (235) | |
| **`cache_creation_input_token_cost_above_1hr`** (140) | 1 saatlik cache yazımı — tycho/toktrack'in kullandığı alan |
| `*_above_200k_tokens` (26) | uzun bağlam kademesi (input/output/cache_creation/cache_read + `_above_1hr_above_200k`) |
| `max_input_tokens`, `max_output_tokens`, `max_tokens` | bağlam penceresi |
| `litellm_provider`, `mode` | `anthropic`, `bedrock_converse`, `vertex_ai`, `azure_ai`… |
| `supports_prompt_caching`, `prompt_cache_min_tokens` | |
| `deprecation_date` (91), `source` (60) | kaynak URL'si bazı girdilerde |
| `search_context_cost_per_query`, `input_cost_per_second` | web arama, ses |

Örnek (`claude-fable-5-1`): in 1e-5, out 5e-5, cache write 1.25e-5,
write-1h 2e-5, cache read 2.5e-7 (girdinin %2.5'i — Opus-5'te %10:
5e-6 → 5e-7). **Model başına cache okuma oranı sabit değil**; "cache read =
0.1×" gibi sabit çarpanlar (cacheeconomics) yanlış olabilir.

## Anahtar sorunları
- Aynı model **onlarca anahtar** altında: `claude-opus-5`, `anthropic.claude-
  opus-5`, `global./us./eu./au./jp.` bölge önekleri, `azure_ai/`, `databricks/`,
  `perplexity/anthropic/`. Transcript `message.model` → eşleştirme kuralı
  gerekli (toktrack: tarih son eki at; VibeBill/TokenTracker: `matcher` +
  `curated-overrides`).
- Fiyat **bölgeye/sağlayıcıya göre** farklı olabilir; Claude Code'un kendi
  `cost.usage` sayısı Anthropic liste fiyatıyla → çapraz doğrulama noktası.

## Platforma aktarılacaklar
1. Fiyat modülü: bundled snapshot + isteğe bağlı yenileme (**tek ağ çağrısı**,
   asla otomatik değil — VibeBill), sürümlü ve tarihli (`pricing_version`,
   `fetched_at`).
2. Fiyat alanları: 5 bileşen (input, output, cache_read, cache_write_5m,
   cache_write_1h) + 200k üstü kademe; eksikse maliyet **withheld** (Figure).
3. Model anahtarı eşleştirme kuralları + "bilinmeyen model" sayacı.
4. `deprecation_date` → sağlayıcı değişim tespiti (MP §28) için sinyal.
