# Derin analiz · Astro-Han/claude-pace

**Okunan:** `claude-pace.sh` (ilk 260 satır), `docs/decisions/2026-05-20-quota-cache-removal.md`.
Bash + jq, tek dosya, MIT, 229★, plugin marketplace'te.

## Veri
Tek `jq` çağrısıyla stdin'den: `model.display_name`, `workspace.project_dir`,
`context_window.used_percentage/context_window_size/total_input_tokens`,
`cost.total_cost_usd`, `effort.level`, `rate_limits.{five_hour,seven_day}.
{used_percentage,resets_at}`. Ayarlar `~/.claude/settings.json`'dan
`--argjson` ile (Windows Git Bash'te process substitution çalışmadığı için
kabuk değişkeni üzerinden — belgeli).

`CLAUDE_CODE_AUTO_COMPACT_WINDOW` varsa context yüzdesi **sıkıştırma eşiğine**
göre yeniden hesaplanıyor ("compaction'a mesafe"); `total_input_tokens` yoksa
tam pencereye düşüyor.

## Pace formülü
```
d = u − (w − rm)·100 / w      # u: kullanım %, w: pencere dk, rm: kalan dk
d > 0 → ⇡d% (hızlı harcıyorsun)   d < 0 → ⇣|d|% (yavaşsın)
```
Basit, açıklanabilir, tahmin değil **oran**. Renk eşikleri 70/90.

## Karar: kota cache'i kaldırma (v0.9.0)
- v0.8.1 son `rate_limits` anlık görüntüsünü makine başına tek dosyada
  cache'liyordu. PR #14: kullanıcı bazı oturumlarda Claude Max, bazılarında
  Microsoft Foundry kullanıyor; Foundry oturumu (`rate_limits` yok) Max
  snapshot'ını okuyup **yanlış hesabın kotasını** gösterdi.
- Öneri (proje başına hash) reddedildi: 5s/7g **hesap seviyesi** veri;
  stdin'de hesap/sağlayıcı kimliği yok → cache'in sahibi kanıtlanamaz.
- **Karar:** fallback tamamen kaldırıldı; alan yoksa `--`. "`--` dürüst bir
  başarısızlık; başka hesabın kotası sessiz yanlış cevap. Kota izleyicide
  sessiz yanlış cevap yer tutucudan kötüdür." ~250 satır (symlink sertleştirme,
  kısmi snapshot reddi, atomik yazma) silindi.
- Yeniden getirme koşulu: stdin'de `account.id`/`subscription.id`/
  `provider.kind` gibi kararlı kimlik.

## Mühendislik notları
- Claude Code refresh gelince devam eden script'i **iptal ediyor** → temp
  dosya + `mv` atomik yazımı yarım kalıp dosya bırakıyordu (bir kullanıcıda
  **3 008** yetim temp dosyası). 5 sn TTL'li git cache için yırtık yazım
  kabul edilebilir → doğrudan `>` yazımı, symlink reddi.
- Cache yalnız kullanıcıya ait, symlink olmayan dizinde
  (`$XDG_RUNTIME_DIR` veya `~/.cache`); güvenli kök yoksa cache kapalı, paylaşılan
  `/tmp`'ye düşmüyor.
- Git bilgisi 5 sn cache; cache anahtarı `sha1(DIR)`.

## Platforma aktarılacaklar
1. **Hesap kimliği olmadan hesap seviyesi veriyi cache'leme** — platform
   kota snapshot'ını `user.account_uuid` (OTel) veya kimlik dosyasındaki
   `subscriptionType`+token parmak iziyle anahtarlamalı; yoksa gösterme.
2. Pace oranı: forecast motorunun en basit katmanı; her zaman açıklanabilir.
3. Statusline yüzeyi yazacaksak: **iptal edilebilir**, hızlı, temp dosya
   bırakmayan, Windows Git Bash'te çalışan tasarım.
4. Auto-compact penceresi farkındalığı.
