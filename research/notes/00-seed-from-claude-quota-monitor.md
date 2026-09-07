# 00 · Prototipten (claude-quota-monitor) aktarılan bulgular

Bunlar 6–7 Eylül 2026'da gerçek veriyle **gözlemlenmiş** şeyler; araştırma
evreninin ilk sabit noktaları. Kaynak: `D:\Repolar\claude-quota-monitor`
(13 sürüm, PROGRESS.md).

## 1. Resmî kota ucu — `GET https://api.anthropic.com/api/oauth/usage`

- Belgelenmemiş; Claude Code'un kendi HUD'u kullanıyor. Yetki:
  `Authorization: Bearer <accessToken>` + `anthropic-beta: oauth-2025-04-20`.
  Token `~/.claude/.credentials.json` → `claudeAiOauth.accessToken`
  (alanlar: `expiresAt`, `scopes`, `subscriptionType`).
- **Şema (gözlenen, 6 Eylül 2026):** üst seviyede `five_hour`, `seven_day`
  (`utilization`, `resets_at` ISO-8601, `limit_dollars`…), model-kapsamlı
  `seven_day_opus/sonnet/cowork/oauth_apps` (çoğu `null`), `extra_usage`,
  `spend`, `member_dashboard_available` ve **`limits` dizisi**:
  `kind` (`session` | `weekly_all` | `weekly_scoped`), `group`, `percent`,
  `severity` (`normal` | `warning` | `critical`), `resets_at`,
  `scope.model.display_name`, `is_active`.
- **`limits` dizisi birincil kaynak olmalı.** Severity'yi uç veriyor;
  eşik uydurmaya gerek yok. `is_active` = şu an fiilen daraltan limit.
- **Kod adı gürültüsü:** yayınlanmamış özelliklere ait anahtarlar dönüyor
  (`nimbus_quill`, `tangelo`, `iguana_necktie`, `cinder_cove`,
  `copper_kite`, `amber_ladder`, `juniper_tide`, `omelette*`). Ayrıştırıcı
  bunları kota sanmamalı. **Şema haber verilmeden değişebilir** →
  yedek ayrıştırıcı + ham veri görünürlüğü + gerçek yanıtla fixture testi.
