# ARCHITECTURE — Claude Code Intelligence Platform

Durum: Faz 7 taslağı (2026-09-07). Bu belge "ne ve neden"; alan şemaları
`DATA_MODEL.md`, olaylar `EVENTS.md`, adaptörler `PROVIDERS.md`, gizlilik
`PRIVACY.md`, analitik `ANALYTICS.md`, eklentiler `EXTENDING.md`, araştırma
`RESEARCH_MODE.md`. Kararların kanıtı `research/reports/sentez.md` (D1–D10).

## 1. Amaç ve sınırlar
Claude Code (ve diğer kodlama ajanlarının) kullanımını **gözlemler, ölçer,
tahmin eder ve öneri üretir**; yerel çalışır; içerik toplamaz; her sayının
kanıt sınıfı vardır. Yapmadıkları: sağlayıcı sınırlarını atlatmak, token
yenilemek, içerik depolamak, dışarıya veri göndermek (Eco aşamasında bile
yalnız açık rıza ile).

## 2. Bileşen haritası
```
 Kaynaklar            Toplayıcılar              Çekirdek (ccid, tek süreç)                    Yüzeyler
 ──────────           ────────────              ─────────────────────────────────            ──────────
 Claude Code ──OTLP──▶ OTLP alıcı ──┐                                                        CLI  (cci)
   ~/.claude/projects ▶ Transcript izleyici ─┤   Ingest kapısı ─▶ Event bus ─▶ Store          TUI
   statusline stdin ──▶ Statusline tap ──────┤   (allow-list,     (in-proc)    (SQLite WAL)    Web (loopback)
   hooks ─────────────▶ Hook alıcı ──────────┤    sınıf, boyut)       │           │            Tray / widget
 /api/oauth/usage ────▶ Kota poller ─────────┘                        ▼           ▼            Statusline betiği
 Codex/Gemini/… ──────▶ Sağlayıcı adaptörleri                    Analitik ─▶ Estimator'lar     (hepsi ince istemci)
                                                                     │            │
                                                                     ▼            ▼
                                                              Alert engine ─▶ Advisor ("ne yapmalıyım?")
                                                                     │
                                          Snapshot dosyası ◀── API (HTTP+WS, loopback) ──▶ yüzeyler
 Kesişen: Doctor/öz-gözlem · Config · Plugin host · Replay · (ayrı süreç) Research Mode
```

## 3. Süreç modeli
- **`ccid`** (daemon): tek süreç, toplayıcı başına async görev; çökme izolasyonu
  görev düzeyinde (bir toplayıcı düşerse diğerleri sürer, `collector.health`).
