# Derin analiz · abhishekray07/claude-meter (Referans #2)

**Okunan:** `internal/proxy/proxy.go`, `internal/normalize/normalizer.go`,
`normalize/types.go`, `capture/types.go`, `storage/normalized_jsonl.go`,
`internal/app/app.go` (ilk 300), `analysis/analyze_normalized_log.py`
(ilk 400), `docs/plans/2026-03-25-claude-meter-estimator-v0.md`.
**Okunmayan:** `normalize/sse.go`, `storage/jsonl.go` (ham yazıcı),
`cmd/claude-meter/{main,setup,backfill}.go`, `analysis/{dashboard,report,
export}.py`, `dashboard.html`. **Sürüm:** 2026-04-01, 48 dosya, Go + Python,
alpha, 93★.

## §8 başlıkları

### Data Acquisition — yerel proxy
`ANTHROPIC_BASE_URL` → yerel HTTP sunucu. `ServeHTTP`: istek gövdesini
tamamen okur, header'ları klonlayıp upstream'e iletir, yanıt header'larını
kopyalar, gövdeyi **hem istemciye akıtır hem belleğe tamponlar**
(`io.MultiWriter`) → `CompletedExchange{id, başlangıç, bitiş, süre_ms,
request{method,path,headers,body}, response{status,headers,body}}` →
tamponlu kanala **bloke etmeden** bırakır (dolu ise düşürür, sayar).
TLS sonlandırma yok (yerel düz HTTP; upstream HTTPS Go istemcisiyle).
Streaming SSE geçer ama tüm gövde bellekte tutulur.

### Data Model (normalize/types.go)
`Record{id, request_timestamp, response_timestamp, method, path, status,
latency_ms, request_model, response_model, session_id,
declared_plan_tier, request_id, usage{input, cache_creation, cache_read,
output}, ratelimit{status, representative_claim, fallback_percentage,
overage_disabled_reason, overage_status, retry_after_s, windows{<ad>:
{status, reset_ts, utilization, surpassed_threshold}}}}`.
- `session_id`, isteğin `metadata.user_id` alanındaki JSON'dan (`session_id`
  anahtarı) çıkarılıyor — **Claude Code istekleri oturum kimliğini
  böyle taşıyor** (dolaylı gözlem; proxy ile doğrulanabilir).
- `declared_plan_tier` kullanıcı beyanı (max_20x vb.) — kohort anahtarı.
- Pencere adları genel (`5h`, `7d` … yeni pencereler otomatik).

### Storage
Ham ve normalize ayrı dizinler (`raw/`, `normalized/`), **günlük JSONL**
dosyaları, dizin 0700 / dosya 0600. Ham veri = tam prompt/yanıt gövdesi
(gizlilik yükü burada). Arka planda tek yazıcı goroutine, panic recover.

### Processing
`Normalize`: gzip çözme; `/v1/messages` için SSE (`message_start` model+
usage, `message_delta` usage) veya JSON gövde; `/v1/messages/count_tokens`
ayrı. Header ayrıştırma önek tabanlı ve **kapalı liste yok**.
CLI log satırı: model | in/out/cache | pencere yüzdeleri renkli; her N
istekte özet.

### Analytics / Estimation (analysis/*.py)
Amaç: **görünmez kotanın birimini kestirmek.** Yaklaşım:
- Aday sayaçlar: `effective_tokens_raw` (in+out+cache_create+cache_read),
  `no_cache_read`, `io_only`, `weighted` (cache_read×w),
  **`price_equivalent_5m`** (model liste fiyatları ağırlık: haiku
  1/5/1.25/0.10, sonnet 3/15/3.75/0.30, opus 5/25/6.25/0.50 $/Mtok).
- **Kümülatif aralık** kurucu: (hesap parmak izi, plan, pencere) başına;
  utilization sabitken kayıtları biriktir; artınca aralık yayınla
  (`implied_cap = usage_total / Δutil`); azalınca (sıfırlanma) yeniden
  demirle. Eksik usage'lı aralık `complete_usage=false`.
- Eski yöntem (oturum içi komşu delta) karşılaştırma için tutuluyor.
- Özet: kohort başına count/min/p10/medyan/p90/max; **<3 nokta ise yalnız
  min/medyan/max** ("dürüst kalmak için"). Tahmin bandı filtresi:
  ≤10 kayıt ve ≤20 dk'lık aralıklar daha güvenilir.
- README'nin "confidence" iddiası bu band/percentile yapısına dayanıyor;
  ayrı bir güven modeli okunmadı.

### Forecasting — pencere sonuna projeksiyon `dashboard.py`'de olabilir
(okunmadı). Estimator gelecek değil **gizli sabit** (cap) tahmin ediyor.

### Visualization — Python `dashboard.py` + gömülü `dashboard.html`
(okunmadı). Go süreci Python betiğini çağırıyor: iki dil, iki çalışma
zamanı — dağıtım yükü.

### Alerts — CLI'da 429 kırmızı satır; başka yok.

