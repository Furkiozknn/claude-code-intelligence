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

## C. Statusline `rate_limits` (dolaylı kaynaklar)
claude-pace README: Claude Code ≥2.1.80 statusline stdin'inde
`rate_limits.five_hour` ve `.seven_day`. Resmî doküman URL'si henüz
okunmadı — Faz 5'te `docs/en/statusline` okunacak ve alan adları
doğrulanacak.

## D. Kota ucu (gözlenmiş, prototipten)
`GET https://api.anthropic.com/api/oauth/usage` — bkz. notes/00 §1.
Belgelenmemiş. `limits[]` dizisi: kind/group/percent/severity/resets_at/
scope/is_active.

## E. Rate-limit header'ları (dolaylı kanıt)
rjwalters/claude-monitor: `POST /v1/messages`'a 1 tokenlık istekle
rate-limit header'ları okunuyor; 429 yanıtı bile header taşıyor;
`claude setup-token` ile ~1 yıllık OAuth token. → Header'lar OAuth
trafiğinde var. Ama bu yöntem kota harcar; platformda kullanılmayacak.
claude-meter proxy'de aynı header'ları pasif okuyor (Faz 5: alan adları).
