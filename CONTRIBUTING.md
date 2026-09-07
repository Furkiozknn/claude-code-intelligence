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

## Testler
`uv run pytest`: şema/gizlilik (yasak anahtar, etiket), dedup, koruma yasası,
golden özetler, estimator backtest (kaydedilmiş snapshot fixture'ları),
dosya izinleri (POSIX), log redaksiyonu, ağ izin listesi.

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
