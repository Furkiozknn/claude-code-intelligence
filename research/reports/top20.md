# Top 20 — Faz 4 seçimi

Üretim: 7 Eylül 2026 · Girdi: 232 repo katalog, 55'i 13 kriterde puanlı
(`research/reports/catalog.md`). Seçim **yalnızca puana göre değil**;
MASTER_PROMPT §7'nin istediği kategori çeşitliliği korundu ve her seçim
için "neden bu, neden daha yüksek puanlı X değil" yazıldı.

## Seçim ilkeleri
1. İki referans repo (CodeZeno, claude-meter) zorunlu.
2. 12 kategorinin (usage analytics · quota intelligence · proxy ·
   observability · dashboard · desktop UI · TUI · cost analytics ·
   forecasting · anomaly detection · developer analytics · cross-provider)
   her biri en az bir repoyla temsil edilsin.
3. Aynı fikri tekrar eden büyük platformlardan (Langfuse/Opik/Phoenix/
   OpenLIT/Helicone) en fazla **bir** temsilci; yerel-öncelikli kişisel
   araç için mimari ilham dışında katkıları sınırlı.
4. **Kalıp değeri** yıldızdan önemli: 1★'lı ama tek bir doğru fikri
   uygulayan repo (tycho, VibeBill, tokentab) 10k★'lı genel araçtan önce
   gelebilir.
5. Anti-pattern örnekleri Top 20'ye girmez; ayrı listede incelenir.

## Liste

| # | Repo | Puan | Kategori yuvası | Neden seçildi | Neden daha yüksek puanlı X değil |
|--:|---|--:|---|---|---|
| 1 | CodeZeno/Claude-Code-Usage-Monitor | 64.2 | Quota intelligence · Desktop UI · **Referans #1** | Resmî uçlar, 5 sağlayıcı adaptörü, taskbar+tray+pano, tema/expression motoru, 14 dil, winget | Zorunlu |
| 2 | abhishekray07/claude-meter | 60.9 | Proxy · **Referans #2** | RAW→normalize→estimate katmanları, rate-limit header'ları, güvenli tahmin | Zorunlu |
| 3 | getagentseal/codeburn | 69.3 | Cost analytics · Recommendation · Cross-provider | 41 parser, israf kalıpları, A–F notu, geri alınabilir düzeltme, gerçek tasarruf raporu — §21'in en olgun hali | — |
| 4 | ryoppippi/ccusage | 65.7 | Usage analytics | Fiili standart (18.4k★), 18 araç, 5s blok projeksiyonu, statusline modu; prototipte ölçüldü | — |
| 5 | mag123c/toktrack | 67.2 | Usage analytics · Performance | 3 GiB/s, 0.04 s cache; Claude Code'un 30 günlük silmesine karşı değişmez günlük cache = **saklama** çözümü | — |
| 6 | vscarpenter/tycho-cli | 66.3 | Privacy · Usage analytics | İçerik **yapısal olarak** yakalanamıyor; cache ekonomisi; sınırları dürüst | — |
| 7 | Maciek-roboblog/Claude-Code-Usage-Monitor | 66.9 | TUI · Forecasting · Provenance | official/local_estimate/experimental etiketleri, P90 limit tespiti, --write-state versiyonlu snapshot | — |
| 8 | AstroQore/vibe-bar | 66.8 | Forecasting · Desktop UI · Cross-provider | Karar + güven bandı (Learning/Enough/Watch/At risk/Surplus); resmî kota + yerel maliyet harmanı; çalışma saati kalıpları | — |
| 9 | Astro-Han/claude-pace | 62.2 | Quota intelligence · Statusline | stdin rate_limits, sıfır ağ, pace = kullanım% − süre%; veri yoksa `--` | — |
| 10 | shanggqm/codexU | 65.4 | Quota intelligence · Desktop UI | Resmî app-server IPC (`account/rateLimits/read`) + SQLite + rollout — "resmî yerel kanal" kalıbı | — |
| 11 | ActivityWatch/activitywatch | 68.1 | Developer analytics · **Mimari referans** | server(buckets/events/heartbeats/query) + watchers + frontend; özel watcher API; MPL | — |
| 12 | BerriAI/litellm | 70.7 | Proxy/gateway · Pricing | `model_prices_and_context_window.json` ekosistemin fiyat kaynağı; gateway mimarisi; spend per key/team | En yüksek puan; ama bir "kullanım monitörü" değil — fiyat tablosu ve gateway referansı olarak |
| 13 | traceloop/openllmetry | 58.7 | Observability · Data model | `gen_ai.*` OTel semantik konvansiyonları → birleşik modelin (§13) alan adları | Langfuse (69.7)/Opik/Phoenix yerine: platform değil **standart** lazım; onlar runner-up |
| 14 | disler/claude-code-hooks-multi-agent-observability | 58.2 | Observability · Event pipeline | 12 hook olayı payload'ı; hook→HTTP→Bun→SQLite WAL→WS→Vue hattı (§12 referansı) | — |
| 15 | zcquant/claude-code-monitor | 47.9* | Observability · OTel receiver | Kendi OTLP alıcısı (HTTP/JSON + gRPC) tek Node süreci — Grafana'sız alım kanıtı | acreeger (59.4) yerine: acreeger metrik adlarını belgeliyor (notes/02'ye alındı) ama 4 konteyner; bize gömülü alıcı lazım |
| 16 | luoyuctl/agenttrace | 60.9 | TUI · Anomaly/health | Sağlık skoru, retry döngüsü, asılı oturum, "Limited" kanıt etiketi; anomali kategorisinin tek ürün-seviyesi örneği | — |
| 17 | xiufengsun/TokenTracker | 63.5 | Dashboard · Cross-provider · Collector | Hook + SQLite + JSONL **üç yolu birlikte**; "yeni sağlayıcı = bir parser dosyası"; 36 araç | token-monitor (60.6, 2k★) yerine: token-monitor plugin sistemi yok, Electron |
| 18 | Tanisha-Katara/cacheeconomics | 56.2 | Cost analytics · Cache | 0.1×/1×/1.25×/2× çarpanları, expiry/rebuild/marker kanıtı, TTL politika kıyası | Helicone (66.1) yerine: aynı cache analitiği ama **yerel** ve formülleri açık |
| 19 | JARACH-209/VibeBill | 54.3 | Developer analytics · Attribution | Olasılıksal atıf + güven işareti + **koruma yasası** (toplam = atıflı + israf + ek yük + kapsam dışı) | — |
| 20 | adididitagain/tokentab | 56.7 | Cost analytics · Outcome | "Başarılı görev başına maliyet" (§14) tek gerçek uygulaması; içerik alanlarını reddeder | — |