- Uç, token başına düşük bir istek limitine sahip (~5/token diye
  raporlanıyor; issue anthropics/claude-code#31637). 180 sn aralık + üstel
  backoff (max 900 sn) sorunsuz çalıştı. **Token rotasyonu yapılmamalı.**
- Claude Code ≥2.1.x statusline'a `rate_limits.five_hour/seven_day`'i
  **stdin'den** veriyor — sıfır ağ çağrısıyla resmî yüzde. Ancak yalnızca
  CLI statusline'da; Claude Desktop agent mode ve VS Code native panel
  statusLine'ı render etmiyor (issue #55643, #20207, #21265 açık).

## 2. Yerel transcript'ler — `~/.claude/projects/<slug>/<session>.jsonl`

- `type: "assistant"` kayıtlarında `message.usage`: `input_tokens`,
  `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`,
  `cache_creation.ephemeral_{5m,1h}_input_tokens`, `output_tokens_details.
  thinking_tokens`, `server_tool_use.{web_search,web_fetch}_requests`,
  `service_tier`, `iterations[]`. Üst seviyede `timestamp`, `cwd`,
  `sessionId`, `gitBranch`, `version`, `isSidechain`, `parentUuid`.
- `cwd` alt-ajanlarda geçici klasör olabiliyor; proje kimliği için klasör
  slug'ı daha kararlı, gösterim için en sık `cwd`.
- **Atıf** (kotayı ne tüketti): pencere başlangıcı = `resets_at − 5s`;
  bu aralıktaki usage'ı proje/model/oturuma dağıt. Bu bir **oran
  tahmini**dir — sağlayıcı yüzdenin hangi tokenlardan geldiğini söylemiyor,
  başka cihaz/claude.ai kullanımı transcript'te yok.
- Cache **okuma** ağırlığa katılmadı (ucuz); girdi+çıktı+cache oluşturma
  ağırlık sayıldı. Bu bir varsayım; doğrulanmadı.

## 3. "Maliyet" sayılarının güvenilmezliği

Aynı JSONL'den üç araç üç farklı günlük "maliyet" üretti: ccusage $42.26,
phuryn/claude-usage $45.99, token-dashboard $168.45 (4×). Sebep: farklı
fiyat tabloları ve cache fiyatlandırma varsayımları. Hiçbiri "bu bir API
eşdeğeri tahminidir, abonelikte cebinden çıkan değil" diye vurgulamadı.
→ **Observed / Estimated ayrımı ve estimator sürümü zorunlu.**

## 4. Yanma hızı ve pencere sıfırlanması

- Pencere sıfırlanınca yüzde düşer; eğim yalnızca son sıfırlanmadan bu
  yanaki örneklerden hesaplanmalı, yoksa sıfırlanma "negatif tüketim"
  sanılır.
- Haftalık pencere gerçekten 7 gün (sıfırlanmasına "6g 21s" gözlendi);
  önceki turlarda görülen "5dk" bir önceki döngünün kuyruğuydu.
- Ölçülen hızlar: oturum %13.9→%35/sa (otonom döngü aktifken), haftalık
  %1.1–%3.1/sa. Yanma hızı için ≥300 sn ve ≥2 örnek şartı iyi çalıştı.

## 5. Mimari/ürün dersleri

- **Tek veri kaynağı, çok yüzey:** widget ve `--compact` Anthropic'e
  gitmedi, yerel sunucudan okudu. Çift sorgu yok. Platform için de doğru
  model: collector tek, yüzeyler çok.
- **Client tespiti şart:** kullanıcı Claude Desktop'taydı; CLI'a özel
  özellik (statusLine) görünmedi. Yüzey seçimi süreç incelemesiyle
  doğrulanmalı.
- **Ekran alanı birincil UX kriteri** (kullanıcı tray app'i "büyük" diye
  reddetti). Mini mod (yalnızca aktif limit) ve tarayıcı açmadan
  `--compact` iyi karşılandı.
- **Bağımlılıksız Windows bildirimi** PowerShell üzerinden WinRT toast ile
  mümkün; NotifyIcon yedeği. Açılışta "zaten dolu" pencereler için bildirim
  yağmasın diye ilk sorguda tohumlama.
- **Hata sınıfı: elle senkron kopya** (sürüm sabiti, iki tema bloğu,
  ayrı widget paleti, ASCII etiket). Çözüm: `light-dark()`, tek palet
  modülü, tutarlılık testleri. Platformda baştan uygulanacak.
- WCAG: gösterge rengi (3:1) ile metin rengi (4.5:1) ayrı aileler olmalı;
  ölçülmeden seçilen palet 10 yerde kaldı.

## 6. Bilinen açık sorular (araştırmanın cevaplaması gereken)

1. `/api/oauth/usage`'ın gerçek rate-limit'i nedir? Header'larla
   bildiriliyor mu? (claude-meter rate-limit header'larını okuyor.)
2. Anthropic API yanıt header'larında (`anthropic-ratelimit-*`) pencere
   bilgisi var mı ve OAuth/abonelik trafiğinde de dönüyor mu?
3. Proxy yaklaşımı (claude-meter) ile polling yaklaşımı arasında doğruluk
   farkı ne kadar? İkisi aynı anda çalıştırılıp kıyaslanabilir mi?
4. Claude Code hooks (`PreToolUse`, `PostToolUse`, `Stop`…) veri toplama
   için transcript taramaya göre ne kadar daha erken/ucuz?
5. OpenTelemetry export (Claude Code'un `CLAUDE_CODE_ENABLE_TELEMETRY`
   yolu) neler veriyor — token, maliyet, araç? Resmî ve kararlı mı?
6. Abonelik "yüzde"sinin arkasındaki birim ne? Token mı, ağırlıklı maliyet
   mi? (Üç aracın üç maliyeti bunu bilmediğimizi gösteriyor.)
   **Güncelleme (Faz 5, claude-meter estimator planı):** birim
   bilinmiyor ve bilinmediği kabul edilmeli. claude-meter bunu hipotez testi
   olarak kuruyor: aday sayaçlar (`raw` = in+out+cache_create+cache_read;
   `no_cache_read`; `io_only`; `weighted` cache_read×w) × hesap genelinde
   (oturumdan bağımsız) **kümülatif aralıklar** (utilization görünür
   değişene kadar kullanım biriktir; utilization 0.01 adımlarla kaba
   yuvarlanıyor) → her aralık için "implied cap" → cohort başına
   p10/medyan/p90; <3 nokta ise yalnız min/medyan/max. "Tek bir cap
   uydurma." Platformun kota→token dönüşümü bu disiplinle yapılmalı.
