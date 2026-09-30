# Denetim: claude-code-intelligence (30 Eylül 2026)

Yenilemeden önce `master` (`af1a016`, sürüm 0.0.1) üzerinde, bu makinede (Windows 11, uv, Git Bash) ölçüldü. Ölçülmeyen bir şey yazılmadı.

**Veri kuralı.** Bu araç kullanıcının kendi kullanım verisini okur; bu yüzden denetimin tamamı `scripts/ornek-veri.py`'nin yazdığı **sentetik** Claude Code kaydı üzerinde yapıldı (`CLAUDE_CONFIG_DIR` sentetik klasöre, `--data-dir` geçici klasöre). Gerçek kullanıma hiç bakılmadı; bu belgedeki ve `kanit/` altındaki hiçbir tutar, yol ya da kimlik gerçek değil. Geçici klasör yolları çıktılarda `<tmp>` ile maskelendi. Ham çıktı diskte saklanmadı.

## Temiz ortamda kurulum ve ilk sonuç

Her satır boş `uv` önbelleği ve boş veri klasörüyle koşuldu.

| Yol | Süre | Sonuç |
|---|---|---|
| `uv tool install git+https://github.com/Furkiozknn/claude-code-intelligence` | 8,8 s ve 10,4 s (iki ayrı koşu) | `cci 0.0.1` |
| ardından `cci scan` + `cci daily` (271 kayıtlık örnek veri) | 3,7 s | 5 gün, model kırılımı |
| `uvx --from git+https://... cci scan` (tek seferlik, boş önbellek) | 14,3 s | 271 kayıt tarandı |
| `uv sync --locked` (kaynak klonu) | 7,8 s | |

"Tek komutla kur, bir dakikada ilk sonuç" tutuyor: kurulum ~9 s + ilk sonuç ~4 s. PyPI'da paket yok; kurulum GitHub'dan.

## README komutları (sentetik veri)

| Komut | Sonuç |
|---|---|
| `uv sync && uv run pytest` | 279 geçti, 3 atlandı (24,9 s). README "282" diyordu: geçen+atlanan, koşudan uyuşuyor |
| `cci scan`, `today`, `daily`, `sessions`, `session <id>`, `providers`, `doctor`, `advise`, `alerts`, `snapshot`, `statusline`, `tui --once` | hepsi çalıştı; çıkış kodları sözleşmeyle uyumlu |
| `cci quota`, `quota --forecast`, `--backtest`, `--poll` | kota verisi yokken `--`/boş döner, `quota` çıkış 4. `--poll` kimlik dosyası ister; **denenmedi** (gerçek hesaba gider, sentetik denetimde kapsam dışı) |
| `cci setup otlp|statusline` | yalnız gösterim modu denendi; `--write` gerçek `settings.json`'a yazacağı için **denenmedi** |
| `cci serve` + tarayıcı | pano açıldı; Bugün/Uyarılar/Sağlık bölümleri sentetik veriyi gösterdi |
| `cci run`, `widget`, `research proxy` | **denenmedi** (uzun ömürlü daemon / masaüstü penceresi / dış ağ) |
| `benchmarks/bench.py` | koşulmadı; `benchmarks/RESULTS.md` mevcut sayılar olarak bırakıldı |

## Hata mesajları ve `--help` (önce)

Kanıt: `kanit/claude-code-intelligence/once/komutlar.txt`.

1. `--help` iki komutu (`today`/`daily`) aynı cümleyle anlatıyordu; `sessions`, `quota`, `doctor`, `snapshot`, `statusline`, `setup` yardımsızdı; `--json` açıklamasızdı; ilk kullanım örneği ve çıkış kodları yoktu.
2. `--data-dir` bir **dosyayı** gösterince Python izi (`FileExistsError`) ve çıkış 1: kullanıcı hatası çökme gibi görünüyordu.
3. Veri var ama bugüne ait kayıt yokken `cci today` "veri yok (önce `cci scan`...)" diyordu: yanlış yönlendirme (veri zaten taranmıştı).
4. Claude Code klasörü bulunamayınca `cci scan` sessizce "0 kaynak" basıyordu; nereye baktığını söylemiyordu.
5. Bilinmeyen oturumda "oturum bulunamadi" ve bitti; nasıl bulunacağı söylenmiyordu.

Hepsi düzeltildi (`cci/cli.py`); çıkış kodları ve stdout sözleşmesi değişmedi (yeni ipuçları stderr'e ya da mevcut mesaja eklendi). 5 yeni test: 279 → 284 geçti (atlanan 3 aynı), README/`project-meta.json` toplamı 282 → 287.

## Görseller ve gizlilik (asıl bulgu)

Yenilemeden önceki README görselleri **gerçek kullanım verisinden** üretilmişti:

- `assets/terminal.svg`: gerçek `cci daily` çıktısı (gerçek günlük tutarlar ve token sayıları).
- `assets/pano-ekran-goruntusu.png`: gerçek depo (olay sayısı, transcript sayısı).
- `docs/reel/reel.gif|mp4`: üreticisi depoda yoktu, içeriği doğrulanamadı.

Üçü de sentetik veriyle yeniden üretildi (`scripts/gorsel-uret.py` artık yalnız sentetik veriyle çalışıyor; gerçek dizine bakamıyor) ya da kaldırıldı (reel). Yeni demo `scripts/demo-uret.py`. Dosyalar **git geçmişinde duruyor**; geçmişi yeniden yazmadan silinmez (Furki kararı, bkz. rapor).

Ayrıca bulundu, dokunulmadı: `research/notes/00-seed-from-claude-quota-monitor.md` bir günlük gerçek maliyet karşılaştırması içeriyor (kapsam dışı: görsel/README değil).

## Sızıntı taraması

Depo diff'i (eklenen satırlar), `kanit/claude-code-intelligence/`, `sosyal/medya/projeler/claude-code-intelligence/` ve yeni `terminal.svg` metni şu kalıplarla tarandı: kullanıcı adı, e-posta, `C:\Users`, `/Users/`, `AppData`, `sk-`, `ghp_`, `token=`, `USD`, `$` tutarları. Sonuç: yalnız sentetik `$` tutarları (beklenen) ve genel `%LOCALAPPDATA%` yardım metni; kullanıcıya ait yol/kimlik yok. PNG/GIF/MP4 kareleri gözle kontrol edildi.

## Ekosistem denetimi (#19)

Günlük konuda (22 Eylül) bu depoya ait açık bulgu yok; tek bulgu profil deposuna ait. Kapatılacak bir şey yok.