\* zcquant puanı düşük görünüyor çünkü `confidence: medium` ve
dokümantasyon/topluluk zayıf; seçilme sebebi puan değil **mimari kanıt**.

## Kategori kapsaması

| Kategori | Temsilciler |
|---|---|
| Usage analytics | ccusage, toktrack, tycho |
| Quota intelligence | CodeZeno, claude-pace, codexU |
| Proxy | claude-meter, litellm |
| Observability | openllmetry, disler, zcquant |
| Dashboard | TokenTracker, (codeburn desktop) |
| Desktop UI | CodeZeno, vibe-bar, codexU |
| TUI | Maciek, agenttrace, toktrack |
| Cost analytics | codeburn, cacheeconomics, tokentab |
| Forecasting | vibe-bar, Maciek, claude-pace |
| Anomaly detection | agenttrace (+ tokburn eşikleri runner-up) |
| Developer analytics | ActivityWatch, VibeBill |
| Cross-provider | codeburn, TokenTracker, litellm, vibe-bar |

## Runner-up'lar (Faz 6 sentezinde başvurulacak)

| Repo | Neden listede değil | Alınacak fikir |
|---|---|---|
| Langfuse / Opik / Phoenix / OpenLIT / Helicone | Ağır platformlar; kişisel local-first araç için mimari ilham dışı | Helicone: prompt-cache önek analitiği; OpenLIT: düzenlenebilir fiyat dosyası |
| jens-duttke/usage-monitor-for-claude | CodeZeno aynı yuvayı dolduruyor; prototipte zaten denendi | on_threshold/on_reset komut hook'ları; idle modu; tek exe |
| yahav10/claude-code-dashboard | Olgunluk düşük | Soket seviyesinde çıkış engeli + PII redaction (§25) |
| janekbaraniewski/openusage | Tarayıcı oturumu okuma | Binary/env/SQLite ile araç otomatik keşfi |
| Javis603/token-monitor | Plugin sistemi yok | Yüzen balon + iOS hub yüzeyleri |
| lsvishaal/tokburn | Küçük | 4 israf eşiği (>3× medyan, 3+ okuma, ≥%60 araç sonucu, >60 dk) |
| f-is-h/usage4claude | Session-key yaklaşımı kırılgan | Web+Code+Desktop+Mobile birleşik görünüm ihtiyacı |
| rjwalters/claude-monitor | 1 token harcayan ping | "Headroom" skoru; SQLite şeması |
| Dicklesworthstone/caut | Çerez okuma; katkı kapalı | 5 strateji sınıflandırması; ajan için JSON/MD çıktı; 3 MB/10 ms çıtası |
| bevis7781/CodexQuotaSafe | 2 commit | "Resmî CLI'a devret" + imza doğrulama |
| sr-kai/claudeusagewin | CodeZeno aynı yuva | WSL kimlik keşfi; uyarlanabilir 5/7/20 dk |
| Golden0Voyager/kimi-code-usage | Kimi'ye özel | Tek backend → CLI + MCP aracı + VS Code |

