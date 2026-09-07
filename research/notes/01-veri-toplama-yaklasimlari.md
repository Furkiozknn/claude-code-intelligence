# 01 · Veri toplama yaklaşımlarının kıyası (MASTER_PROMPT §6)

**Durum:** Taslak v1 — 230 repo keşfi ve 39 README okuması üzerine.
Faz 5 derin analiziyle güncellenecek. Her hüküm için kanıt repo adıyla
veriliyor; kanıtsız hüküm yok.

## 0. Kısa cevap

Tek bir "en iyi" kaynak yok; **üç farklı granülerlikte üç farklı gerçek**
var ve hiçbir yaklaşım üçünü birden vermiyor:

| Gerçek | Granülerlik | Tek doğru kaynak |
|---|---|---|
| Abonelik kotası (5s/7g %) | hesap | Sağlayıcının kendi ucu (api-polling) **veya** Claude Code'un stdin `rate_limits`'i |
| Token tüketimi | tur / oturum | Yerel transcript (jsonl-parsing) **veya** yerleşik OTel `token.usage` |
| Maliyet | model × tur | **Yerleşik OTel `claude_code.cost.usage`** — resmî dokümana göre *istemci tarafı fiyat tablosu* ("satıcı tahmini"); yine de tek ve tutarlı kaynak. Yoksa kendi fiyat tablomuzla *tahmin* |

Bu yüzden birleşik veri modeli (§13) her alanda `source` ve `confidence`
taşımak **zorunda**; aksi hâlde "üç araç üç maliyet" sorunu tekrarlanır.

## 1. Yaklaşım yaklaşım

### 1.1 `api-polling` — sağlayıcının kullanım ucunu sorgulamak
**Örnekler:** jens-duttke, CodeZeno, onWatch, rjwalters, aqua5230, vibe-bar,
openusage (kısmen), caut, prototip.

