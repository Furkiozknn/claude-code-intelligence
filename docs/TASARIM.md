# Tasarım: README ve CLI yenilemesi

## Hedef

Videodan ya da profilden gelen biri README'nin ilk ekranında (1) aracın ne yaptığını tek cümlede, (2) tek komutlu kurulumu, (3) gerçek komut çıktılı bir demoyu ve (4) ne zaman kullanılıp kullanılmayacağını görür. Gördüğü her çıktı gerçekten çalışan komuttan gelir ve **hiçbir kişinin gerçek kullanımından değildir**.

## Önce / sonra

| | Önce | Sonra |
|---|---|---|
| İlk ekran | "usage monitor değildir, büyük bir sistem hedefleniyor" tanımı; kurulum `uv sync` (klon şart) | tek cümle: nereye gitti / maliyet / kota; `uv tool install git+...` + `cci scan && cci daily` |
| Demo | 15 sn reel (üreticisi yok, veri kaynağı doğrulanamaz) + gerçek veriden terminal görseli | `docs/demo/demo.gif` (18 sn): `scan`, `daily`, `sessions`, `advise`; **sentetik örnek veri** etiketli, üreticisi `scripts/demo-uret.py` |
| Görseller | gerçek tutar/olay sayısı içeriyordu | sentetik veriden, README'de "sentetik örnek veri" notu |
| Karar yardımı | yok | "Ne zaman kullanılır / kullanılmaz" tablosu |
| `--help` | çoğu komut açıklamasız, örnek yok | her komutta açıklama, ilk kullanım örneği, çıkış kodları |
| Hata | Python izi, yanlış yönlendirme | anlaşılır mesaj, sözleşmedeki çıkış kodu |

## CLI akışı

```
cci scan        Claude Code kayıtlarını oku (artımlı)      → "tarandi: N kaynak, ..."
cci daily       gün × model: istek, token, ≈ maliyet       → tam çıktı
cci sessions    son oturumlar ve sağlık                    → tablo
cci advise      "şimdi ne yapmalıyım" (geri alınabilir)    → öneri
cci doctor      bu sayılara güvenilir mi                   → denetim
```

Kaynak yoksa `scan` nereye baktığını ve `CLAUDE_CONFIG_DIR`'i söyler; veri var ama bugün yoksa `today` bunu ayırt eder; yanlış `--data-dir` çökme değil kullanım hatası (çıkış 2) verir.

## Sentetik veri hattı

`scripts/ornek-veri.py` → belirlenimci sahte `projects/*.jsonl` (içerik alanı yok, 271 istek, 8 oturum, 5 gün, 3 model) → `CLAUDE_CONFIG_DIR` ile cci → gerçek çıktı. `gorsel-uret.py` (terminal.svg) ve `demo-uret.py` (GIF, dikey MP4, `komutlar.txt`) yalnız bu yoldan çalışır. `--bugune-kaydir` yalnız panonun "Bugün" bölümünü doldurmak için tarihleri kaydırır.

## Kimlik (FRK-OS) ve renk

Demo GIF ve video: siyah `#0e0d0b`, krem `#f1ece2`, sarı `#ffc21a`, camgöbeği `#19d3e6`, soluk `#9a958a`. Renkler `sosyal/uret/tema.mjs` "klasik" temasından alındı (geçiş/animasyon alınmadı: terminal daktilo akışı yeterli). Yazı tipi: JetBrains Mono (OFL; `ui-styling/canvas-fonts`, yerel dosya, indirme yok). Kontrast, siyah zemine karşı hesaplandı (WCAG göreli parlaklık): krem 16,5:1, sarı 12,0:1, camgöbeği 10,6:1, soluk 6,5:1, düz çıktı metni 11,8:1 — hepsi ≥4,5:1. Başlık yazı tipi (League Gothic) bu yenilemede kullanılmadı: README'de görsel başlığı yok, `assets/banner.svg` ortak üreticiden geliyor ve değiştirilmedi.

## Yapılmayanlar

Sürüm/etiket, PyPI, Pages, GitHub description/homepage, birleştirme: yok (Furki onayı gerekir). Geçmişteki gerçek-veri görsellerinin git geçmişinden silinmesi: yok (Furki kararı).
