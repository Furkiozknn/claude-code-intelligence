# Derin analiz · CodeZeno/Claude-Code-Usage-Monitor (Referans #1)

**Okunan:** `src/poller/claude.rs` (907 satır), `poller.rs`, `providers.rs`,
`models.rs`, `app_settings.rs`, `tray_icon.rs`, `poller/claude_desktop.rs`,
`theme_engine.rs` (ilk 250 satır), `theme_engine/theme_expression.rs`.
**Okunmayan:** `dashboard.rs`, `context_menu.rs`, `desktop_compositor.rs`,
`theme_rendering.rs`, `studio_app/*`, diğer sağlayıcı poller'ları
(codex/antigravity/opencode/cursor). Bunlara dair hükümler yalnızca
README ve dosya adlarından; işaretlendi.
**Sürüm:** v2.9.19 (2026-09-04), 115 dosya, Rust + windows-rs, MIT.

## §8 başlıkları

### Data Acquisition
- **Birincil:** `GET /api/oauth/usage` (Bearer + `anthropic-beta:
  oauth-2025-04-20`). Yalnızca `five_hour`, `seven_day`, `spend`
  ayrıştırılıyor — **`limits[]` dizisi kullanılmıyor** (severity,
  `is_active` bilgisi ziyan; prototipimiz bunu kullanıyor).
- **Yedek:** yalnızca uç **404/desteklenmiyor** dönerse `POST /v1/messages`
  (`max_tokens:1`, içerik `"."`, model zinciri haiku-3 → haiku-4.5) ile
  `anthropic-ratelimit-unified-*` header'ları. Kaynak koddaki karar:
  429/5xx'te **bilerek** yedeğe düşmüyor — "rate limit'e cevap olarak kota
  harcamak yanlış ve sorunu büyütür". Eksik `resets_at` alanlarını da bu
  yedekle dolduruyor.
- **Kimlik keşfi** (ucuzdan pahalıya, tembel): `~/.claude/.credentials.json`
  → **Claude Desktop token cache** (`%APPDATA%\Claude\config.json`
  `oauth:tokenCache`, OSCrypt v10 AES-GCM, anahtar `Local State`'te DPAPI
  sarmalı; `user:inference` kapsamlı en taze giriş) → WSL dağıtımları
  (`wsl -l -q`, `wsl -d X cat …`, UTF-16LE çözümü, 5 sn zaman aşımı).
- **Token yenileme:** süresi dolmuşsa `claude -p .` çalıştırıp (CLAUDECODE
  env'leri temizlenmiş, 30 sn) Claude Code'un yan etki olarak yenilemesi
  bekleniyor; bundled masaüstü CLI (`%APPDATA%\Claude\claude-code\<sürüm>\
  claude.exe`) de aranıyor. Desktop kaynağında yenileme yok. **Bu gerçek
  bir model çağrısı** — küçük ama kota tüketir.
- Kimlik değişim izleme: dosya için yol|boyut|mtime, Desktop için şifreli
  cache'in FNV-1a hash'i (config.json pencere konumu için sık yazılıyor).

### Data Model
`UsageSection{percentage, resets_at}` · `UsageData{session, weekly,
weekly_label?, monthly?, credits?, stale}` · `CreditsSection{percentage,
remaining, total}` · `AppUsageData = map<ProviderId, UsageData>` (eski
anahtarları tolere eden serde). **Yalnızca pencere yüzdeleri** — token,
maliyet, geçmiş, oturum yok. Kota-monitörü; istihbarat katmanı değil.
Codex için "öğrenilen payda" (`CodexCreditsState{balance, baseline}`:
bakiye yükselmesi = yükleme → yeni taban).

### Storage
`%APPDATA%\ClaudeCodeUsageMonitor\{settings.json, usage-cache.json,
codex-credits.json}`. `usage-cache.json = {updated_unix, poll_ok, data}`.
**Atomik yazım:** geçici dosya + `sync_all` + `MoveFileExW(REPLACE_EXISTING
| WRITE_THROUGH)`. Geçmiş **yok**.

### Processing
`poll()` → sağlayıcı başına en fazla 3 iş parçacığı (scoped threads +
mpsc) → `merge_poll_results` (bir sağlayıcı cevap verirse başarı) →
`carry_forward_failures` (başarısız sağlayıcının önceki değeri
`stale=true` ile taşınır). Hata sınıfları: `AuthRequired | NoCredentials |
TokenExpired | RequestFailed`. HTTP: ureq, native TLS, platform
doğrulayıcı, 30 sn. Tarih: chrono'suz el yazması ISO-8601.
`time_until_display_change`: yalnızca görünen birim (g/s/dk/sn)
değişeceği anda yeniden çiz — akıllı zamanlayıcı.

### Analytics — yok (yüzde + geri sayım). Forecasting — yok. Alerts —
balon bildirimi (`NIIF_WARNING`), tetik mantığı okunmadı.

### Visualization
Tema motoru: `ThemeDocument{schema_version:1, surfaces:[SceneObject]}`;
her nesne `render/visibility/x/y/width/height/rotation/corner_radius/gap`
**ifade** alanlarıyla, `Placement{reference: Monitor|Taskbar|SystemTray +
display:index, nest: Taskbar|TrayIcon|Desktop|Floating, anchors,
offset(_expression)}`. Renderer kalıcı struct'ı değil çözümlenmiş sahneyi
tüketiyor (bozuk girdi kurtarılabilir, tema dosyası taşınabilir). Tema
kökleri **gerçek bildirim alanı ikonu** olabiliyor (32-bit DIB alfa,
≤512 px; Explorer sırayı/taşmayı yönetiyor).

### Privacy
Yalnızca okur; token yalnızca Authorization header'ında. Desktop cache
çözme DPAPI ile **oturum açmış kullanıcı** olarak — teknik olarak
uygulamanın gizli anahtarını açmak; README'de açıkça anlatılmalı (bizde
opt-in olacak). Telemetri yok. Tek dış uç: api.anthropic.com (+ diğer
sağlayıcılar).

