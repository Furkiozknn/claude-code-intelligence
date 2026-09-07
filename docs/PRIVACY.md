# PRIVACY — sınıflandırma, saklama, tehdit modeli

Durum: Faz 7 taslağı. Kararlar: sentez D6; kanıt: tycho ADR 0001,
cacheeconomics allow-list, tokentab tehdit modeli, codeburn rıza parmak izi,
resmî `data-usage` sayfası (`notes/02` §H).

## 1. Sınıflar (alan düzeyinde)
| Sınıf | Tanım | Örnek alanlar | Varsayılan |
|---|---|---|---|
| `public` | Kimliksiz toplamlar | günlük token/maliyet toplamı, model dağılımı | saklanır, paylaşılabilir |
| `internal` | Kişiye ait ama içerik değil | session_id, prompt_id, model id, token sayıları, araç adları, süreler | saklanır, yerel |
| `sensitive` | Kimliklendirici veya bağlam sızdıran | proje yolu/adı, cwd, git dalı, dosya yolları, hesap kimliği, e-posta, hostname, pencere başlığı | hash/takma ad ile saklanır; ham yalnız kullanıcı açarsa |
| `secret` | Kimlik bilgisi ve içerik | access token, API anahtarı, prompt/yanıt metni, araç argümanları, dosya içeriği | **hiçbir tipte alan yok**; bellekte geçici, log'a asla |

Şema kuralı: her alan `privacy:` etiketi taşır; etiketsiz alan şema testinde
hata. `secret` etiketi bir alanda görünürse test başarısız (yapısal engel).

## 2. Ingest kapısı
1. Allow-list: olay türü başına izinli anahtar kümesi; dışı → red +
   `rejected_forbidden_key` (anahtar adı loglanmaz).
2. `FORBIDDEN_KEYS` özyinelemeli tarama: `content, prompt, messages, body,
   text, arguments, tool_input, transcript, response, completion, stdout,
   stderr, diff, patch` ve `*_content`, `*_text`.
3. Boyut: zarf ≤64 KB; OTLP gövdesi ≤1 MB (tokentab); büyük gövde → red + sayaç.
4. Statusline/hook betiklerinden gelen JSON'da yalnız beyaz listeli yollar
   okunur (`rate_limits`, `context_window`, `cost.total_cost_usd`, `model`,
   `prompt_cache`, `session_id`); `transcript_path` **açılmaz** (transcript
   izleyici ayrı ve kendi kurallarıyla okur).
5. OTLP: `api_request_body`/`api_response_body` olayları çekirdek alıcıda
   **düşürülür** (sayaçla). Research Mode ayrı alıcı ve ayrı depo.

## 3. Saklama (retention)
| Katman | İçerik | Süre | Not |
|---|---|---|---|
| Ham | OTLP gövdeleri, proxy yakalamaları | **Yalnız Research Mode**, 7 gün, ayrı dizin, 0700 | çekirdekte ham yok |
| Olaylar (`events`) | zarf + allow-list payload | **30 gün** (R-12); özet kararlılaşınca payload budanır, zarf + hash kalır | replay kaynağı (30 gün); 10 M olay senaryosu için |
| Normalize (`usage_records`, `quota_snapshots`) | `DATA_MODEL` tipleri | 365 gün | `sensitive` alanlar hash |
| Özetler (`daily_summary`, `session_summary`) | toplamlar | süresiz | `public/internal`; transcript silinse de kalır |
| Tahmin/uyarı geçmişi | `Estimate`, `Alert`, `Recommendation` | 365 gün | realized-vs-estimated için |
| Log | uygulama logu, redakte | 14 gün, 10 MB döngü | token desenleri silinir |

Silme: `cci purge --class sensitive --older-than 30d` ve `cci forget --project X`
(proje anahtarına bağlı tüm kayıt ve özetler). Kalıcı silme kullanıcı
komutuyla; otomatik silme yalnız süre dolunca ve log'a yazılarak.

