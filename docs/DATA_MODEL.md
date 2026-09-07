# DATA_MODEL — birleşik kullanım modeli

Durum: Faz 7 taslağı (2026-09-07). Kaynak kararlar: `research/reports/sentez.md`
D2–D4; kanıt: tycho SCHEMA.md, ccusage adaptör kuralları, cacheeconomics
`Figure`, VibeBill sözleşmeleri, OTel GenAI semconv (`notes/03`).

Üç değişmez ilke:
1. **İçerik alanı yok.** Hiçbir tipte prompt/yanıt/araç argümanı/dosya içeriği
   alanı tanımlı değil. Eklemek diff'te görünür ve `PRIVACY.md` incelemesi ister.
2. **Her sayı kanıt sınıfı taşır.** `evidence_class` zorunlu; para ve tahmin
   alanları `Figure` tipindedir.
3. **Toplamlar parçalardan türetilir**, asla ayrı saklanmaz; koruma yasası
   (`toplam = Σ parça`) her rapor çıkışında doğrulanır.

## 1. Ortak tipler

### 1.1 `EvidenceClass`
| Değer | Anlam | Örnek |
|---|---|---|
| `observed` | Sağlayıcının/istemcinin doğrudan raporladığı | `usage.output_tokens`, kota `utilization` |
| `derived` | Gözlemlerden deterministik hesap | günlük toplam, cache hit oranı |
| `vendor_estimated` | Satıcının kendi tahmini | Claude Code `cost_usd` (belge: "estimated") |
| `estimated` | Bizim modelimiz + fiyat tablosu | `cost.usd` LiteLLM ile |
| `predicted` | Geleceğe dair, bant ve güvenle | pace ETA, harman projeksiyon |
| `inferred` | Kanıtı dolaylı, güven düşük | P90 "limit", saf-zaman atıfı |