### Architecture
Sağlayıcı = `ProviderDescriptor{id, key, cache_key, display_name,
settings_description, native_menu_command_id, default_enabled}` +
`ProviderPoller{id, poll: fn, credential_watch: fn}` — **adaptör arayüzü
iki fonksiyon işaretçisi**. `ProviderSet` bit kümesi, "en az bir sağlayıcı
açık" değişmezi. Yeni sağlayıcı = descriptor + poller + ayar alanı
(`show_<x>` — ayar dosyasında sağlayıcı başına elle alan; ölçeklenmez).

### Performance
Tek exe, framework yok, Win32 doğrudan. Sorgu aralığı yalnızca
{1, 5, 15, 60 dk}, varsayılan **15 dk** (bizim prototip 3 dk; ucun
limiti düşünülürse 15 dk çok muhafazakâr, 3 dk gözlemde sorunsuzdu).

### Reliability
Kademeli kimlik kaynakları, stale taşıma, zaman aşımlı WSL çağrıları,
hata sınıflandırması, legacy ayar göçü (`legacy_*_pending` bayrakları).
Şema değişimine karşı: `UsageResponse` yalnızca 3 alan — bilinmeyen alan
sorun değil ama **yeni bilgi de görülmez**.

### Extensibility
Sağlayıcı ekleme mekanik ama tüm katmanlara dokunuyor (descriptor,
poller, settings alanı, tema anahtar listesi `format_usage_line`'da sabit
kodlu!). Tema/expression motoru kullanıcı tarafı özelleştirme için güçlü.

## §9 özel maddeler — alınmaya değer mi?

| Madde | Gözlem | Verdikt |
|---|---|---|
| Taskbar mimarisi | Tema kökü `SurfaceNest::Taskbar`; `desktop_compositor.rs` okunmadı | ⏸ Windows'a özel; platform çapraz olacak — **alınmaz**, fikir olarak "yüzey = yuva" soyutlaması alınır |
| Provider abstraction | Descriptor + 2 fn pointer + bit kümesi | ✅ **Alınır**, ama `capabilities()` ve `normalize()` eklenerek (MP §27) |
| Usage windows | session/weekly/monthly/credits; `weekly_label` ile "30d" gibi | ✅ Pencere adları sağlayıcıya göre değişir — modelde `window` serbest metin + tür |
| Countdown | `time_until_display_change` | ✅ **Alınır** — gereksiz yeniden çizim yok |
| Multi-monitor | `ReferenceTarget.display: usize` | ✅ Fikir alınır (yüzey → monitör indeksi) |
| System tray | Gerçek Shell_NotifyIcon; balon | ✅ Kalıp alınır (bağımlılıksız native) |
| Theme engine | Declarative sahne + ifade | ⏸ v1 için **fazla**; Ecosystem aşamasında "template + data context" olarak sadeleştirilmiş hali |
| Dashboard | `dashboard.rs` okunmadı | — |
| Configuration | Atomik yazım, göç bayrakları, değişmezler | ✅ **Alınır** |
| Provider adapters | 5 sağlayıcı | ✅ Codex/Antigravity/Cursor/OpenCode poller'ları Faz 7'de okunacak |
| Local credential discovery | CLI → Desktop cache → WSL, tembel | ✅ **Alınır, aynen** — özellikle Desktop cache (kullanıcımızın durumu) |
| Expression engine | 640 satır, min/max/clamp/if/lerp… | ⏸ Sonra |
| Context menus | okunmadı | — |
| Visual customization | Theme Studio | ⏸ Sonra |

## Eleştiri
1. `limits[]` dizisini yok sayarak ucun verdiği severity/is_active
   bilgisini kaybediyor — bizim prototip burada daha ileride.
2. Token yenilemek için gerçek bir prompt göndermek ("`claude -p .`")
   gri alan: küçük ama tüketim, ve kullanıcı bilmiyor.
3. Veri modeli yalnızca yüzde; geçmiş yok → tahmin, atıf, anomali
   imkânsız. Bir "kota widget'ı"; MP'nin istediği istihbarat katmanı
   değil.
4. Sağlayıcı anahtarları tema motorunda sabit kodlu (`format_usage_line`)
   — plugin mimarisiyle çelişiyor.
5. Rust + Win32 kalitesi yüksek; testler anlamlı (429'da yedeğe düşmeme
   testi gibi davranış testleri).

## Platforma aktarılacaklar (özet)
- Kimlik keşif zinciri (Desktop OSCrypt dahil) — **opt-in**, salt okunur.
- Hata sınıflandırması ve "429'da asla kota harcama" kuralı.
- `stale` bayrağıyla taşıma; `time_until_display_change`.
- Atomik JSON persist + göç bayrakları.
- Sağlayıcı descriptor kalıbı (genişletilmiş).
- Header adları (notes/02 §E).