## 4. Hesap kimliği ve çoklu hesap
- `account_key` = **yalnız** OTel `user.account_uuid` (R-9). Kimlik dosyası
  içeriğinden türetilen hash **kullanılmaz**: gizli değerden türetilmiş
  kimlik, sızarsa hesabı işaret eder ve gizli değerin varlığını doğrular.
  Core zaten OTLP gerektirdiğinden kimlik bu kanaldan gelir.
- Kimlik yoksa hesap seviyesi kota **saklanmaz**, yalnız canlı gösterilir ve
  `--` ile işaretlenir (claude-pace).
- E-posta/hesap id `sensitive`; UI'da varsayılan gizli.

## 5. Tehdit modeli
| Varlık | Tehdit | Önlem | Artık risk |
|---|---|---|---|
| Kimlik dosyaları | Okuma sırasında sızma | bellekte, redakte hata, asla diske/log'a, opt-in Desktop cache | süreç belleği dump'ı |
| Yerel DB | Aynı makinedeki başka kullanıcı/süreç | `~/.cci` 0700, dosyalar 0600 (Windows: kullanıcı ACL), WAL | yedek yazılımı kopyaları |
| Loopback API | Yerel zararlı süreç | yalnız 127.0.0.1, rastgele port + token dosyası 0600, CORS yok, WS origin kontrolü | aynı kullanıcı hakkındaki süreçler |
| Snapshot dosyası (`state/latest.json`) | Aynı kullanıcı süreçlerinin okuması | 0600; `sensitive` alanlar snapshot'ta **hash'li/takma adlı** (R-10); hesap kimliği yalnız kısaltılmış | okuyan süreç toplamları görür |
| OTLP alıcı | Sahte olay enjeksiyonu | loopback, boyut sınırı, şema doğrulama, kaynak sayaçları | yerel süreçler |
| Statusline/hook betikleri | Claude Code'u yavaşlatma/bloklama | fail-open, exit 0, ≤50 ms, zaman aşımı | ölçüm kaybı |
| Klonlanan araştırma repoları | `.claude/skills|hooks` enjeksiyonu (bu projede yaşandı) | klonlar scratchpad'de; `.claude/` çalıştırılmaz; README uyarısı | kullanıcı yanlış dizinde açarsa |
| Dışa aktarım (Eco) | İstemsiz veri gönderimi | varsayılan kapalı; alan anlamları listesi; rıza parmak izi (alan/hedef/kadans değişince yeniden); makbuz | hedef tarafın işlemesi |
| Web yüzeyi | XSS/CSRF | CSP, inline script yok, loopback, token | tarayıcı eklentileri |
| Fiyat yenileme | Tek dış çağrı (LiteLLM) | kullanıcı tetikler, HTTPS, hash doğrulama, bundled yedek | MITM (HTTPS'e bağlı) |

## 6. Anthropic'e giden veri (bilgilendirme)
Platform Anthropic'e **hiçbir şey göndermez**; Claude Code'un kendi operasyonel
telemetrisi (`DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`,
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`) kullanıcı kararıdır; `doctor`
bunların durumunu **gösterir**, değiştirmez.

## 7. Research Mode sınırları
- Ayrı ikili/komut (`cci research …`), ayrı dizin, ayrı şema; çekirdek DB'ye
  yazmaz; çıktısı yalnız **özet** (estimator parametreleri, dağılım) olarak
  çekirdeğe aktarılır.
- Proxy MITM yalnız kullanıcının kendi trafiği; başlıklar
  (`authorization`, `x-api-key`, `proxy-authorization`, `cookie`) diske
  yazılmadan silinir; gövdeler 7 gün.
- `OTEL_LOG_RAW_API_BODIES=file:<dir>` kullanılıyorsa dizin Research Mode
  dizinidir ve aynı saklama kuralı uygulanır.

## 8. Doğrulama testleri (CI)
- Şema testi: `secret` etiketi yok; her alan etiketli.
- Ingest testi: `FORBIDDEN_KEYS` içeren olay reddedilir; hata mesajı anahtar
  adını içermez.
- Log testi: örnek token desenleri (`sk-ant-…`, `Bearer …`, JWT) log
  çıktısında görünmez.
- Dosya izin testi (POSIX): 0700/0600.
- Ağ testi: izin listesi dışı host'a çıkış girişimi → hata.
