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
| 0 | Kurulum: depo, katalog aracı, prototip derslerinin aktarımı | — | ✅ |
| 1 | **Keşif** — ≥100 repo (hedef 150–300), 15 kategori, farklı teknik yaklaşımlar | 2–4 | ✅ 230 repo |
| 2 | **Puanlama** — 13 kriter/100 puan, her puan gerekçeli | 5 | 🔄 39/230 puanlı |
| 3 | **Veri toplama analizi** — yaklaşımların accuracy/reliability/privacy/… kıyası | 6 | 🔄 taslak v1 |
| 4 | **Top 20** — kategori çeşitliliği korunarak | 7 | ⬜ |
| 5 | **Derin analiz** — Top 20 kaynak kod seviyesi + iki referans repo özel inceleme | 8–9 | ⬜ |
| 6 | **Sentez** — pattern'ler, anti-pattern'ler, çözülmemiş problemler, rekabet analizi | 38 | ⬜ |
| 7 | **Mimari** — sistem/veri/event/collector/analytics/quota/forecast/anomaly/privacy/plugin/UI | 10–36, 39–40 | ⬜ |
| 8 | **Ürün spesifikasyonu** — product/UX/dashboard/CLI/TUI/alert | 22–23 | ⬜ |
| 9 | **Öz-eleştiri** — 18 soru, mimariyi yeniden optimize et | 41 | ⬜ |
| 10 | **İmplementasyon** — Stage 1–16, sırayla | 42 | ⬜ |
| 11 | **Benchmark → eleştiri → iyileştirme** döngüsü | 43, final | ⬜ |

