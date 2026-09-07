# İlerleme Günlüğü — Claude Code Intelligence Platform

Bu dosya otonom çalışmanın hafızası. Her turda: (1) burayı oku, (2) aktif
fazın sıradaki parçasını yap, (3) bulguları gerekçelendirerek kaydet,
(4) commit at. Faz sırasını atlama; **araştırma bitmeden platform kodu
yazma** (araştırma araçları serbest).

**Kapsam:** `D:\Repolar\claude-code-intelligence`.
**Sınır:** GitHub'a yayınlama yok (`raporlar/ONAY-BEKLEYENLER.md`).
**Dil:** Türkçe. Kaynak kod yorumları ASCII olabilir; kullanıcıya görünen
metin düzgün Türkçe.
**Kullanıcı durumu:** 7 Eylül sabahı işe gitti; "durma, onay isteme,
döndüğümde her şeyi aktar" dedi. Döndüğünde `raporlar/`'a özet rapor yaz.

---

## Faz haritası (MASTER_PROMPT bölümlerine eşlenmiş)

| Faz | İçerik | MP § | Durum |
|---|---|---|---|
| 0 | Kurulum | — | ✅ |
| 1 | **Keşif** — ≥100 repo (hedef 150–300) | 2–4 | ✅ 232 repo |
| 2 | **Puanlama** — 13 kriter/100, gerekçeli | 5 | ✅ 55 puanlı (Top-20 adaylarının tümü) |
| 3 | **Veri toplama analizi** | 6 | ✅ v1 + resmî doküman doğrulaması |
| 4 | **Top 20** | 7 | ✅ `research/reports/top20.md` |
| 5 | **Derin analiz** — Top 20 kaynak kod + 2 referans repo | 8–9 | 🔄 2/20 (iki referans repo bitti) |
| 6 | **Sentez** — pattern / anti-pattern / çözülmemiş / rekabet | 38 | ⬜ |
| 7 | **Mimari** | 10–36, 39–40 | ⬜ |
| 8 | **Ürün spesifikasyonu** | 22–23 | ⬜ |
| 9 | **Öz-eleştiri** (18 soru) | 41 | ⬜ |
| 10 | **İmplementasyon** Stage 1–16 | 42 | ⬜ |
| 11 | **Benchmark → eleştiri → iyileştirme** | 43 | ⬜ |

---

## Araştırma katalog protokolü
- `research/inbox/batch-NN.json` → `python research/tools/catalog.py ingest …`
- `depth`: shallow → fetched (README) → deep (kaynak). Puan yalnız fetched+.
- `gaps` / `top N` / `report`. Konsol: `PYTHONIOENCODING=utf-8`.
- Testler: `python -m unittest research/tools/test_catalog.py` (9 test).

---

## Sıradaki işler (öncelik sırası)

1. **Faz 5 devam** — Top-20'nin kalan 18'i, klonlar scratchpad'de
   (`…/scratchpad/repos/`). Her biri için `research/notes/deep/<owner-repo>.md`
   (§8 başlıkları + "alınmaya değer mi"). Sıra ve odak:
   codeburn (parser sözleşmesi, act journal, grade) · ccusage (tekilleştirme,
   blocks) · toktrack (değişmez günlük cache) · tycho (yapısal gizlilik) ·
   Maciek (provenance etiketleri, --write-state şeması) · vibe-bar (forecast
   verdict/güven bandı) · claude-pace (bash; resmî alanlar) · codexU
   (app-server JSON-RPC) · ActivityWatch (bucket/event/heartbeat) · litellm
   (fiyat JSON şeması) · openllmetry (gen_ai semconv) · disler (olay şeması)
   · zcquant (OTLP JSON ayrıştırma) · agenttrace (sağlık formülü) ·
   TokenTracker (parser sözleşmesi) · cacheeconomics (çarpanlar) · VibeBill
   (eşleştirme skoru) · tokentab (etiketleme akışı).
2. **Faz 5 doğrulama deneyleri** (nazikçe, kendi makinede):
   a. OTLP alıcı kapalıyken Claude Code davranışı (küçük HTTP alıcı yaz,
      kapat, `[3P telemetry]` logunu gözle).
   b. `settings-reference` sayfası: `cleanupPeriodDays`, `modelPricing` şeması.
   c. `/api/oauth/usage` istek limiti: `Retry-After` var mı (tek 429'u
      gözlemek yeter; zorlamadan).
3. **Faz 6 sentez** — `research/reports/sentez.md`: pattern'ler,
   anti-pattern'ler, çözülmemiş problemler, MP §38 rekabet tablosu
   (özellik × bizim / en iyi mevcut / neden daha iyi / nerede onlar daha iyi /
   ne alınacak).
4. **Faz 7 mimari** — `docs/ARCHITECTURE.md` + `DATA_MODEL.md` +
   `EVENTS.md` + `COLLECTORS.md` + `PRIVACY.md` + `PLUGINS.md`; MP §10–36.
5. Faz 8–9, sonra Stage 1.

---

## Günlük

### 7 Eylül 2026 — Faz 0 · Kurulum ✅
Depo, katalog aracı (13 kriter/100), prototip dersleri (`notes/00`), seed 41.

