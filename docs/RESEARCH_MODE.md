# RESEARCH_MODE — araştırma modu

Durum: Faz 7 taslağı. Kanıt: claude-meter (proxy + estimator), CodeZeno
(429 kuralı), rate-limit başlıkları (`notes/02` §E), cacheeconomics (rakam
disiplini). MP §28–29, §31.

## 1. Amaç
Belgesiz veya kanıtsız soruları **kontrollü deneyle** yanıtlamak; sonuçları
**özet parametre** olarak çekirdeğe aktarmak. Varsayılan kapalı; ayrı komut
(`cci research …`), ayrı dizin (`~/.cci/research/`), ayrı şema; çekirdek DB'ye
yazmaz.

## 2. Yetenekler
| Yetenek | Ne | Sınır |
|---|---|---|
| Proxy yakalama | Kullanıcının kendi Anthropic trafiği (MITM, `ANTHROPIC_BASE_URL`) → rate-limit başlıkları, gövde meta | başlıklar `authorization/x-api-key/proxy-authorization/cookie` diske yazılmadan silinir; gövdeler 7 gün, 0700 |
| Ham OTLP gövdeleri | `OTEL_LOG_RAW_API_BODIES=file:<dir>` → dizin research altında | aynı saklama; çekirdek alıcı bu olayları düşürür |
| Kota birimi estimator'ı | §3 | yalnız bant yayınlar |
| Sağlayıcı davranış deneyleri | 429 `Retry-After`, alıcı kapalıyken davranış (U2), pencere sıfırlanma anları | nazik: tek gözlem yeter, zorlama yok |
| Şema keşfi | `usage_api` yanıt anahtarları, transcript yeni kayıt türleri, `limits[]` yeni `kind` | fark raporu → `provider.schema_change` |

## 3. Kota birimi estimator'ı (claude-meter protokolü, genişletilmiş)
Girdi: `quota_snapshots` (utilization, resets_at) + `usage_records` (hesap
genelinde; tüm oturumlar/alt ajanlar).
1. **Aralıklar:** ardışık iki snapshot arasında utilization değişmemişse
   biriktir; değiştiği anda aralık kapanır: `Δutil`, aralıktaki kullanım
   vektörü `(input, output, cache_read, cache_write_5m, cache_write_1h)`
   model başına.
2. **Aday sayaçlar:** `raw` (hepsi), `no_cache_read`, `io_only`,
   `weighted` (model × tür ağırlıkları), `price_equivalent` (LiteLLM $/Mtok,
   modelin **kendi** cache oranıyla — sabit 0.1× yok).
3. Her aday için `implied_cap = usage/Δutil`; aralıklar arasında **değişim
   katsayısı** en düşük aday "en tutarlı" (kanıt: tutarlılık, doğruluk değil).
4. Yayın: aday başına `p10/p50/p90`; <3 aralık → yalnız min/median/max ve
   `confidence=learning`; hiçbir zaman nokta değeri.
5. `weekly_scoped` pencereler model kapsamlı → model başına ayrı estimator.
6. Çıktı çekirdeğe **yalnız** `estimator_params{version, candidate, cap_band,
   n_intervals, window_kind}` olarak aktarılır; ham aralıklar research'te kalır.

## 4. Deney günlüğü formatı
`~/.cci/research/experiments/<tarih>-<ad>.md`: hipotez, kurulum (env,
sürümler), gözlem (redakte), sonuç, çekirdeğe aktarılan parametre, tekrar
koşulları. Kullanıcıya görünen sonuçlar `cci research report`.

## 5. Güvenlik ve etik sınırlar
- Kendi hesabı, kendi trafiği; başka kullanıcı yok.
- Sağlayıcı sınırlarını ölçmek için **zorlama yok**: 429'u yalnız doğal
  akışta gözle; token rotasyonu/yenileme yok; kota harcayan sentetik istek
  atma (CodeZeno'nun `claude -p .` yaklaşımı reddedildi).
- Klonlanan repoların `.claude/` içeriği çalıştırılmaz (tedarik zinciri).
- Research dizini `cci research purge` ile silinir; çekirdeğe yalnız
  parametre geçtiği için silme analitiği bozmaz.

## 6. Çıkış ölçütleri (bir deneyin bitmesi)
Soru için ≥N bağımsız gözlem, sonuç deney günlüğünde, parametre sürümlü
konfigürasyona işlendi, `doctor` yeni parametre sürümünü gösteriyor.