### 1.2 `Figure` (para ve tahmin değerleri)
```
Figure {
  value: decimal|null      # nanoUSD (para) veya birim değeri
  unit: "nanoUSD" | "tokens" | "percent" | "seconds"
  evidence_class: EvidenceClass
  released: bool           # mutabakat/kapı geçildi mi
  withheld_because: str    # released=false ise zorunlu, insan okur
  released_as: "draft" | "reconciled" | ""   # released=true ise
  projected: bool          # pencere dışına ölçeklendi mi
  estimator: {id, version} | null
  band: {lo, hi} | null    # predicted/estimated için
  confidence: 0..1 | null
}
```
Kurallar (cacheeconomics'ten): toplam `Figure` = parçaların toplamı; **bir
parça `released=false` ise toplam da**, `withheld_because` ilk tutulan
parçadan; bir parça `draft` ise toplam `draft`; herhangi biri `projected` ise
toplam `projected`. Render katmanı `released=false` için sayıyı **basamaz**
(tip düzeyinde: `Figure.render()` yalnız released ise sayı döner).

### 1.3 `PrivacyClass` — bkz. `PRIVACY.md`: `public | internal | sensitive | secret`.
Her alan şemada sınıf etiketi taşır; `secret` alanı **hiçbir tipte yoktur**.

### 1.4 Kimlikler
```
AccountRef   { provider, account_key }   # account_key = OTel user.account_uuid (tek kaynak; R-9)
                                          # gizli değerden türetilmiş kimlik YOK (kimlik dosyası hash'i kaldırıldı)
                                          # null → hesap seviyesi veri cache'lenmez, yalnız canlı gösterilir (claude-pace kuralı)
SourceInstance { provider, instance_id, label, kind, root_path?, network: bool, schema_verified: bool }
SessionRef   { session_id, parent_session_id?, agent_id?, is_sidechain: bool }
```

## 2. `UsageRecord` — normalize edilmiş tek API çağrısı
```
UsageRecord {
  record_id: str                 # sha256(dedup_key)
  dedup_key: str                 # "<provider>:<message_id>:<request_id|->:<session_id>"
  provider: "anthropic"|"openai"|"google"|"github"|...   # semconv provider.name ile hizalı
  source: SourceInstance
  account: AccountRef | null
  session: SessionRef
  prompt_id: str | null          # OTel prompt.id / hook prompt_id
  message_id: str | null
  request_id: str | null
  ts: datetime (UTC, ms)         # [2000, 2100) sınırı dışı → reddet, say
  model: { id: str, display: str, family: str|null, unknown: bool }
  tokens: {
    input: int                   # cache HARİÇ girdi (Anthropic anlamı)
    input_total: int             # input + cache_read + cache_write (semconv anlamı)
    output: int
    cache_read: int
    cache_write_5m: int | null   # null = sağlayıcı ayırmıyor
    cache_write_1h: int | null
    cache_write_total: int
    reasoning: int | null
  }
  cost: { usd: Figure, vendor_usd: Figure|null, pricing_effective_at: date|null }
  timing: { duration_ms: int|null, ttft_ms: int|null }
  attribution: {
    query_source: "main"|"subagent"|"auxiliary"|null
    agent: str|null, skill: str|null, plugin: str|null,
    mcp_server: str|null, mcp_tool: str|null, marketplace: str|null
    speed: "standard"|"fast"|null, effort: str|null
  }
  flags: { synthetic: bool, api_error: bool, advisor: bool, iteration_index: int|null,
           sidechain_replay_dropped: int, stream_partial_suspected: bool }
  workspace: { project_key: str, cwd_hash: str|null, git_branch: str|null }   # sensitive
  evidence_class: "observed"
  collector: { name, version, schema_version }
}
```
Dedup ve kazanan kuralları (`ccusage`, tycho ADR 0002; **Stage 5'te kesinleşti**):
- **`dedup_key`** (kaynaklar arası mutabakat anahtarı): `request_id` varsa
  `<provider>:req:<request_id>` — OTel `api_request.request_id` ile transcript
  `requestId` aynı API istek kimliğidir, iki kaynak tek kayıtta **birleşir**;
  yoksa `<provider>:msg:<message_id>:<session_id>` (gateway aynı `message_id`'yi
  farklı oturumda yeniden kullanabilir); o da yoksa `<provider>:uuid:<uuid>:<session_id>`.
- **`message_key`** (ikincil): `<provider>:msg:<message_id>:<session_id>` —
  sidechain replay tespiti için (aynı mesaj, farklı `requestId`).
- Aynı `dedup_key` → kazanan: sidechain olmayan > **daha büyük toplam token**
  > yeni şema (`speed` alanı olan). Kaybedenin tamamlayıcı bilgisi kazanana
  **birleştirilir** (satıcı maliyeti, 5m/1h kırılımı, eksik kimlik/atıf
  alanları); token sayıları asla ezilmez, fark varsa `token_mismatch`
  kanaryası artar (R-11).
- `is_sidechain=true` kopya ile ebeveyn çakışırsa (aynı `message_key`, farklı
  `dedup_key`) ebeveyn kalır, `sidechain_replay_dropped` sayacı artar.
- Advisor iterasyonları ayrı kayıt: `message_id="<id>:advisor:<i>"`,
  `request_id=None` (ana kayıtla çakışmaz).
- `usage.iterations[type=advisor_message]` → ayrı `UsageRecord`, `flags.advisor=true`,
  `message_id = "<id>:advisor:<i>"`, model = advisor modeli, `vendor_usd=null`.
- Üst seviye usage sıfır ve iterasyon doluysa iterasyon toplamı; sentetik
  (`model="<synthetic>"`) kayıt token=0, `flags.synthetic=true`, toplama girmez.

## 3. `QuotaSnapshot` — hesap seviyesi kota gözlemi
```
QuotaSnapshot {
  snapshot_id, provider, account: AccountRef (null ise SAKLANMAZ)
  fetched_at: datetime
  source: "usage_api" | "statusline" | "rate_limit_headers" | "provider_ipc"
  authoritative: bool             # tüm pencereler sınıflandı, çelişki yok (codexU)
  windows: [ QuotaWindow ]
  spend: { used: Figure, limit: Figure } | null        # ekstra kullanım/gateway
  retry_after_s: int | null
  raw_hash: str                   # ham yanıtın sha256 (içerik saklanmaz)
  evidence_class: "observed"
}
QuotaWindow {
  kind: "session_5h" | "weekly_all" | "weekly_scoped" | "monthly" | "unclassified"
  duration_s: int | null          # 18000 / 604800 / 2419200–2678400
  utilization: 0..1 | null        # yüzde değil, oran
  resets_at: datetime | null
  scope: { model_display: str|null, group: str|null }
  severity: "normal"|"warning"|"critical"|null
  is_active: bool | null
}
```
Sınıflandırma **süreye göre** (`duration_s`), ada göre değil; eşleşme sayısı
≠ 1 ise `kind=unclassified` ve `authoritative=false`. Pencere sıfırlanmasından
sonra 180 sn tolerans; `elapsed=0 ∧ utilization>0` → pace hesaplanmaz.

## 4. `SessionSummary` (türetilmiş, yeniden hesaplanabilir)
```
SessionSummary {
  session: SessionRef, project_key, provider, started_at, ended_at|null, active: bool
  requests: int, models: [{model_id, requests, tokens{…}, cost: Figure}]
  tokens{…toplam}, cost: Figure, vendor_cost: Figure|null
  cache: { hit_ratio: float|null, write_5m_share, write_1h_share }
  tools: [{name, calls, failures, p95_ms, timeouts}]
  diagnostics: {                          # agenttrace modeli
    retry_events: int, loop_fingerprints: [{tool, result_hash, count}],
    context_utilization: {estimated_total, risk: "ok"|"warn"|"critical"} | null,
    compactions: int, unused_tools: [str], attention: "critical"|"failures"|"anomaly"|"context"|"loops"|"cost"|"latency"|"warning"|"ok"
  }
  attribution: { by_agent: {...}, by_skill: {...}, by_mcp: {...} }
  conservation: { total, attributed, unattributed, ok: bool }
  summary_version: int
}
```

## 5. `DailySummary` (kalıcı özet cache — toktrack)
Gün (yerel), provider, source instance, model, project → token/cost/requests.
`CACHE_VERSION` uyuşmazsa geçmiş **korunur**, ham dosyası duran günler yeniden
hesaplanır; `retroactive_reconciliation=true` kaynaklarda etkilenen günler tam
kümeden yeniden. Bugün her zaman yeniden hesaplanır. Transcript 30 günde
silinse de bu tablo kalır.

## 6. `Estimate` ve `Forecast`
```
Estimate {
  estimator: {id, version}, target: str, produced_at, inputs_hash
  value: Figure (predicted|estimated|inferred), band{lo,hi}, confidence 0..1
  diagnostics: {...}              # açıklanabilirlik: aday projeksiyonlar, kapsama, örnek sayısı
}
QuotaForecast extends Estimate {
  window_kind, current_utilization, projected_at_reset {median, lo, hi}
  verdict: "at_risk"|"watch"|"learning"|"surplus"|"enough"
  run_out_at: datetime|null, target_remaining: float
}
```
Estimator sürümü değişince eski tahminler silinmez; `realized` alanı gerçek
sonuçla doldurulur (realized-vs-estimated, codeburn).

## 7. `Alert` ve `Recommendation`
```
Alert { alert_id, rule_id, severity, raised_at, resolved_at|null, subject{kind,id},
        evidence: [{metric, value, baseline, ratio}], dedupe_key, cooldown_until }
Recommendation { rec_id, kind, title, why: [evidence], action: {type, reversible: bool, plan_hash},
                 expected: Figure, realized: Figure|null, status }
```

## 8. Kaynak → alan eşlemesi (özet; tam tablo `notes/03`)
| Alan | OTel olayı | Transcript | Statusline | Hook |
|---|---|---|---|---|
| tokens.* | `api_request.{input,output,cache_read,cache_creation}_tokens` | `message.usage.*` (+`cache_creation.ephemeral_*`) | `context_window.total_*` (oturum toplamı) | — |
| cost.vendor_usd | `api_request.cost_usd_micros` | — | `cost.total_cost_usd` | — |
| attribution.* | `agent.name`, `skill.name`, `mcp_*`, `query_source` | `attribution*` alanları | — | `tool_name` |
| session/prompt | `session.id`, `prompt.id`, `message.uuid` | `sessionId`, `uuid` | `session_id` | `session_id`, `prompt_id` |
| kota | — | — | `rate_limits.*` | — |
| compaction | — | — | — | `PreCompact/PostCompact` |

## 9. Açık noktalar
- ~~`account_key` için kimlik dosyası parmak izi~~ — Faz 9'da kaldırıldı
  (R-9): yalnız OTel `user.account_uuid`.
- `tokens.input_total`'ın OpenAI/Gemini'de `input` ile ilişkisi adaptör
  başına belgelenecek (`PROVIDERS.md` §5).
- `evidence_class`: `input_total` alanı **derived**'dır; kayıt düzeyinde
  `evidence_class=observed` olsa da alan düzeyi meta `derived` işaretler
  (SELF_CRITIQUE Q10).
