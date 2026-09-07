# Derin analiz · ActivityWatch (aw-core / aw-server)

**Okunan (web):** `aw_core/models.py` (Event modeli), belgeler "Buckets and
events". Kod klonlanmadı; kategori: **OS aktivite izleme** — Claude Code'a özgü
değil, "aktif zaman / hangi uygulama" bağlamı için referans. ~18.8k★.

## Veri modeli
- **Bucket:** `id` (`aw-watcher-<tür>_<hostname>`), `created`, `name`, `type`
  (olay şeması kimliği), `client` (izleyici yazılımı), `hostname`.
- **Event:** `id`, `timestamp` (UTC, **ms hassasiyet**, ISO8601), `duration`
  (saniye), `data` (bucket türüne bağlı JSON). Eşitlik `id` hariç; sıralama
  zaman damgasıyla.
- **Standart türler:** `currentwindow{app,title}`, `afkstatus{status: afk|
  not-afk}`, `web.tab.current{url,title,audible,incognito}`,
  `app.editor.activity{file,project,language}`.
- **Heartbeat:** izleyici periyodik olay yollar; sunucu, `data` **aynı** ve
  zaman farkı `pulsetime` içindeyse önceki olayla **birleştirir** (erken
  zaman damgası, süre ikisini kapsar). Böylece "5 sn'de bir aynı pencere"
  tek uzun olaya çöker — depolama ve sorgu maliyeti düşer.

## Claude Code için anlamı
- Claude Code'un `active_time.total` metriği "aktif zaman"ı kendi tanımıyla
  verir; ActivityWatch, kullanıcının **gerçekten önünde olduğu** zamanı (AFK)
  ve terminal/IDE penceresinin öndeliğini verir → "bekleme süresi" ve "insan
  vs ajan zamanı" ayrımı için dış kaynak.
- İsteğe bağlı **adaptör**: aw-server REST (`/api/0/buckets/<id>/events`)
  salt okunur; yalnız `afkstatus` ve `currentwindow.app` (başlık **alınmaz** —
  SENSITIVE).

## Platforma aktarılacaklar
1. **Heartbeat birleştirme** kalıbı: statusline/OTLP'den gelen tekrarlı durum
   anlık görüntüleri (aynı değer) tek aralığa çökertilebilir (`pulsetime`).
2. Bucket = (kaynak örneği, tür, host) → platformun `source_instance` +
   `stream_type` ayrımıyla aynı.
3. `afkstatus` ile "oturum aktif ama insan yok" (otonom döngü) tespiti —
   yalnız opt-in adaptör (Aşama 4).
