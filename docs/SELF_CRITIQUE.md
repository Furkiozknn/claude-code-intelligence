# SELF_CRITIQUE — MP §41'in 18 sorusu (Faz 9)

Tarih: 2026-09-07. Cevaplar dürüst; her cevabın sonunda gerekiyorsa **R-n**
revizyonu var. Revizyonlar §19'da toplanır ve belgelere işlenir.

1. **Gerçekten yeni bir sistem mi oluşturduk?** Kısmen. Algoritmaların çoğu
   (dedup, pace, harman, atıf, teşhis) mevcut repolardan. Yeni olan
   **bileşim ve disiplin**: kanıt sınıfı + `Figure` + koruma yasası + çok
   kaynaklı mutabakat (OTLP ⨯ transcript ⨯ kota) + öneri merdiveni + geri
   alınabilir eylem. Matris (sentez §4) hiçbir reponun beşini birlikte
   taşımadığını gösteriyor. Yenilik iddiası buna sınırlı.
2. **İki repo'yu birleştirip yeniden mi adlandırdık?** Risk gerçek: Core =
   "ccusage (transcript) + CodeZeno (kota)" gibi görünebilir. Farkı kanıtlayan
   şeyler Core kabul ölçütlerine bağlandı: OTLP birincil, `Figure`/withheld,
   koruma yasası `--strict`, `doctor`, hesap kimliği kuralı. Bunlar
   Stage 1–7'de yoksa **evet, yeniden adlandırmadır** → `IMPLEMENTATION_PLAN`
   kabul ölçütleri (R-1).
3. **Hangi fikirler hangi projelerden?** `sentez.md` §1 her kalıpta kaynak
   verir (58 kalıp); özet: zarf/dedup (tycho, ccusage), Figure (cacheeconomics),
   koruma yasası/atıf (VibeBill), forecast (vibe-bar), pace/`--` (claude-pace),
   pencere sınıflandırma (codexU), teşhis (agenttrace), sağlayıcı arayüzü/
   guard/act (codeburn), cache sürümü (toktrack), kapsam/LWW (TokenTracker),
   kimlik zinciri/429 kuralı (CodeZeno), estimator (claude-meter), tehdit
   modeli (tokentab), heartbeat (ActivityWatch), fiyat şeması (LiteLLM),
   semconv (OTel/openllmetry).
4. **Hangi fikirleri geliştirdik?** (a) dedup + sidechain + advisor + iterations
   tek kural seti; (b) `input`/`input_total` ikiliği (semconv uyumsuzluğunu
   çözer); (c) `Figure`'a estimator sürümü ve bant; (d) pencere sınıflandırma +
   hesap kimliği + authoritative birlikte; (e) forecast **backtest protokolü**
   (hiçbir repo yöntemini ölçmüyor); (f) act günlüğü + realized-vs-estimated'ı
   öneri motoruna bağlama; (g) tedarik zinciri uyarısı.
5. **Diğerlerinin çözemediği problemler?** Kota birimi (kimse kanıtlayamadı);
   üç kaynağın mutabakatı; rakamı dürüstçe **basmamak**; sağlayıcı değişimini
   fark etmek; çoklu hesap karışması.
6. **Biz hangi yeni problemi çözüyoruz?** "Tüm sinyaller verildiğinde şu anda
   ne yapmalıyım" sorusunu kanıtlı, geri alınabilir ve sonradan ölçülen bir
   cevapla; ve "bu sayıya güvenebilir miyim" sorusunu her sayıda.
7. **Hangi özellikler gereksiz?** HITL kontrol düzlemi, uzak kaynaklar, tema
   motoru, leaderboard, Desktop OSCrypt kimlik çözme (opt-in bile olsa Core'a
   yakın durmamalı), gölge model karşılaştırması (Intel), commit atıfı
   (Adv). **Traces (beta) alımı Core'dan çıkar** (R-2); Desktop kimlik Eco
   (R-3).
8. **Nerede over-engineering var?** (a) Event bus + replay Core'da: değer
   yüksek ama uygulama **basit** olmalı — SQLite `events` + in-proc pub/sub,
   çerçeve yok (R-4). (b) JSON-RPC eklenti taşıması → Stage 15'e (R-5).
   (c) Altı yüzey → Core yalnız CLI + statusline + snapshot dosyası; tray
   Stage 9'dan sonra (R-6). (d) `Figure` tipi karmaşık ama gerekçeli; kalır.
9. **Tahminlerimiz ne kadar güvenilir?** Henüz bilinmiyor; v1 pace tek
   başına açıklanabilir ama zayıf; v2 ancak ≥5 tamamlanmış döngüden sonra
   `medium`. Kural: `confidence=learning` iken hüküm yok, yalnız pace (R-7);
   backtest MAE/bant kapsaması `cci quota --backtest` ile yayınlanır; kota
   birimi yalnız bant.