**Faz 2 tamamlanma ölçütü:** Top-20 adayı olabilecek her repo `fetched`
ve puanlı; kategori başına en az 3 puanlı örnek. Shallow olanların tümünü
puanlamak gerekmiyor (230'un çoğu düşük yıldızlı türev).
**Faz 4 ölçütü:** 12 kategoriden ≥1'er örnek; her seçim için "neden bu,
neden daha yüksek puanlı X değil" yazılı.

---

## Araştırma katalog protokolü

- Yeni bulgular `research/inbox/batch-NN.json`, sonra
  `python research/tools/catalog.py ingest research/inbox/batch-NN.json`.
- URL'ye göre tekilleştirme otomatik; alanlar birleşir, derinlik yükselir.
- `depth`: `shallow` → `fetched` (README okundu) → `deep` (kaynak kod).
  **Puan yalnızca `fetched`+ için** — araç shallow'a puanı reddeder.
- Kanıtsız kriter boş kalır; `scored_weight` doldurulan ağırlığı gösterir.
- `python research/tools/catalog.py gaps` → Faz 1 ölçütü; `top 20` → sıralama;
  `report` → `research/reports/catalog.md`.
- Konsolda Türkçe için `PYTHONIOENCODING=utf-8`.

---

## Sıradaki işler (öncelik sırası)

1. **Faz 2 devam:** Top-20 adayı olup henüz `shallow` olanları fetch + puanla:
   stormzhang/token-tracker (509★), aqua5230/usage (309★), shanggqm/codexU
   (343★), sr-kai/claudeusagewin, Tendo33/cursor-usage-tracker, rjwalters,
   f-is-h/usage4claude, Golden0Voyager/kimi-code-usage (CLI+MCP+VSCode),
   bevis7781/CodexQuotaSafe (resmî app-server), zcquant (OTLP), NikiforovAll/
   ccdashboard (Aspire), lsvishaal/tokburn, tycho-cli, Ziit, telemetry-kit,
   cacheeconomics, VibeBill, mag123c/toktrack (hız iddiası).
2. **Faz 2:** `report` üret, `top 30`'a bak, kategori kapsamasını kontrol et.
3. **Faz 4:** Top 20 seçimi + gerekçe → `research/reports/top20.md`.
4. **Faz 5:** İki referans repo (CodeZeno, claude-meter) için kaynak kod
   incelemesi — `git clone --depth 1` ile yerel okuma; notlar
   `research/notes/deep/<owner-repo>.md`. Sonra Top 20'nin geri kalanı.
5. **Faz 5 doğrulama listesi** (notes/01 §4): OTel cost.usage kaynağı,
   alıcı kapalıyken davranış, rate-limit header'ları, hook zaman aşımı.
6. **Faz 6:** pattern / anti-pattern / çözülmemiş problem / rekabet tablosu.

---

## Günlük

### 7 Eylül 2026 — Faz 0 · Kurulum
- Depo açıldı. Prototip (`claude-quota-monitor`) döngüsü durduruldu; işi
  git'te (13 sürüm, 14 commit). Dersleri `research/notes/00-*`'a aktarıldı.
- `research/tools/catalog.py`: ingest / stats / gaps / list / score / top /
  report. Rubric MP §5 ile aynı (13 kriter, toplam 100).
- Seed: bu oturumda gerçekten görülen 41 repo (`batch-00-seed.json`).

### 7 Eylül 2026 — Faz 1 · Keşif ✅
- **Tur 1** (`batch-01`, 49 repo): 12 kategori araması — LLM maliyet,
  gözlemlenebilirlik, proxy, kota, geliştirici verimliliği, coding-agent,
  TUI, tray, redaction, zaman serisi, çapraz sağlayıcı, local-first.
- **Tur 2** (`batch-02`, 36 repo): adı geçen ama URL'si görünmeyen büyük
  projeler **uydurulmadı, fetch ile doğrulandı** (LiteLLM 58.2k★, Langfuse
  34.3k★, Opik 21.8k★, ActivityWatch 18.8k★, Phoenix 11.3k★, OpenLLMetry
  7.4k★, Helicone 6.1k★, Wakapi 4.4k★, OpenLIT 2.7k★). Boşluk kategorileri
  hedefli aramayla açıldı: hooks (disler, TechNickAI, karanb192), OTLP
  (acreeger, rockdarko, ColeMurray, li0nel, ccdashboard, aaraujodata),
  sqlite-inspection (cursor-clean, Tendo33, cursor-wrapped, cursor-chronicle).
  İki ayrı "tokburn" bulundu (JSONL vs proxy). codeburn (41 araç) bulundu.
- **Tur 3** (`batch-03`, 104 repo): GitHub topic sayfaları (claude-usage,
  ai-usage-tracker, token-tracker, llm-costs, quota-tracker, codex-usage,
  ai-cost-tracking). Kripto/bot/spam elendi. Yeni yüzeyler: ESP32 AMOLED
  ekran (vibepulse 187★), WiFi masa saati, GNOME Shell, Waybar, macOS notch,
  MCP sunucusu (llm-usage-mcp, kimi-code-usage), Codex Skill, mobil.
- **Sonuç:** 230 repo · 14 kategori hepsi ≥3 · 11 yaklaşım hepsi ≥2 ·
  `gaps` çıkış 0. 26 → 40 fetched.
- **Öğrenilen:** topic sayfaları arama motorundan 5–10× verimli; tek
  fetch'te 20 repo + yıldız + tek satır açıklama.

### 7 Eylül 2026 — Faz 2 · Puanlama (tur 1) 🔄
- 14 yeni README okundu ve toplam **39 repo** 13 kriterde puanlandı
  (`batch-04.json`, gerekçeli `score_notes`, `confidence` etiketi).
- **Kritik bulgular:**
  - **Claude Code'un yerleşik OTel çıkışı resmî maliyet metriği veriyor:**
    `claude_code.cost.usage` (model bazlı USD), `token.usage` (in/out/cache),
    `session.count`, `lines_of_code.count`, `commit.count`,
    `pull_request.count`, `code_edit_tool.decision` (acreeger). "Üç araç üç
    maliyet" sorununu Claude Code için çözebilir. Kaynağı doğrulanacak.
  - **vibe-bar** tahmini nokta değil **karar + güven bandı** olarak veriyor
    (Learning/Enough/Watch/At risk/Surplus); kota gözlemi + hız + tamamlanmış
    döngüler + çalışma saati kalıpları. §17–18 için en güçlü referans.
  - **claude-pace** "pace" = kullanım% − geçen süre%; veri yoksa `--`,
    cache'li yedek bilinçli reddedilmiş. Dürüstlük örneği.
  - **codeburn** (10.9k★) §21 öneri motorunun en olgun hali: israf
    kalıpları + A–F notu + geri alınabilir otomatik düzeltme + 3 gün sonra
    gerçek tasarruf raporu.
  - **disler** 12 hook olayının payload'larını belgeliyor (SubagentStart/
    Stop, PreCompact, PostToolUseFailure) — olay hattı referansı.
  - **tokentab** "başarılı görev başına maliyet"i eval assertion'larıyla
    ölçüyor, ≥30 görev/%95 GA eşiği; içerik alanlarını girişte reddediyor.
  - **caut** çıktıyı "AI ajanının tüketmesi için" JSON/Markdown veriyor;
    3 MB/10 ms/10 MB — performans çıtası.
  - **TokenTracker** üç yolu (hook + SQLite + JSONL) birlikte kullanan tek
    araç; "yeni sağlayıcı bir parser dosyası uzağında".
- **Faz 3 taslak v1** yazıldı: `research/notes/01-veri-toplama-yaklasimlari.md`
  — 11 yaklaşım × 8 boyut, özet matris, platform için ön karar
  (birincil: gömülü OTLP alıcı + nazik kota poller + artımlı transcript;
  ikincil: statusline-tap + bloke etmeyen hooks + diğer ajan adaptörleri;
  araştırma modu: proxy; reddedilen: token rotasyonu, scrape).

---

## Bilinen riskler / açık sorular

- `/api/oauth/usage` belgelenmemiş; şema değişebilir. Yedek ayrıştırıcı +
  ham görünürlük + fixture testi şart (prototipte uygulandı).
- OTLP alıcısı kapalıyken Claude Code'un davranışı bilinmiyor.
- Abonelik trafiğinde rate-limit header'ları var mı bilinmiyor.
- Puanlar README'ye dayalı (`confidence` medium çoğunlukta); Faz 5 kaynak
  kod okuması puanları değiştirebilir — değişince `score_notes`'a "rev" notu.
