# CONTRIBUTING

Durum: Faz 7 taslağı; Stage 1 ile birlikte kesinleşir.

## Kurulum
- Python 3.12 + `uv` (`uv sync`), Windows/macOS/Linux.
- Konsol Türkçe/Unicode: `PYTHONIOENCODING=utf-8`.
- Araştırma araçları: `python research/tools/catalog.py …` (bkz. `research/README.md`).

## Değişmezler (her PR'da kontrol)
1. **İçerik alanı yok.** Şemaya prompt/yanıt/argüman/dosya içeriği alanı eklenmez;
   `secret` etiketi görünürse şema testi kırılır (`docs/PRIVACY.md`).
2. **Her sayı kanıt sınıfı taşır**; para/tahmin alanları `Figure`
   (`docs/DATA_MODEL.md` §1). `released=false` sayı render edilmez.
3. **Koruma yasası**: her rapor `toplam = Σ parça`; `--strict` çıkış 3.
4. **Ağ envanteri** (`docs/ARCHITECTURE.md` §7) dışına çıkış yok; yeni host
   PR'da gerekçeyle listeye eklenir.
5. **Token yenileme/rotasyon yok, UA taklidi yok, kaynak dosyaya yazma yok.**
6. Türetimler saf fonksiyon (events, config, now enjekte); replay bit-eşit.

## Testler (MP §33 kategorileri)
`uv run pytest` — dizinler `tests/<kategori>/`:
| Kategori | Kapsam |
|---|---|
| collector | OTLP json/protobuf gövdeleri → olay; boyut/allow-list reddi; 429/401 davranışı; alıcı kapalı |
| parser | transcript satır türleri, bozuk satır, sentetik, iterations, sidechain |
| normalization | dedup (7 kopya → 1), `input`/`input_total`, model eşleme, pencere sınıflandırma |
| estimator / forecast | pace kenar durumları, harman ağırlıkları, backtest MAE fixture'ları, `learning` kapısı |
| storage | idempotent yazım, saklama/budama, WAL kilit, izinler (POSIX), replay bit-eşit |
| privacy | şemada `secret` yok, etiket zorunlu, `FORBIDDEN_KEYS`, log redaksiyonu, ağ izin listesi |
| provider compatibility | tarihli fixture'lar, `schema_verified`, şema hash değişimi tespiti, anlamsal kanaryalar |
| UI | golden raporlar (rozetler dahil), statusline ≤ 50 ms, snapshot şeması geriye uyum, kontrast |
| benchmarks | `benchmarks/` hedefleri (`docs/ARCHITECTURE.md` §11) |

## Fixture kuralları
Gerçek üründen, tarihli, **redakte**: içerik → `<redacted>`, kimlikler sahte
ama şekil korunur (`msg_…`, `req_…`), yollar `~/proj-a` gibi. Redaksiyon
betiği `tests/fixtures/redact.py`; ham fixture depoya girmez.

## Karar kayıtları
Mimari değişiklik → `docs/adr/NNNN-<konu>.md` (bağlam, karar, reddedilenler,
sonuç). "Gerçek kazanır": belge ile kod çelişirse gözlem kazanır ve belge
düzeltilir (tycho kuralı).

## Commit
Küçük, tek amaçlı; Türkçe başlık; davranış değişikliği geçmiş sayıları
oynatıyorsa `CHANGELOG`'da açık yaz. Otomatik oturumlarda:
`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Üçüncü taraf repo inceleme
Klonlar yalnız geçici dizinde; `.claude/` içeriği asla çalıştırılmaz
(bir klon bu projede skill enjekte etti). Bulgular `research/notes/deep/`'e
kaynak dosya adıyla.