### Privacy
En kötü profil: **tam prompt/yanıt gövdeleri diskte** (`raw/`), yalnız
dosya izni koruması. Normalize kayıtlar içerik taşımıyor — ayrım doğru
ama ham veri varsayılan açık. Kimlik: proxy Authorization header'ını
geçirir, saklamaz (ham JSONL'de header listesi var — **Authorization
header'ı ham kayda yazılıyor mu?** `flattenHeaders` tüm header'ları
düzleştiriyor → büyük olasılıkla evet; `storage/jsonl.go` okunup
doğrulanmalı. Ciddi risk).

### Architecture
```
Claude Code ─HTTP─▶ proxy.Server ─chan(256)─▶ app.processExchange
                                              ├─ rawWriter (raw/YYYY-MM-DD.jsonl)
                                              ├─ normalizer.Normalize → Record
                                              ├─ normalizedWriter (normalized/…)
                                              └─ log + status
analysis/*.py ◀── normalized JSONL ── (çevrimdışı)
```
RAW → NORMALIZE → (çevrimdışı) ANALYSIS → ESTIMATION → VISUALIZATION
katmanları **gerçekten ayrı**; normalizasyon değişmeden estimator
yeniden çalıştırılabiliyor (plan dosyası bunu açıkça hedefliyor).

### Performance
Kritik yolda: gövde tamponlama (bellek = yanıt boyutu), tek goroutine
yazıcı, kanal dolunca **kayıt düşürme** (veri kaybı sayılıyor ama
kullanıcıya gösterilmiyor). Latency etkisi ölçülmemiş.

### Reliability
Proxy çökerse Claude Code çalışmaz (base URL ona bakıyor) — **tek
başarısızlık noktası**. Claude Code'un base URL'i yok sayması / yeni uç
ekle­mesi (`/v1/messages/count_tokens` zaten ayrı ele alınmış) kırılganlık.

### Extensibility
Header ayrıştırıcı genel; sayaçlar parametreli; başka sağlayıcı yok (yalnız
Anthropic biçimi).

## §9 özel maddeler — verdikt

| Madde | Verdikt |
|---|---|
| Local proxy | ⏸ **Yalnız Research Mode**; varsayılan asla. Tek başarısızlık noktası + ham içerik |
| Raw capture | ⏸ Research Mode'da, **şifreli** ve Authorization header'ı **çıkarılarak** |
| Normalization pipeline | ✅ **Alınır**: `Record` şeması iyi bir başlangıç; `source`/`confidence` eklenir |
| JSONL storage (günlük dosya, 0600) | ✅ Basit ve doğru; SQLite ile birlikte "olay günlüğü" olarak |
| Rate-limit headers | ✅ Alan adları alındı (notes/02 §E); pasif okuma |
| 5h/7d windows | ✅ Genel pencere adı yaklaşımı alınır |
| Model-specific usage | ✅ `response_model` öncelikli, `request_model` yedek |
| Token breakdown / cache | ✅ Dört alan standart |
| Estimation + confidence | ✅ **Alınır (en değerli fikir):** kota birimi hipotez; aday sayaçlar; kümülatif aralık; percentile bandı; <3 nokta dürüstlüğü |
| Time-series | ⏸ dashboard.py okunmadı |
| Dashboard | ✗ Go+Python karışımı; bizde tek çalışma zamanı |
| Privacy model | ✗ Ham gövde varsayılan; header sızıntısı şüphesi |
| Raw vs normalized | ✅ **Doğru ilke**; platformda katman olarak korunur |

## RAW→NORMALIZATION→ANALYSIS→ESTIMATION→VISUALIZATION doğru mu?
**Evet, iki düzeltmeyle:**
1. "RAW" her collector için aynı anlama gelmez: proxy'de ham gövde, OTLP'de
   ham metrik/olay, transcript'te ham JSONL satırı, poller'da ham JSON.
   Ham depo **kaynağa göre sınıflandırılmalı** (MP §25: PUBLIC/INTERNAL/
   SENSITIVE/SECRET) ve SENSITIVE/SECRET olanlar varsayılan **yazılmamalı**.
2. Estimation'ın çıktısı tek sayı değil **dağılım + sürüm** olmalı
   (claude-meter'ın percentile bandı + MP §30 estimator versiyonlama).

## Platforma aktarılacaklar (özet)
- `Record` benzeri normalize şema + pencere haritası.
- Kota birimi estimator'ı: sayaç hipotezleri × kümülatif aralık ×
  percentile bandı; "price_equivalent" hipotezi dahil.
- Ham/normalize ayrımı; günlük JSONL olay günlüğü; 0600.
- Proxy yalnız Research Mode; Authorization header'ı asla diske.

## Doğrulama (2026-09-07)
`internal/storage/jsonl.go` `sanitizeHeaders`: `authorization`, `proxy-authorization`,
`x-api-key` başlıkları **diske yazılmadan önce temizleniyor** (request + response).
Önceki not'taki "Authorization diske yazılıyor olabilir" riski **kapandı**. Ham
gövdeler (`Body []byte`) ise hâlâ olduğu gibi yazılıyor — içerik riski geçerli.