- **`cci`** (CLI): daemon çalışıyorsa API'den; yoksa DB'yi doğrudan salt okur
  (rapor komutları daemon'suz çalışır — ccusage/toktrack kullanım alışkanlığı).
- **Yüzeyler** ince istemci: snapshot dosyasını (`state/latest.json`, atomik)
  veya WS'i okur; hesap yapmaz. Statusline betiği yalnız snapshot dosyasını
  okur (≤50 ms, iptal edilebilir, temp dosya yok).
- **Research Mode** ayrı süreç ve dizin (`RESEARCH_MODE.md`).

## 4. Veri akışı (örnek: bir API isteği)
1. Claude Code `api_request` log olayını OTLP ile `127.0.0.1:<port>/v1/logs`'a
   yollar (5 sn içinde). Alıcı zarfa sarar → ingest kapısı (allow-list, ≤64 KB,
   sınıf etiketi) → `usage.request` olayı `events`'e yazılır → bus.
2. Normalizer `UsageRecord` üretir; dedup anahtarıyla `usage_records`'a upsert
   (kazanan kuralı). Aynı isteğin transcript kopyası dakikalar sonra gelir →
   aynı anahtar → birleşir (transcript `ephemeral_5m/1h` kırılımını ekler,
   OTel `cost_usd`'yi `vendor_usd` olarak korur).
3. Etkilenen oturum/gün özeti **kirli** işaretlenir; özetleyici yeniden
   hesaplar (saf fonksiyon), koruma yasasını doğrular.
4. Estimator'lar (pace, harman) yeni kota snapshot'ı veya özetle tetiklenir;
   `estimate.published`.
5. Alert engine kuralları değerlendirir (cooldown, dedupe); Advisor dikkat
   merdivenini günceller.
6. Snapshot yazıcı `state/latest.json`'ı atomik yazar (`generated_at`,
   `account_key`, `next_display_change_at`); WS yayınlar; tray günceller.

## 5. Depolama
`~/.cci/` (Windows: `%LOCALAPPDATA%\cci\`), 0700:
```
config.toml            events.db (SQLite WAL)  state/latest.json   logs/
cache/pricing.json     cache/manifests/        research/ (ayrı; yalnız Research Mode)
```
Tablolar: `events` (append-only) · `usage_records` · `quota_snapshots` ·
`session_summary` · `daily_summary` · `estimates` · `alerts` ·
`recommendations` · `collector_health` · `meta` (şema/summary/estimator
sürümleri). İndeksler: `(ts)`, `(session_id, ts)`, `(project_key, day)`,
`(dedup_key) UNIQUE`. Türetilmiş tablolar `events` + transcript'ten her zaman
yeniden üretilebilir (`cci replay`).

## 6. Dil ve dağıtım kararı (D10)
**Stage 1–2: Python 3.12** (uv; kullanıcının ortamı ve prototip burada;
OTLP protobuf/gRPC, SQLite, tray kütüphaneleri olgun; hızlı iterasyon).
Adaptör arayüzü **JSON-RPC/stdio ile dil bağımsız** olduğundan performans
kritik adaptörler (transcript tarayıcı) Rust'a taşınabilir; ccusage/toktrack
kanıtı hazır. Yeniden değerlendirme ölçütleri (Stage 6'da): 500 MB transcript
ilk taraması > 60 sn, boşta CPU > %1, tek ikili dağıtım zorunluluğu.
Dağıtım: `uv tool install` / `pipx`; tray için PyInstaller paket (Stage 9).

## 7. Ağ envanteri (tam liste — başka çıkış yok)
| Hedef | Ne için | Ne zaman | Kim tetikler |
|---|---|---|---|
| `https://api.anthropic.com/api/oauth/usage` | kota snapshot | ≥180 sn aralık, geri çekilmeli | poller (kullanıcı açar) |
| `https://raw.githubusercontent.com/BerriAI/litellm/…/model_prices_and_context_window.json` | fiyat tablosu yenileme | yalnız `cci pricing refresh` | kullanıcı |
| `127.0.0.1:<otlp_port>` (giriş) | OTLP alıcı | sürekli | Claude Code → biz |
| `127.0.0.1:<api_port>` (giriş) | yüzeyler | sürekli | yerel yüzeyler |
Diğer sağlayıcı adaptörleri kendi resmî uçlarını `PROVIDERS.md`'de listeler;
listede olmayan host'a çıkış girişimi test hatasıdır.

## 8. Aşamalar (MP §36 — overbuild yok)
| Aşama | Kapsam | Kalıplar |
|---|---|---|
| **Core (1)** | OTLP alıcı (metrik + log; **traces hariç**, R-2) + transcript + kota poller; UsageRecord/QuotaSnapshot; dedup; günlük/oturum özetleri; Figure; pace v1; snapshot dosyası (sensitive alanlar hash'li, R-10); **yalnız CLI + statusline** (R-6); doctor + anlamsal kanaryalar (R-11); PRIVACY kuralları | P1–P6, P8–P9, P11–P18, P21–P24, P26–P27, P30, P33, P35, P38, P40–P43, P46–P47, P49, P55–P57 |
| **Advanced (2)** | Tray/TUI/Web; hook ve statusline tap; oturum teşhisi; cache ekonomisi; commit atıfı; account/local kapsam; heartbeat; explainability | P7, P10, P19–P20, P25, P28–P29, P31–P32, P39, P45, P48, P50–P51, P58 |
| **Intelligence (3)** | Harman tahmin v2; estimator backtest; anomali + alert; Advisor; guard/act (geri alınabilir); realized-vs-estimated | P34, P36–P37, P52–P53 |
| **Ecosystem (4)** | Eklenti SDK; diğer adaptörler; uzak kaynaklar; dışa aktarım (semconv); ActivityWatch; HITL | P44, P54, remote |

## 9. Arıza mühendisliği (MP §35)
| Arıza | Davranış |
|---|---|
| OTLP alıcı kapalı/yavaş | Claude Code tarafı **belgesiz** (U2 deneyi); bizim taraf: bounded kuyruk (10k), dolunca en eskiyi düşür + `dropped` sayacı; asla geri basınç uygulayıp Claude Code'u bekletme |
| Kota ucu 429/5xx/şema değişimi | stale carry-forward (`stale=true`, yaşı görünür), geri çekilme, `provider.schema_change`; asla token yenileme/rotasyon |
| Transcript yarım satır / bozuk dosya | satırı atla + say; dosya bazında izole; mtime okunamazsa dahil et |
| DB bozulması | `events` + transcript'ten yeniden inşa; günlük özet cache ayrı dosya (toktrack) — geçmiş korunur |
| Saat kayması | `received_at` ile karşılaştırma; sınır dışı `ts` reddedilir; atıf penceresi 120 sn tolerans |
| Çoklu hesap/sağlayıcı | hesap kimliği yoksa saklama yok, `--` |
| Daemon çökmesi | yüzeyler son snapshot'ı yaş etiketiyle gösterir; watchdog yeniden başlatır |
| Estimator hatası | tahmin `withheld` + sebep; UI sayıyı basmaz |
| Eksik başlık / bozuk yanıt (kota ucu) | sınıflanamayan pencere → `authoritative=false`; JSON parse hatası → `transient`, ham hash loglanır (içerik değil); 3 ardışık bozukta `provider.schema_change` |
| Ağ hatası | üstel geri çekilme (60 → 900 sn), `stale` carry-forward, yaş görünür |
| Kimlik bilgisi yok / süresi dolmuş | `disconnected|expired` durumu, `--`; kullanıcıya "Claude Code'a giriş yap" — asla kendi yenileme |
| SQLite kilitli | `busy_timeout=5000`, WAL, tek yazar (daemon), CLI salt okur; kilit sürerse kuyruğa al + sayaç |
| Bozuk log satırı / dosya | satır atla + say; dosya izole; manifest o dosyayı "kısmi" işaretler, sonraki mtime'da yeniden |
| Disk dolu | yazma hatası → toplama **duraklar** (Claude Code etkilenmez), `collector.health=down(disk_full)`, snapshot'a uyarı; saklama budaması önce çalıştırılır |
| Dashboard çökmesi | yüzey ayrı süreç; toplama sürer (test: Stage 9) |
| Toplayıcı çökmesi | görev izolasyonu, watchdog 5 ardışık hatada 15 dk duraklatır ve raporlar |
| Saat dilimi | tüm zamanlar UTC; gün özetleri yerel gün ile ama TZ kaydı `daily_summary.tz`; TZ değişince ilgili günler yeniden |
| Reset tespit hatası | `resets_at` geriye gittiyse veya süre sınıfı değiştiyse `quota.reset_observed` yerine `provider.schema_change`; pace 180 sn tolerans; pencere kapanmadan utilization düşerse `authoritative=false` |

## 10. Öz-gözlemlenebilirlik (MP §34)
`cci doctor`: toplayıcı durumları ve gecikmeleri; sayaçlar (dropped, rejected,
unknown_field, parse_error, dedup_merged, sidechain_dropped, synthetic,
unknown_model, withheld_figures); DB boyutu ve büyüme; kendi CPU/bellek;
kota ucu son başarı/429 sayısı; Claude Code telemetri değişkenlerinin
durumu (yalnız gösterir); fiyat tablosu yaşı; şema/summary/estimator
sürümleri. Her sayı için "güvenebilir miyim" satırı. MP §34 ölçütleri
birebir: collector health, events/sec, processing latency (`received_at −
ts` ve ingest → özet süresi), storage size, parser errors, provider errors,
forecast errors (backtest MAE), dashboard latency (API p95), memory, CPU.
Anlamsal kanaryalar (R-11, `PROVIDERS.md` §6) burada raporlanır.

## 11. Performans bütçeleri (MP §33)
| Ölçüt | Hedef |
|---|---|
| Boşta CPU (daemon) | < %1 |
| Bellek (daemon) | < 150 MB |
| Statusline betiği | ≤ 50 ms (snapshot okuma) |
| OTLP ingest | ≥ 2 000 olay/sn (loopback) |
| Transcript ilk tarama | ≤ 60 sn / 500 MB; sonrası artımlı (mtime+manifest) |
| Sorgu p95 (günlük rapor) | < 200 ms |
| Snapshot yazımı | ≤ 5 ms, atomik |

## 12. Depo yapısı (MP §39)
```
cci/                 çekirdek paket (Python)
  collectors/  otlp/ transcript/ quota/ statusline/ hooks/
  adapters/    claude_code/ codex/ gemini/ …   (her biri fixtures/ ile)
  ingest/      allowlist.py schema.py classify.py
  model/       types (DATA_MODEL), figure.py, evidence.py
  store/       sqlite.py migrations/ replay.py
  analytics/   summaries/ diagnostics/ attribution/ cache/
  estimators/  pace_v1.py blend_v2.py registry.py backtest.py
  alerts/      rules/ engine.py sinks/
  advisor/     ladder.py actions/ journal.py
  api/         http.py ws.py snapshot.py
  surfaces/    cli/ tui/ web/ tray/ statusline/
  doctor/
  research/    proxy/ unit_estimator/ (ayrı giriş noktası)
docs/            bu belgeler
research/        Faz 1–6 çıktıları (katalog, notlar, raporlar)
tests/           şema/gizlilik/koruma yasası/backtest testleri
```

## 13. Faz 9'a taşınan sorular
Kimlik parmak izi güvenliği; OTLP protobuf kütüphanesi seçimi; tray için
Windows/Mac/Linux tek kod tabanı; snapshot dosyası çoklu daemon örneği
(profil anahtarı); Research Mode'un çekirdekle paylaşabileceği tek şey
(özet parametreler) — sınır testi.