| Boyut | Değerlendirme |
|---|---|
| Doğruluk | Kota yüzdesi için **en yüksek** — ucun kendisi gerçek. `limits[]` dizisi severity ve `is_active` bile veriyor (prototip gözlemi). |
| Güvenilirlik | Uç **belgelenmemiş**; şema haber verilmeden değişebilir (kod adı gürültüsü gözlendi). Token süresi dolar (401). Ucun kendi istek limiti var (~5/token raporlanıyor; issue #31637). |
| Gizlilik | OAuth token yalnızca sağlayıcıya gider; başka hiçbir yere değil. Kimlik dosyasını okumak gerekir. |
| Performans | Çok düşük: 180 sn'de bir küçük JSON. |
| Kararlılık | Orta: 6–7 Eylül'de 20 saat kesintisiz çalıştı. |
| Bakım | Ayrıştırıcı şema değişimine hazır olmalı (yedek yol + ham görünürlük + fixture testi). |
| Sağlayıcı bağımlılığı | Tam. Her sağlayıcı ayrı adaptör. |
| Hata modları | 401 süresi dolmuş token · 429 uç limiti · şema değişimi · kimlik dosyası yok/kilitli · sıfırlanma zamanında saat kayması · WSL/Windows yol farkı (sr-kai/claudeusagewin bunu ayrıca çözmüş). |

**Anti-pattern:** Uç limitine takılınca **yeni OAuth token üretip sayacı
sıfırlamak** (onWatch). Sağlayıcının korumasını aşar; hesap riski.
Doğru davranış: backoff + son bilinen değeri "bayat" etiketiyle göstermek
(rjwalters, jens-duttke, CodeZeno, prototip).

**Tur 2 eklemeleri (7 Eylül):**
- rjwalters `/v1/messages`'a **1 tokenlık istek** atıp rate-limit
  header'larını okuyor. Kanıt değeri: header'lar OAuth trafiğinde var.
  Ama her sorgu kota harcıyor — sınırda; platformda kullanılmayacak.
- **"Resmî CLI'a devret" kalıbı** (CodexQuotaSafe, codexU, rjwalters'ın
  OpenAI yolu): kimlik dosyasına hiç dokunmadan sağlayıcının kendi CLI
  app-server'ından stdio/JSON-RPC ile kota okumak. Codex'te
  `account/rateLimits/read` var. **Claude Code'da karşılığı var mı?**
  (Bilinen tek resmî kanal statusline stdin'i.) Faz 5 sorusu.
- aqua5230 Claude/Codex "kotasını" **yalnız yerel loglardan** türetip
  kota gibi gösteriyor — tahmini gözlem gibi sunma hatası (§10).
- Kimlik keşfi: Windows native + **WSL** (`\\wsl$\<distro>\home\…`)
  (sr-kai). Adaptör bunu desteklemeli.

### 1.2 `stdin-statusline` — Claude Code'un statusline'a verdiği `rate_limits`
**Örnekler:** claude-pace, ohugonnot, Maciek ("taze ise canlı gerçek"),
ccusage statusline, claude-powerline.

| Boyut | Değerlendirme |
|---|---|
| Doğruluk | Resmî; api-polling ile aynı kaynak, **sıfır ağ**. |
| Güvenilirlik | Yalnızca Claude Code ≥2.1.80 ve **yalnızca bir CLI oturumu çalışırken**. Claude Desktop agent mode ve VS Code native panel statusLine'ı render etmiyor (issue #55643/#20207/#21265 — prototipte doğrulandı). |
| Gizlilik | Mükemmel. |
| Performans | Statusline komutu hızlı olmalı (ccusage ~400 ms ölçüldü; npx 1.2 s takılma hissi). |
| Kararlılık | Geçici: oturum kapanınca kaybolur; kalıcılık için cache dosyası gerekir (gagar1n `.statusline-cache.json` okuyor). |
| Hata modları | Alan yoksa (eski sürüm) uydurmamak — claude-pace `--` gösteriyor, doğru davranış. |

**Sonuç:** Mükemmel ikincil kaynak; CLI oturumu varken api-polling'i
gereksiz kılar (uç limitini de korur). Tek başına yetmez.

### 1.3 `jsonl-parsing` — yerel transcript'ler (`~/.claude/projects/**/*.jsonl`)
**Örnekler:** ccusage (18.4k★), token-dashboard, phuryn, codeburn (41 araç),
token-monitor, tokburn (lsvishaal), tycho, prototip atıfı.

| Boyut | Değerlendirme |
|---|---|
| Doğruluk | Token sayıları **gözlenmiş** (`message.usage`: in/out/cache_create/cache_read, thinking). **Maliyet ise tahmin** — fiyat tablosu + cache varsayımına bağlı; aynı veriden $42 / $46 / $168 çıktı. Kota % **yok**. |
| Güvenilirlik | Format Claude Code'un iç formatı; `version` alanı var ama şema sözü yok. Alt-ajanlarda `cwd` geçici klasör olabiliyor; `isSidechain`. |
| Gizlilik | Dosyalar **tam prompt ve yanıt** içerir. Okumak yerel; ama çıkarılan her şey (export, telemetri) redaction'dan geçmeli. yahav10 PII tespiti + soket seviyesinde çıkış engeli koyuyor. |
| Performans | Dosyalar büyür; her turda tam tarama pahalı. Gerekli: mtime kısa devresi, satır ofseti/artımlı okuma, `"usage"` ön eleme (prototip), 30 sn cache. token-dashboard 30 sn'de tam yeniden tarıyor (ölçek sorunu). |
| Kararlılık | Claude Code yazarken kısmi satır okunabilir; tolere edilmeli. |
| Bakım | Diğer ajanlar için aynı sınıf: Codex `~/.codex/sessions/*.jsonl`, Gemini `~/.gemini/tmp/*.json`, DeepSeek `~/.dsh/sessions/` (token-monitor, codeburn belgeliyor). Parser başına bir dosya deseni (TokenTracker) doğru. |
| Hata modları | Dev dosya · encoding · yazım sırasında okuma · şema alanı yeniden adlandırma · fiyat tablosu güncel değil · `cwd` yanıltıcı. |

**Sonuç:** Atıf (proje/oturum/model/araç) için **tek kaynak**. Maliyet için
"estimated + estimator sürümü + fiyat tablosu sürümü" etiketiyle.

### 1.4 `hooks` — Claude Code hook olayları
**Örnekler:** disler (12 olay tipi), szaher (Unix socket alıcı), TechNickAI
(hook → OTel span), TokenTracker (SessionEnd), robbedoo (plugin).

| Boyut | Değerlendirme |
|---|---|
| Doğruluk | **Gerçek zamanlı gözlenmiş olay**: PreToolUse/PostToolUse (araç adı, girdi, sonuç, mcp_server), PostToolUseFailure, PermissionRequest, UserPromptSubmit, SessionStart/End, SubagentStart/Stop, PreCompact, Stop (transcript yolu). Token sayısı hook payload'ında **görünmüyor** — Stop'un verdiği transcript yolundan okunur. |
| Güvenilirlik | `settings.json`'a hook yazmak gerekir; yalnızca yapılandırılmış CLI oturumlarında. Her olayda bir süreç çalışır. |
| Gizlilik | Payload'lar prompt ve araç sonucu içerir. disler bunları SQLite'a yazıyor (eksi). |
| Performans | **Kritik:** hook Claude Code'un yolunda; yavaş/çöken hook deneyimi bozar, `Pre*` hook'ları sıfır dışı çıkışla engelleyebilir. Gözlemlenebilirlik hook'u **asla bloke etmemeli, asla başarısız olmamalı, zaman aşımı olmalı, fire-and-forget** göndermeli. |
| Hata modları | Alıcı kapalıyken hook ne yapar? (kuyruğa yaz, sessizce geç) · hook script bağımlılığı (uv/Python) yok · WSL/Windows yol. |

**Resmî doküman doğrulaması (notes/02 §B):** hook girdisinde token yok;
`"async": true` bloke etmeyen ve zaman aşımsız çalışır; çıkış 2 bloke
eder, diğer sıfır dışı kodlar çoğunlukla etmez; `prompt_id` OTel
`prompt.id` ile aynı → iki kaynak tek anahtarla birleşir;
`SessionStart.match_value=compact` ve `PreCompact/PostCompact` gözlenmiş
sıkıştırma sinyali verir; 30'dan fazla olay tipi (TaskCreated/Completed,
WorktreeCreate, PreModelSwitch…).

**Sonuç:** Oturum/araç istihbaratı (§14) için en iyi **gerçek zamanlı**
kanal; transcript taramayı tamamlar (olay → transcript/OTel'den token).
Varsayılan kapalı, opt-in, **`async: true` + daima çıkış 0 + alıcı
kapalıysa kuyruğa yaz** tasarımı şart.

### 1.5 `otlp` — Claude Code'un yerleşik OpenTelemetry çıkışı
**Örnekler:** acreeger (metrik adları belgeli), rockdarko, ColeMurray,
li0nel, ccdashboard (hafif Aspire alternatifi), aaraujodata, zcquant.

| Boyut | Değerlendirme |
|---|---|
| Doğruluk | **Resmî ve zengin:** `claude_code.session.count`, **`claude_code.cost.usage` (model bazlı USD — Claude Code'un kendi hesabı)**, `claude_code.token.usage` (in/out/cache), `lines_of_code.count`, `commit.count`, `pull_request.count`, `code_edit_tool.decision` (kabul/ret); olaylar: prompt, araç sonucu, API istek/hata. Kota % **yok**. |
| Güvenilirlik | Resmî özellik (`CLAUDE_CODE_ENABLE_TELEMETRY=1` + OTEL_* env). Standart protokol. Toplayıcı ayakta değilse Claude Code'un davranışı **doğrulanacak** (drop mu, tampon mu, yavaşlama mı?). |
| Gizlilik | Hedef kullanıcı kontrolünde; prompt loglama opsiyonel; kardinalite azaltma var. Yerel bir alıcıya gönderilirse hiçbir şey dışarı çıkmaz. |
| Performans | Mevcut örnekler 4 konteynerli Grafana yığını kuruyor — kişisel kullanım için ağır. **Fırsat:** platform kendi minik OTLP alıcısını gömerse (HTTP :4318, protobuf/JSON) Grafana'ya gerek kalmaz. ccdashboard'un "Aspire Dashboard" alternatifi bu yönde. |
| Hata modları | Env değişkenlerinin her oturumda ayarlı olması · gRPC/HTTP protokol seçimi · şema/ad değişimi (resmî olduğu için daha kararlı). |

**Resmî doküman doğrulaması (notes/02 §A):** `cost.usage` **istemci tarafı
fiyat tablosuyla** hesaplanıyor — gözlem değil, *satıcı tahmini*. Buna
karşılık: (a) maliyet ve token metrikleri `query_source` (main/subagent/
auxiliary), `agent.name`, `skill.name`, `mcp_server.name`, `mcp_tool.name`
öznitelikleriyle geliyor → **atıf bedava**; (b) `api_request` olayı istek
başına `cost_usd_micros` + `request_id`, `tool_result` olayı `duration_ms`
+ `success` veriyor; (c) `prompt.id` / `message.uuid` / `client_request_id`
korelasyon anahtarları var; (d) prompt/yanıt metni varsayılan redakte;
(e) alıcı kapalıyken davranış **belgelenmemiş**; (f) `rate_limits` yok.
zcquant tek Node süreciyle gömülü OTLP alıcısının çalıştığını gösteriyor.

**Sonuç:** **Claude Code için birincil token + maliyet + olay kaynağı.**
Maliyet "satıcı tahmini" olarak etiketlenir (`source: claude_code_otel`),
ama tek ve tutarlı olduğu için ccusage/token-dashboard'un ayrı ayrı
fiyat tablolarına tercih edilir. Kota için yetmez; poller/statusline
gerekir.

### 1.6 `proxy` — `ANTHROPIC_BASE_URL` ile araya girmek
**Örnekler:** claude-meter (referans #2), tokburn/patheonsceo, LiteLLM,
Helicone gateway, openproxy, polyllm-gateway.

| Boyut | Değerlendirme |
|---|---|
| Doğruluk | Her istek/yanıt + **rate-limit header'ları** (claude-meter 5s/7g pencereleri buradan türetiyor) — tur başına en zengin sinyal. Abonelik OAuth trafiğinde bu header'ların dönüp dönmediği **doğrulanacak**. |
| Güvenilirlik | **Kırılgan ve tehlikeli:** streaming SSE geçişi, auth header'ları, Claude Code güncellemeleri; proxy çökerse **iş durur**. Bazı araçlar base URL'i yok sayar. |
| Gizlilik | **En kötü:** ham prompt/yanıt yakalanır. claude-meter ham JSONL saklıyor. |
| Performans | Kritik yolda gecikme. |
| Bakım | Protokole sıkı bağlı. |

**Sonuç:** Yalnızca **Research Mode** (§29) için, opt-in, açık uyarıyla,
raw depo şifreli/redaction'lı. Asla varsayılan.

### 1.7 `sqlite-inspection` — diğer araçların yerel DB'leri
**Örnekler:** codeburn (Cursor `state.vscdb`, OpenCode), TokenTracker (Cursor,
Kiro, Hermes, Copilot, Zed, Goose), Tendo33 (state.vscdb'den token → API),
cursor-wrapped, cursor-chronicle, cursor-clean.

| Boyut | Değerlendirme |
|---|---|
| Doğruluk | Değişken: Cursor çıktı tokenı yanıt metninden **tahmin**, cache sunucu tarafında (codeburn belgeliyor). |
| Güvenilirlik | Şema belgelenmemiş; DB uygulama çalışırken kilitli olabilir (WAL); **sınırsız büyüme, vacuum yok, multi-GB'da UI donması** (cursor-clean). codeburn #114: dolu DB'ye rağmen sıfır kullanım — şema kayması örneği. |
| Gizlilik | Sohbetler DB'de. |
| Performans | Salt okunur/immutable açma; kopyala-sonra-oku. |

**Sonuç:** Çapraz sağlayıcı (Cursor/Copilot) için gerekli ama her zaman
"estimated" etiketiyle; adaptör başına sürüm tespiti.

### 1.8 `browser-scrape` / tarayıcı çerezi
**Örnekler:** Gronsten (headless Chromium), lugia19, claude-counter,
MuneebQureshi; caut/openusage/vibe-bar (çerezden oturum).

Kırılgan, ağır, gizlilik açısından hassas, hizmet şartlarına yakın.
**Çekirdek için reddedildi.** Yalnızca claude.ai web kullanımı gibi başka
yolu olmayan yüzeyler için, opt-in, ayrı bir "web collector" olarak
düşünülebilir — Faz 7'de karar.

### 1.9 `sdk-instrumentation`
**Örnekler:** tokentab (başarılı görev başına maliyet), openllmetry,
langfuse/opik/openlit SDK'ları, llm_cost_tracker.

Kesin ama uygulamanın enstrümante edilmesini gerektirir; kapalı CLI ajana
uygulanamaz (claude_telemetry bunu SDK'yı sarmalayarak yapıyor — ürünü
değiştiriyor). **Platformun kendi SDK'sı/MCP'si** için ve gelecekte ajan
çerçeveleri için geçerli. OTel `gen_ai.*` konvansiyonları (openllmetry)
birleşik modelin alan adları için referans.

### 1.10 `os-monitor`
**Örnekler:** ActivityWatch (bucket/heartbeat), exelban/stats, hypnguyen1209.

Aktif pencere/AFK/odak: "hangi projede çalışıyordum" ve "oturum süresi"
için tamamlayıcı. Gizlilik hassas; opt-in. ActivityWatch'ın
**watcher → bucket → event → query** mimarisi bizim collector katmanı için
doğrudan model.

### 1.11 `log-parsing` (Claude dışı ajan logları)
codeburn/token-monitor/agenttrace'in belgelediği yollar: Codex
`~/.codex/sessions/`, Gemini `~/.gemini/tmp/`, DeepSeek `~/.dsh/sessions/`,
Copilot VS Code `workspaceStorage/*/chatSessions/` + `~/.copilot/`.
jsonl-parsing ile aynı sınıf; adaptör başına yol keşfi + XDG/env override.

## 2. Özet matris

Puan: 1 (kötü) – 5 (iyi). Kanıt: yukarıdaki bölümler.

| Yaklaşım | Doğruluk | Güvenilirlik | Gizlilik | Performans | Kararlılık | Bakım | Sağlayıcı bağımlılığı | Kota % | Token | Maliyet | Gerçek zamanlı |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| api-polling | 5 | 3 | 4 | 5 | 3 | 3 | tam | ✅ | ❌ | ❌ | ~3 dk |
| stdin-statusline | 5 | 2 | 5 | 4 | 2 | 4 | tam | ✅ | kısmi | ❌ | anlık |
| jsonl-parsing | 4 (token) / 2 (maliyet) | 3 | 2 | 3 | 3 | 3 | format | ❌ | ✅ | tahmin | sn–dk |
| hooks | 5 (olay) | 3 | 2 | 2 (bloke riski) | 3 | 3 | tam | ❌ | dolaylı | ❌ | anlık |
| otlp (yerleşik) | 5 | 4 | 4 | 4 | 4 | 4 | tam (resmî) | ❌ | ✅ | **✅ gözlenmiş** | anlık |
| proxy | 5 | 1 | 1 | 2 | 1 | 1 | protokol | header? | ✅ | ✅ | anlık |
| sqlite-inspection | 2–3 | 2 | 2 | 3 | 2 | 2 | uygulama | değişken | tahmin | tahmin | dk |
| browser-scrape | 3 | 1 | 1 | 1 | 1 | 1 | arayüz | ✅ | ❌ | ❌ | — |
| sdk-instrumentation | 5 | 4 | 3 | 4 | 4 | 4 | yok | ❌ | ✅ | ✅ | anlık |
| os-monitor | 4 | 4 | 2 | 4 | 4 | 4 | yok | ❌ | ❌ | ❌ | anlık |

## 3. Platform için ön karar (Faz 7'de kesinleşir)

```
BİRİNCİL (varsayılan açık)
  ├─ otlp-receiver   : gömülü minik OTLP alıcısı → gözlenmiş token + maliyet + olaylar
  ├─ quota-poller    : sağlayıcı ucu, nazik (180 sn, backoff, rotasyon yok)
  └─ transcript      : artımlı JSONL → atıf (proje/oturum/model/araç)

İKİNCİL (opsiyonel, opt-in)
  ├─ statusline-tap  : CLI oturumu varken rate_limits (poller'ı uyutur)
  ├─ hooks           : bloke etmeyen olay yayıcı → gerçek zamanlı oturum istihbaratı
  └─ other-agents    : Codex/Gemini/Cursor adaptörleri (log/sqlite, 'estimated' etiketli)

ARAŞTIRMA MODU (açık uyarı, şifreli raw)
  └─ proxy           : header ve ham trafik incelemesi

REDDEDİLDİ
  ├─ token rotasyonu
  └─ browser-scrape (çekirdek için)
```

## 4. Faz 5'te doğrulanacaklar

1. ~~`claude_code.cost.usage` sunucu mu istemci hesabı mı?~~ **İstemci
   fiyat tablosu** (resmî doküman). Kapandı.
2. OTLP alıcısı kapalıyken Claude Code ne yapar? — dokümanda yok,
   **deneyle ölçülecek**.
3. Abonelik OAuth trafiğinde `anthropic-ratelimit-*` header'ları dönüyor
   mu? — rjwalters dolaylı kanıt veriyor (evet); **alan adları** claude-meter
   kaynak kodundan çıkarılacak.
4. ~~Hook zaman aşımı ve hata davranışı~~ **Belgelendi** (notes/02 §B). Kapandı.
5. `/api/oauth/usage`'ın gerçek istek limiti ve `Retry-After` verip
   vermediği — deneyle (nazikçe).
6. CodeZeno'nun "CLI'a token yenileme yaptırma" mekanizması — kaynak kod.
7. **Yeni:** Claude Code'da Codex `app-server` benzeri resmî yerel IPC var
   mı? (CodexQuotaSafe kalıbı.)
8. **Yeni:** `~/.claude/settings.json` `env` bloğu OTel değişkenlerini
   taşıyor mu? (Kurulum sihirbazı için.)
9. **Yeni:** Statusline `rate_limits` alanlarının resmî doküman adları
   (`docs/en/statusline`).

## §4-ek · Doğrulama durumu (2026-09-07)
| # | Deney | Durum |
|---|---|---|
| 1 | OTLP alıcı kapalıyken Claude Code davranışı | **Açık** — belge sessiz; Aşama 1'de canlı deney |
| 7 | claude-meter Authorization başlığı diske yazıyor mu | **Kapandı** — `sanitizeHeaders` temizliyor; gövdeler ham |
| 8 | `settings-reference`: `cleanupPeriodDays`, `modelPricing` | notes/02 §G-ek'e bakınız |
| 9 | `/api/oauth/usage` Retry-After | Kısmen — codeburn gövdede `retry_after` alanı okuyor (min 60 s); başlık adı doğrulanmadı; canlı deney nazikçe |
| 10 | OTel GenAI semconv ile alan hizası | **Kapandı** — notes/03 |
