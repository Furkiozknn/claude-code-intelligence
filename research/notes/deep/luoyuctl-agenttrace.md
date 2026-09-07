# Derin analiz · luoyuctl/agenttrace

**Okunan:** `crates/agenttrace-core/src/diagnostics.rs` (ilk 320 satır).
**Okunmayan:** `lib.rs` (sağlık skoru formülü), `parser.rs`, `insights.rs`,
`governance.rs`, `history.rs`, `session_cache.rs`, `sqlite_sessions.rs`,
TUI. Rust workspace (core + cli), MIT, 130★, 488 commit, `PRIVACY.md` ve
`SECURITY.md` var, Codex plugin olarak da paketli.

## Teşhis modeli (`Diagnostics`)
| Alan | İçerik |
|---|---|
| `loop_cost` | retry maliyeti, araç döngüsü maliyeti, toplam, retry olayı sayısı, döngü grubu, tür, tur |
| `loop_fingerprints[]` | `tool_name` + `result_hash` tekrar sayısı, ilk/son indeks, severity — **aynı araç aynı sonuçla tekrar** = döngü |
| `tool_latencies[]` | araç başına count/avg/p95/max/min, timeout sayısı, `is_slow` |
| `context_utilization` | tahmini toplam, araç tanımları, konuşma geçmişi, sistem prompt'u, göreve kalan, %, risk seviyesi, öneri |
| `large_params[]` | büyük araç parametreleri (boyut, risk) |
| `unused_tools[]` | tanımlı ama az/hiç çağrılmayan araçlar |
| `stuck_patterns[]` | takılma kalıpları (pattern, açıklama, severity) |
| `steps[]` | trace adımları (kind, name, süre, durum, token, call_id, parent_id) |

Ek: `FixSuggestion{title, description, action, severity, category}`,
`CostAlert{triggered, level, current, baseline, ratio}` (**taban çizgisine
göre oran** — anomali eşiği), `SessionFinding{kind, value, detail, severity,
evidence[]}` — bulgu + **kanıt**.

## "Önce neye bakayım" merdiveni (`inspect_reason`)
```
health < 50            → critical
tool_calls_fail > 0    → failures
anomalies non-empty    → anomaly
context risk warn/crit → context
loop_groups>0 | stuck  → loops
cost ≥ $1              → cost
duration ≥ 300 s | p95 boşluk ≥ 60 s → latency
health < 80            → warning
else                   → ok
```
`needs_attention` = bunlardan herhangi biri; `attention_rank` = (öncelik,
sağlık, −(anomali+hata), −maliyet) demeti ile deterministik sıralama;
`inspect_first` her sebep için tek "en kötü" oturumu seçer (tekrarsız).

## §8 kısa değerlendirme
| | |
|---|---|
| Data acquisition | 14 ajan + genel JSON/JSONL; keşif `discovery.rs`; SQLite oturumlar |
| Analytics | Oturum sağlığı, döngü/retry maliyeti, araç gecikme p95, context bütçesi kırılımı, kullanılmayan araçlar |
| Anomaly | `CostAlert` taban/oran; `anomalies` alanı (formül okunmadı) |
| Accuracy | "Limited" yetenek etiketi; bulgu+kanıt |
| Privacy | `PRIVACY.md` (okunmadı); yerel, backend yok |
| UX | TUI sıralama/arama; JSON/MD/HTML rapor |

## Platforma aktarılacaklar
1. **Oturum teşhis modeli** — MP §14'ün somutu: retry oranı, döngü parmak izi
   (araç+sonuç hash), araç p95, context bütçesi kırılımı, kullanılmayan araç.
2. **Dikkat merdiveni**: deterministik "önce buna bak" — "Şu anda ne yapmalıyım?"
   motorunun (§21) oturum katmanı.
3. Bulgu = değer + kanıt listesi; maliyet uyarısı = taban çizgisine oran.
4. Faz 7: `lib.rs` sağlık formülü ve `governance.rs` okunacak.