## Anti-pattern vaka listesi (Faz 6)
- **onllm-dev/onWatch** — token rotasyonuyla uç limitini aşma (mimari ve UX
  kalitesi yüksek; tek karar yüzünden dışarıda).
- **Gronsten/claude-usage-monitor** — headless Chromium scrape.
- **aqua5230/usage** — loglardan türetilen tahmini "kota" olarak sunma.
- **rjwalters** — kota harcayan ping (sınırda).
- **disler** — prompt/transcript içeriğini SQLite'a yazma (gizlilik).

## Faz 5 derin analiz planı (repo başına okunacak dosyalar)

| Repo | Okunacak | Cevaplanacak |
|---|---|---|
| CodeZeno | `src/poller/claude.rs`, `poller.rs`, `providers.rs`, `models.rs`, `theme_engine/theme_expression.rs`, `dashboard.rs`, `context_menu.rs`, `app_settings.rs` | Adaptör arayüzü; pencere/geri sayım; expression engine; token yenileme; çoklu monitör; tema |
| claude-meter | `internal/proxy/proxy.go`, `normalize/*.go`, `capture/types.go`, `storage/*.go`, `docs/plans/*estimator*`, `analysis/dashboard.py` | Header alanları; SSE normalizasyonu; raw/normalized ayrımı; estimator + güven |
| codeburn | provider parser yapısı, `act` journal, grade hesabı | Parser arayüzü; undo tasarımı; grade formülü |
| ccusage | JSONL parser, blocks hesabı, pricing yükleme | Tekilleştirme (message id?), blok algoritması |
| toktrack | cache şeması, simd-json kullanımı, audit | Değişmez günlük cache tasarımı |
| tycho | deserialize edilen tipler | "Yapısal gizlilik" nasıl garanti ediliyor |
| Maciek | provenance etiketleme, P90, --write-state şeması | Etiket taksonomisi; snapshot şeması |
| vibe-bar | forecast modülü | Karar eşikleri; güven bandı hesabı |
| claude-pace | tek bash dosyası | rate_limits alan adları (resmî kanıt) |
| codexU | app-server istemcisi | JSON-RPC metotları; kimlik keşfi |
| ActivityWatch | `aw-core` modeller, `aw-server` REST | Bucket/event/heartbeat şeması; query dili |
| litellm | `model_prices_and_context_window.json` şeması | Fiyat tablosu alanları; cache fiyat alanları |
| openllmetry | semconv sabitleri | `gen_ai.*` alan listesi |
| disler | hook script + server şeması | Olay şeması; SQLite tablo |
| zcquant | `otlp-receiver.js` | OTLP JSON ayrıştırma; metrik → günlük toplama |
| agenttrace | health skoru | Sağlık formülü; anomali sıralaması |
| TokenTracker | parser dizini, SessionEnd hook | Parser sözleşmesi |
| cacheeconomics | çarpan tabloları, reconciliation | Formüller |
| VibeBill | eşleştirme skoru | Olasılık ağırlıkları; koruma yasası uygulaması |
| tokentab | eval assertion, CI eşiği | "Başarılı görev" etiketleme akışı |
