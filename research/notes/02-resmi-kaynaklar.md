# 02 · Resmî kaynaklardan doğrulanmış gerçekler

Kaynak: Claude Code dokümanları (7 Eylül 2026'da okundu). Bu dosya
"gözlenmiş/resmî" bilginin referansı; mimari kararlar buraya dayanır.
Doküman değişebilir — tarih ve URL saklanıyor.

## A. OpenTelemetry çıkışı — `https://code.claude.com/docs/en/monitoring-usage`

### Etkinleştirme
```
CLAUDE_CODE_ENABLE_TELEMETRY=1
OTEL_METRICS_EXPORTER=otlp          # otlp | prometheus | console | none
OTEL_LOGS_EXPORTER=otlp             # otlp | console | none
OTEL_EXPORTER_OTLP_PROTOCOL=grpc    # grpc | http/json | http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer …"   # isteğe bağlı
```
Aralıklar: metrik 60 000 ms, log 5 000 ms, trace 5 000 ms (env ile ayarlanır).

### Metrikler
| Ad | Birim | Not |
|---|---|---|
| `claude_code.session.count` | — | |
| `claude_code.lines_of_code.count` | — | ekleme/silme |
| `claude_code.pull_request.count` | — | |
| `claude_code.commit.count` | — | |
| `claude_code.cost.usage` | USD | **istemci tarafı fiyat tablosuyla hesaplanır** |
| `claude_code.token.usage` | token | `type`: input / output / cacheRead / cacheCreation |
| `claude_code.code_edit_tool.decision` | — | `tool_name` Edit/Write/NotebookEdit, `decision` accept/reject, `source`, `language` |
| `claude_code.active_time.total` | s | |

**Maliyet öznitelikleri:** `model`, `query_source` (main / subagent /
auxiliary), `speed`, `effort`, `agent.name`, `skill.name`, `plugin.name`,
`marketplace.name`, `mcp_server.name`, `mcp_tool.name`.
Token öznitelikleri aynı + `type`.

→ **Atıf bedava:** hangi ajan, hangi skill, hangi MCP aracı, ana/alt-ajan
ayrımı metrik özniteliği olarak geliyor. Transcript taramaya gerek kalmadan
proje-dışı boyutlar (ajan/skill/MCP) elde edilir. Proje boyutu için
`session.id` + `cwd` (olaylardan) gerekir.

**Ortak öznitelikler:** `session.id`, `app.version`, `app.entrypoint`,
`organization.id`, `user.account_uuid`, `user.account_id`, `user.id`
(anonim, `~/.claude.json`'da), `user.email` (OAuth'ta), `terminal.type`,
`OTEL_RESOURCE_ATTRIBUTES`.

### Olaylar (log kayıtları)
| Olay | Öznitelikler |
|---|---|
| `claude_code.user_prompt` | prompt metni (varsayılan **redakte**), uzunluk, komut adı/kaynağı |
| `claude_code.assistant_response` | yanıt metni (varsayılan redakte), uzunluk, model, request_id |
| `claude_code.tool_result` | tool_name, tool_use_id, success, **duration_ms**, error_type |
| `claude_code.api_request` | model, **cost_usd, cost_usd_micros**, tokens, request_id, speed |
| `claude_code.api_error` | error, status_code, attempt, request_id |
| `claude_code.api_refusal` | model, stop_reason, category, server_fallback_hop |
| `claude_code.api_request_body` / `api_response_body` | ham JSON (yalnız `OTEL_LOG_RAW_API_BODIES`) |
| `claude_code.tool_decision` | tool_name, decision, source: config/hook/user_permanent/user_temporary/user_abort/user_reject |
| `claude_code.permission_mode_changed`, `auth`, `mcp_server_connection` | |

**Korelasyon:** `prompt.id` (bir kullanıcı prompt'undan doğan tüm olaylar),
`message.uuid` (transcript girdisi), `client_request_id` (HTTP'de
`x-client-request-id`).

→ `api_request` olayı **istek başına** token+maliyet+request_id veriyor;
`tool_result` **araç süresi** ve başarı/hata veriyor. Yani "hangi prompt
kaç istek, kaç token, kaç saniye araç" tamamen resmî olaylardan çıkıyor.

### Gizlilik ve kardinalite
- Varsayılan: prompt ve yanıt metni **redakte**. Açmak için
  `OTEL_LOG_USER_PROMPTS=1`, `OTEL_LOG_ASSISTANT_RESPONSES=1`,
  `OTEL_LOG_TOOL_DETAILS=1` (araç parametreleri, bash komutları, skill/MCP
  adları), `OTEL_LOG_TOOL_CONTENT=1`.
- `CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH` varsayılan 61 440 (60 KB).
- Kardinalite: `OTEL_METRICS_INCLUDE_SESSION_ID` (varsayılan true),
  `_INCLUDE_VERSION` (false), `_INCLUDE_ACCOUNT_UUID` (true),
  `_INCLUDE_ENTRYPOINT` (false), `_INCLUDE_RESOURCE_ATTRIBUTES` (true).

### Bilinmeyenler (dokümanda yok)
- **Alıcı erişilemezken davranış** belgelenmemiş; exporter hataları debug
  logunda `[3P telemetry]` olarak görünüyor. Tampon/at/yeniden dene/bloke —
  **deneyle ölçülecek** (Faz 5).
- `rate_limits` telemetride **yok**. Kota için OTel yeterli değil.

### Bizim için anlamı
1. `cost.usage` **gözlem değil, satıcı tahmini** ("vendor-estimated"):
   Claude Code'un kendi fiyat tablosu. Yine de tek ve tutarlı bir kaynak —
   ccusage/token-dashboard'un farklı tablolarına göre tercih edilir.
   Veri modelinde `source: claude_code_otel`, `confidence: high`,
   `kind: estimated` olarak taşınmalı.
2. Gömülü OTLP alıcısı (HTTP :4318 + gRPC :4317) ile hem metrik hem olay
   toplanır; Grafana yığınına gerek yok (zcquant kanıtı).
3. Kullanıcı env değişkenlerini ayarlamalı — kurulum sihirbazı bunu
   `~/.claude/settings.json` `env` bloğuna yazabilir (doğrulanacak: settings
   env'i OTel değişkenlerini destekliyor mu).

## B. Hook'lar — `https://code.claude.com/docs/en/hooks`

### Olaylar
Oturum: `SessionStart`, `SessionEnd`, `Setup` · Tur: `UserPromptSubmit`,
`Stop`, `StopFailure` · Araç: `PreToolUse`, `PostToolUse`,
`PostToolUseFailure`, `PermissionRequest`, `PermissionDenied`,
`PostToolBatch` · Ajan/görev: `SubagentStart`, `SubagentStop`,
`TaskCreated`, `TaskCompleted`, `TeammateIdle` · Yapılandırma:
`ConfigChange`, `InstructionsLoaded`, `CwdChanged`, `FileChanged` ·
Diğer: `Notification`, `MessageDisplay`, `PreCompact`, `PostCompact`,
`PreModelSwitch`, `PostModelSwitch`, `Elicitation`, `ElicitationResult`,
`WorktreeCreate`, `WorktreeRemove`, `UserPromptExpansion`.

### Girdi (stdin JSON) — ortak alanlar
`session_id`, `prompt_id`, `transcript_path`, `cwd`, `permission_mode`,
`hook_event_name`, `effort.level`; alt-ajanda `agent_id`, `agent_type`;
araç olaylarında `tool_name`, `tool_input`, `tool_use_id`.
`SessionStart.match_value`: startup | resume | clear | compact | fork.
`SessionEnd.match_value`: clear | resume | logout | prompt_input_exit | other.
`Stop.last_assistant_message`.

**Token kullanımı hook girdisinde YOK.** Token için `transcript_path`
okunur veya OTel `api_request` olayı kullanılır.

### Çıkış kodu ve bloke etme
- 0: başarı; stdout JSON ise yapısal kontrol.
- **2: eylemi bloke eder** (PreToolUse araç çağrısını, UserPromptSubmit
  prompt'u, Stop/SubagentStop durmayı, TaskCreated'ı geri alır;
  PostToolUse'ta stderr Claude'a gösterilir). PermissionRequest'te 2
  dikkate alınmaz.
- Diğer sıfır dışı: çoğu olayda bloke etmez.
- **Zaman aşımı:** command/http/mcp_tool 600 s, prompt 30 s, agent 60 s;
  UserPromptSubmit/PreModelSwitch/PostModelSwitch 30 s; MessageDisplay 10 s.
- **`"async": true`:** bloke etmez, zaman aşımı uygulanmaz.
  `"asyncRewake": true`: arka planda çalışır, çıkış 2 ise Claude'u uyandırır.

### Bizim için anlamı
1. Gözlemlenebilirlik hook'u **daima `async: true`** ve **daima çıkış 0**
   olmalı; alıcı kapalıysa kuyruğa yazıp sessizce çıkmalı. Aksi hâlde
   kullanıcının iş akışını bozarız.
2. `prompt_id` OTel'deki `prompt.id` ile aynı — hook olayları ve OTel
   olayları **tek anahtarla birleştirilebilir**.
3. `SessionStart.match_value=compact` ve `PreCompact/PostCompact` →
   context sıkıştırma olayları; token-dashboard/tokburn'ün "uzun oturum →
   compaction" sezgisi yerine **gözlenmiş** compaction sinyali.
4. `SubagentStart/Stop` + OTel `query_source=subagent` → alt-ajan
   maliyeti gözlenmiş.

## C. Statusline stdin JSON — `https://code.claude.com/docs/en/statusline` (resmî)

| Alan | Anlam |
|---|---|
| `rate_limits.five_hour.used_percentage` / `.seven_day.used_percentage` | 0–100 |
| `rate_limits.five_hour.resets_at` / `.seven_day.resets_at` | Unix epoch **saniye** |
| `rate_limits.spend_limit.used_percentage` / `.resets_at` | Claude apps gateway harcama limiti; 100'ü aşabilir; v2.1.251+ |
| `cost.total_cost_usd` | **İstemci tarafı liste fiyatıyla tahmin**; `modelPricing` ayarı varsa o tablo; faturadan farklı olabilir; `/clear` ile sıfırlanır (v2.1.211+) |
| `cost.total_duration_ms`, `cost.total_api_duration_ms` | duvar saati / yalnız API bekleme |
| `context_window.context_window_size` | 200000 veya 1000000 |
| `context_window.used_percentage` | **yalnız girdi**: input + cache_creation + cache_read (çıktı hariç); oturum başında `null` olabilir |
| `context_window.remaining_percentage`, `current_usage` | |
| `exceeds_200k_tokens` | son yanıtın toplam tokenı >200k (sabit eşik) |
| cache bölümü (`warm`, `hit_ratio` …) | cache durumu özeti — alan listesi ayrıca çıkarılacak |
| `model.display_name`, `version` (ör. 2.1.90), `workspace`, `session_id`, `transcript_path` | |

**Ek alanlar (örnek JSON'dan):** `cost.total_lines_added/removed`,
`context_window.total_input_tokens/total_output_tokens/current_usage
{input, output, cache_creation, cache_read}` (ilk çağrıdan önce ve
`/compact` sonrası `null`), `fast_mode`, `effort.level`, `thinking.enabled`,
`output_style.name`.

**`prompt_cache` — Claude Code'un kendi cache analitiği** (API yanıtlarındaki
cache sayılarından hesaplanır, her sağlayıcıda çalışır):

| Alan | Anlam |
|---|---|
| `warm` | Cache'li önek TTL içinde mi (son yanıtta cache tokenı yoksa `false`) |
| `caching_observed` | Oturumda hiç cache tokenı görüldü mü |
| `ttl` | `"5m"` veya `"1h"` |
| `expires_at` | Öneğin soğuyacağı epoch sn |
| `requests` | Ana konuşmada kaydedilen API isteği |
| `misses` | **Tanım:** cache'te olanın >%5'ini ve ≥2 000 tokenını yeniden işleyen istekler, sıkıştırma/araç-sonucu temizliğiyle açıklanamayan |
| `expected_rebuilds` | Sıkıştırma/temizlik sonrası beklenen yeniden inşalar |
| `hit_ratio` | cache okuma / tüm girdi (okuma+yazma+cache'siz), 0–1 |
| `cache_write_tokens`, `miss_recache_tokens` | |
| `last_miss_at`, `last_miss_cause` (`tools_changed` vb., v2.1.260+), `miss_causes` | **teşhis** |
| `recache_tokens_if_cold` | Cache soğursa sonraki isteğin yeniden yazacağı token |

→ Bu, `/usage` komutunun "Prompt cache (main)" satırıyla aynı istatistik.
Platform cache analitiğini **sıfırdan yazmak yerine** bu alanları
(statusline'dan veya OTel `api_request`'ten türeterek) kullanmalı;
cacheeconomics'in çarpanlarıyla dolara çevirmeli.

Kurallar:
- `rate_limits` **yalnızca Pro/Max** (veya gateway) ve **ilk API
  yanıtından sonra**; her pencere bağımsız olarak **yok olabilir**;
  pencere `resets_at`'ini geçince Claude Code alanı **düşürür**.
- Yeniden çalıştırma tetikleri: 300 ms debounce; pencere `resets_at`'e
  ulaşınca; komut değişince anında; devam eden script iptal edilir.
- `jq -r '.rate_limits.five_hour.used_percentage // empty'` kalıbı.

→ `used_percentage` = uçtaki `utilization`; `resets_at` **saniye** (uç
ISO-8601 verir). Birleşik modelde ikisi de epoch saniyeye normalize edilir.
→ `modelPricing` ayarı: kullanıcı kendi fiyat tablosunu Claude Code'a
verebiliyor — platformun fiyat tablosu ile **aynı** tabloyu buraya yazmak
"üç maliyet" sorununu kökten çözer (tek fiyat kaynağı).

## G. Settings `env` bloğu — `https://code.claude.com/docs/en/settings` (resmî)
- Ayar dosyalarında `env` bloğu **sıradan bir anahtar**; öncelik
  seviyelerini izler (managed > `--settings` > `.claude/settings.local.json`
  > `.claude/settings.json` > `~/.claude/settings.json`).
- Proje seviyesindeki çoğu `env` değeri klasöre **güven verildikten sonra**
  uygulanır; kullanıcı seviyesi (`~/.claude/settings.json`) her projede.
- Kabuk değişkeni ile ayar anahtarı çiftlerinde hangisinin kazandığı çift
  çift belirlenir (`env-vars` referansı).
→ Kurulum sihirbazı `~/.claude/settings.json` → `env` içine
`CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_*` yazabilir. `cleanupPeriodDays`
(transcript saklama, toktrack'e göre varsayılan 30 gün) bu sayfada değil;
`settings-reference` okunacak.

## D. Kota ucu (gözlenmiş, prototipten)
`GET https://api.anthropic.com/api/oauth/usage` — bkz. notes/00 §1.
Belgelenmemiş. `limits[]` dizisi: kind/group/percent/severity/resets_at/
scope/is_active.

## E. Rate-limit header'ları — **kaynak koddan doğrulandı**

İki bağımsız uygulama aynı aileyi ayrıştırıyor: CodeZeno
`src/poller/claude.rs` (`parse_rate_limit_headers`) ve claude-meter
`internal/normalize/normalizer.go` (`parseRatelimit`). `/v1/messages`
yanıtında (OAuth abonelik trafiği dahil; 429'da bile) dönüyor.

Önek: `anthropic-ratelimit-unified-`

| Header (önek sonrası) | Tip | Anlam |
|---|---|---|
| `5h-utilization` | 0–1 float | 5 saatlik pencere doluluğu (×100 = %) |
| `5h-reset` | unix sn | 5 saatlik sıfırlanma |
| `5h-status` | string | pencere durumu |
| `5h-surpassed-threshold` | bool | eşik aşıldı |
| `7d-utilization` / `7d-reset` / `7d-status` / `7d-surpassed-threshold` | | haftalık karşılıkları |
| `reset` | unix sn | genel sıfırlanma |
| `status` | string | `rejected` → istek reddedildi |
| `representative-claim` | `five_hour` \| `seven_day` | reddin hangi pencereden kaynaklandığı |
| `fallback-percentage` | float | |
| `overage-status`, `overage-disabled-reason` | string | ek kullanım durumu |
| (ayrıca) `retry-after` | sn | |

claude-meter pencere adlarını genel ayrıştırıyor (`<pencere>-<alan>`), yani
`5h`/`7d` dışında yeni pencereler gelirse de yakalar.

**`/api/oauth/usage` ile eşleme:** `limits[].kind=session` ↔ `5h`,
`weekly_all` ↔ `7d`; `limits[].is_active` ≈ `representative-claim`;
`limits[].severity` ≈ `surpassed-threshold`/`status`.

**Nasıl okunur:** CodeZeno yalnızca usage ucu **404/desteklenmiyor**
döndüğünde `max_tokens:1` bir Messages isteğiyle header okuyor; 429/5xx'te
**bilerek** okumuyor ("rate limit'e cevap olarak kota harcamak yanlış ve
sorunu büyütür" — kaynak koddaki yorum). claude-meter proxy'de pasif
okuyor. Platform için: **pasif** (kullanıcının zaten yaptığı isteklerden,
yalnızca Research Mode proxy'siyle) veya hiç.

## F. Claude Desktop token cache'i (CodeZeno `poller/claude_desktop.rs`)

CodeZeno kimlik kaynaklarını ucuzdan pahalıya sıralıyor:
1. `~/.claude/.credentials.json` (CLI girişi)
2. **Claude Desktop uygulamasının kendi token cache'i** — CLI hiç
   kullanılmamış, yalnızca masaüstü uygulaması varsa tek kaynak bu
3. WSL dağıtımları (`wsl.exe -l -q` → `wsl -d <distro> cat ~/.claude/…`;
   UTF-16LE çıktı çözümü)

Kimlik değişimini izlemek için yol|boyut|mtime imzası tutuluyor.
Token süresi dolmuşsa `claude -p .` (headless prompt) çalıştırılıp
Claude Code'un yan etki olarak token yenilemesi bekleniyor (30 sn).
**Dikkat:** bu bir gerçek model çağrısıdır ("." prompt'u) — küçük ama
kota tüketir. Desktop kaynağında yenileme denenmez (uygulama kendi
yeniler). Bundled masaüstü CLI: `%APPDATA%\Claude\claude-code\<sürüm>\claude.exe`.
Kullanıcımız Desktop agent mode'da — bu kaynak platform için zorunlu.
