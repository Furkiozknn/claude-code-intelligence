# Degisiklik gunlugu

Bicim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/), surumleme
[SemVer](https://semver.org/lang/tr/). Surum numarasinin tek kaynagi
`pyproject.toml` (`cci/__init__.py` ayni degeri tasir); `yayinla.yml`
etiketle surum uyusmazsa yayini durdurur.

## Yayimlanmamis

### Arayuz ve gizlilik
- README gorselleri gercek kullanim verisinden uretilmisti (gercek gunluk tutarlar,
  olay/transcript sayilari). Hepsi `scripts/ornek-veri.py`'nin yazdigi SENTETIK veriyle
  yeniden uretildi ve README'de oyle etiketlendi; `scripts/gorsel-uret.py` artik
  kullanicinin kendi dizinine bakamiyor. Uretici belirsiz `docs/reel/` kaldirildi.
- Yeni `scripts/demo-uret.py`: gercek `cci` komutlarini sentetik veride kosar,
  `docs/demo/demo.gif` ve kanit metnini uretir.
- README ilk ekrani: tek cumle, tek komutlu kurulum (`uv tool install`), demo,
  ne zaman kullanilir/kullanilmaz.
- `cci --help`: her alt komutun aciklamasi, ilk kullanim ornegi, cikis kodlari.
- `cci today`: veri var ama bugun kayit yoksa "veri yok" demiyor (cikis kodu 4 ayni).
- `cci scan`: Claude Code klasoru bulunamazsa nereye baktigini stderr'e yaziyor.
- `--data-dir` bir dosyayi gosterirse Python izi yerine kullanim hatasi (cikis 2).
- `cci session`: bulunamayinca `cci sessions`'a yonlendiriyor.

### Guvenlik
- OTLP alicisi: gzip govdesi siniri artik acilirken uygulaniyor. Once tamamen
  acilip sonra olculdugu icin 1 MB'in altindaki bir gzip bombasi yuzlerce MB
  bellek ayirtabiliyordu (testte 200 MB'lik govde: 437 MB tepe).
- OTLP alicisi: negatif `Content-Length` 400 donuyor. `rfile.read(-1)` boyut
  sinirini atlayip baglanti kapanana dek okuyordu.
- OTLP alicisi: `Origin` basligi tasiyan (yani tarayicidan gelen) istekler
  403. Acik bir web sayfasi, on ucus gerektirmeyen bir POST ile yerel depoya
  sahte kullanim/maliyet yazabiliyordu.
- Pano API token dosyasi 0600 izinle olusturuluyor; eskiden once umask ile
  (genelde 0644) yazilip sonra chmod'lanirdi.

### CI
- Testler desteklenen iki Python surumunde (3.12, 3.13) kosuyor.

## 0.0.1 (etiketlenmedi)

`pyproject.toml`'daki ilk ve su anki surum. Henuz etiketlenmedi ve PyPI'a
yayimlanmadi. Icerik: README'deki Stage 1-16 (model, adaptor sozlesmesi,
transcript/kota/OTLP toplayicilari, SQLite olay deposu, normalizasyon,
fiyat tablosu, pace/tahmin, uyari motoru, CLI, loopback API + pano).