### 7 Eylül 2026 — Faz 1 · Keşif ✅
batch-01 (49, 12 kategori) · batch-02 (36, fetch ile doğrulanmış büyük
projeler + hooks/OTLP/sqlite) · batch-03 (104, GitHub topic sayfaları).
**232 repo**, 14 kategori ≥3, 11 yaklaşım ≥2. Topic sayfaları arama
motorundan 5–10× verimli.

### 7 Eylül 2026 — Faz 2 · Puanlama ✅
- Tur 1 (batch-04): 39 repo. Tur 2 (batch-05): 16 repo. **Toplam 55.**
- **Araç hatası bulundu ve düzeltildi:** gelen kayıtta `depth` yoksa
  `shallow` varsayılıp mevcut `fetched` kaydın puanları sessizce
  düşüyordu (25 kayıt). Etkin derinlik = mevcut ∨ gelen; 9 testli
  `test_catalog.py` eklendi. (Kullanıcının ilkesi: hatayı düzeltme,
  sınıfını yok et.)
- Sıralama (özet): litellm 70.7 · langfuse 69.7 · codeburn 69.3 ·
  activitywatch 68.1 · opik/toktrack 67.2 · Maciek 66.9 · vibe-bar 66.8 ·
  phoenix 66.4 · tycho 66.3 · helicone 66.1 · ccusage 65.7 · codexU 65.4 …
  `research/reports/catalog.md`.

### 7 Eylül 2026 — Faz 3 · Veri toplama analizi ✅ (v1)
`notes/01`: 11 yaklaşım × 8 boyut, özet matris, ön karar. Resmî
dokümanlarla doğrulandı (`notes/02`):
- **OTel:** `claude_code.cost.usage` istemci tarafı fiyat tablosu ("satıcı
  tahmini"); `query_source`/`agent.name`/`skill.name`/`mcp_tool.name`
  öznitelikleri → atıf bedava; `api_request` olayı `cost_usd_micros` +
  `request_id`; `prompt.id`/`message.uuid`/`client_request_id`
  korelasyonu; prompt/yanıt varsayılan redakte; alıcı kapalıyken davranış
  belgelenmemiş; `rate_limits` yok.
- **Hooks:** 30+ olay; stdin'de token yok; `async:true` bloke etmez ve
  zaman aşımsız; çıkış 2 bloke eder; `prompt_id` OTel ile aynı anahtar;
  `PreCompact/PostCompact` gözlenmiş sıkıştırma sinyali.
- **Statusline:** `rate_limits.five_hour.used_percentage`/`resets_at`
  (epoch sn), yalnız Pro/Max ve ilk yanıttan sonra, pencere sıfırlanınca
  alan düşer; `cost.total_cost_usd` istemci tarafı, **`modelPricing`
  ayarıyla değiştirilebilir**; `context_window.used_percentage` yalnız girdi.
- **Settings:** `env` bloğu OTel değişkenlerini taşıyabilir (kullanıcı
  seviyesi her projede).
- **Rate-limit header'ları kaynak koddan kesinleşti** (`anthropic-
  ratelimit-unified-{5h,7d}-{utilization,reset,status,surpassed-threshold}`,
  `-status`, `-representative-claim`, `-fallback-percentage`, `-overage-*`).

### 7 Eylül 2026 — Faz 4 · Top 20 ✅
`research/reports/top20.md`: 20 repo, 12 kategori kapsaması, her seçim için
"neden bu / neden daha yüksek puanlı X değil", runner-up'lar, anti-pattern
vaka listesi, repo başına derin analiz planı.

### 7 Eylül 2026 — Faz 5 · Derin analiz 🔄 (2/20)
- **CodeZeno** (`notes/deep/CodeZeno-…md`): usage ucu → yalnız 404'te
  Messages header yedeği ("429'da kota harcama" testli kural); kimlik
  zinciri CLI → **Claude Desktop OSCrypt cache (DPAPI + AES-GCM)** → WSL;
  `claude -p .` ile token yenileme (gerçek çağrı!); veri modeli yalnız
  yüzde; atomik persist; `time_until_display_change`; tema/expression
  motoru (v1 için fazla); `limits[]` dizisini kullanmıyor.
- **claude-meter** (`notes/deep/abhishekray07-…md`): proxy tüm gövdeyi
  tamponlar, kanal dolunca düşürür; `Record` şeması; `session_id` isteğin
  `metadata.user_id`'sinden; günlük JSONL 0600; **kota birimi estimator'ı:
  aday sayaçlar (raw / no_cache_read / io_only / weighted /
  price_equivalent) × hesap genelinde kümülatif aralık × percentile bandı,
  <3 nokta dürüstlüğü** — en değerli fikir; ham gövde varsayılan diskte
  (Authorization header'ı da yazılıyor olabilir — doğrulanacak).
- RAW→NORMALIZE→ANALYSIS→ESTIMATION→VISUALIZATION ilkesi **doğru, iki
  düzeltmeyle**: ham veri kaynağa göre sınıflandırılmalı ve hassas olan
  yazılmamalı; estimation çıktısı dağılım + sürüm olmalı.

---

## Bilinen riskler / açık sorular
- `/api/oauth/usage` belgelenmemiş; şema değişebilir.
- OTLP alıcısı kapalıyken Claude Code davranışı bilinmiyor (deney).
- Claude Desktop token cache'ini çözmek güçlü ve hassas — opt-in, salt
  okunur, asla diske yazılmaz; README'de açık anlatım.
- Puanlar README'ye dayalı; kaynak kod okumaları puanları değiştirebilir
  ("rev" notuyla).