10. **Observed ve estimated karışıyor mu?** Yapısal olarak hayır (`evidence_class`
    zorunlu, `Figure`). Riskli noktalar: `input_total` (derived) observed
    gibi okunabilir; statusline `cost.total_cost_usd` (vendor_estimated) ile
    bizim `cost.usd` (estimated) iki alan; UI rozeti metnin parçası. Golden
    rapor testinde rozetler doğrulanır (R-8).
11. **Privacy yeterli mi?** Şema düzeyinde güçlü. Zayıf noktalar: (a) hesap
    kimliği için kimlik dosyası hash'i — gizli değerden türetilmiş kimlik →
    **kaldırıldı**; yalnız OTel `user.account_uuid` (Core zaten OTLP ister),
    yoksa cache yok (R-9). (b) snapshot dosyası aynı kullanıcı süreçlerine
    açık — 0600 + sensitive alanlar snapshot'ta hash'li (R-10). (c) Research
    Mode ham gövdeler — 7 gün, ayrı dizin; kabul edilen risk, belgeli.
12. **Provider değişirse dayanıklılık?** Şema hash'i, bilinmeyen alan sayaçları,
    sınıflanamayan pencere, fixture testleri; `/api/oauth/usage` kaybolursa
    statusline `rate_limits` + (research) başlıklara düşüş yolu belgeli.
    **Anlamsal** değişim (aynı alan, yeni anlam) yakalanmıyor → kanaryalar:
    OTel vs transcript token eşitliği istek başına; pencere içinde kullanım
    monoton artmalı; `resets_at` süre sınıfı sabit (R-11).
13. **1 GB raw telemetry?** Core ham saklamaz. OTLP olayı ~1 KB → 1 GB ≈ 1 M
    olay → soru 14.
14. **1 M event?** SQLite `events` ~1.5 GB (payload JSON); normalize tablo
    ~300 MB; sorgular özetlerden (ms); replay ~5 k olay/sn → ~4 dk. Kabul.
    Tipik kullanıcı (2 k istek/gün) 1 M olaya ~1.5 yılda ulaşır.
15. **10 M event?** 15 GB kabul edilemez. Karar: `events` saklama 30 gün ve
    özet kararlılaştıktan sonra payload budaması (zarf + hash kalır); dayanıklı
    katman `usage_records`/`quota_snapshots` (365 gün) + özetler (süresiz);
    replay 30 günle sınırlı, daha eskisi özetlerden (R-12). Ölçüm: benchmark
    Stage 6'da 10 M sentetik olayla.
16. **Collector çökerse?** Görev izolasyonu, watchdog + üstel yeniden
    başlatma, `collector.health`; OTLP alıcı kapalıyken Claude Code tarafı
    belgesiz (U2 deneyi Stage 3'te); transcript izleyici boşluğu sonradan
    kapatır (dedup birleştirir); kota poller kaçırırsa `stale` yaş etiketi.
17. **Dashboard çökerse toplama sürer mi?** Evet: toplama daemon'da, yüzeyler
    ayrı süreç ve yalnız snapshot/API okur; snapshot dosyası daemon yaşadıkça
    yazılır.
18. **Provider API değişirse sistem anlar mı?** Sözdizimsel: evet (§12);
    anlamsal: R-11 kanaryalarıyla kısmen; tamamen değil — `doctor`
    "son doğrulama tarihi"ni gösterir ve fixture'lar tarihli.

## 19. Revizyon listesi (belgelere işlenecek)
| R | Değişiklik | Belge |
|---|---|---|
| R-1 | Core kabul ölçütleri: OTLP birincil, Figure/withheld, koruma yasası `--strict`, doctor, hesap kimliği kuralı | IMPLEMENTATION_PLAN |
| R-2 | Traces (beta) alımı Core dışı (Stage 3 opsiyonel bayrak) | ARCHITECTURE §8, EVENTS §3 |
| R-3 | Claude Desktop OSCrypt kimlik çözme Eco + ayrı bayrak | PROVIDERS §4 |
| R-4 | Event bus = SQLite tablo + in-proc pub/sub; çerçeve yok | EVENTS §6 |
| R-5 | JSON-RPC eklenti taşıması Stage 15 | EXTENDING §3 |
| R-6 | Core yüzeyleri: CLI + statusline + snapshot; tray/TUI/web Stage 9+ | ARCHITECTURE §8, PRODUCT |
| R-7 | `learning` iken hüküm yok; ≥5 döngü | ANALYTICS §2.2 |
| R-8 | Golden rapor testi rozetleri doğrular | CONTRIBUTING |
| R-9 | `account_key` yalnız OTel `user.account_uuid`; kimlik dosyası hash'i yok | DATA_MODEL §1.4, PRIVACY §4 |
| R-10 | Snapshot'ta sensitive alanlar hash'li; dosya 0600 | ARCHITECTURE §3, PRIVACY §5 |
| R-11 | Anlamsal kanaryalar (OTel↔transcript eşitliği, monotonluk, süre sınıfı) `doctor`'da | ARCHITECTURE §10, PROVIDERS §6 |
| R-12 | `events` 30 gün + payload budama; dayanıklı katman normalize + özet | PRIVACY §3, EVENTS §5 |
