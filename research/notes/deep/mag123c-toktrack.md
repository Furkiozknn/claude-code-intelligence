# Derin analiz · mag123c/toktrack

**Okunan:** `.claude/ai-context/architecture.md` (projenin AI için yazdığı mimari
belge), `src/services/cache.rs` (ilk 220 satır), `src/parsers/mod.rs`.
**Okunmayan:** `src/parsers/claude.rs`, `src/services/audit.rs`. Rust, MIT, 188★.

## Kaynak bulguları (cache.rs / parsers/mod.rs)
- **`CACHE_VERSION = 16`** ve her artışın sebebi yorumda (v14 proje kırılımı,
  v15 eksik model → zaman damgasından çözüm, v16 1 sa cache yazımı LiteLLM
  `_above_1hr` fiyatı). Sürüm uyuşmazsa **geçmiş korunur**, uyarı verilir ve
  ham dosyası hâlâ duran günler yeniden hesaplanır — "yeniden hesaplanamayan
  geçmişi silme" ilkesi.
- `load_or_compute`: bugün her zaman + kayıt gelen tüm günler yeniden;
  cache'li geçmişle birleştirilir; ayrı `.lock` dosyası (fs2) ile süreçler
  arası kilit; kilit açılamazsa kilitsiz devam (geriye uyum).
- Model anahtarı `model::provider` bileşik; yalnız model kısmı normalize
  (issue #134: sağlayıcı adı normalize edilmemeli).
- **`retroactive_reconciliation()` trait bayrağı**: Copilot oturum kapanışında
  kümülatif toplamları **önceki günlere geri yazar** → sıcak yolda "son
  dosyalar" yalnız yeni günleri değil eski günleri de değiştirebilir; o günler
  tam dosya kümesinden yeniden hesaplanmalı. (Artımlı tasarımda gözden kaçan
  bir kaynak sınıfı.)
- `parse_recent_files`: mtime okunamazsa dosya **dahil** edilir ("güvenli
  yön").
- Dedup: `message_id:request_id` **ilk kazanır** HashSet — tycho ADR 0002'nin
  reddettiği yöntem (akış ortası kısmi kayıt kalabilir).
- `SourceInstance{id, label, kind, parser}`: aynı format için birden çok
  konum (`codex@devbox` uzak snapshot fikri) — sağlayıcı ≠ kaynak örneği
  ayrımı (MP §27 `source_instance`).
- Parse hatası dosya bazında uyarı + atlama (tek bozuk dosya tümünü düşürmez).

## Mimari
```
TUI[ratatui] → CLI[clap] → Services → Parsers[trait] → Cache
```
- **`CLIParser` trait:** `name`, `data_dir`, `file_pattern`, `parse_file`,
  `parse_all` (rayon), `parse_recent_files(since)` (mtime filtresi),
  `collect_files`, `parse_and_dedup` — **collector sözleşmesinin** iyi bir
  örneği.
- **8 parser:** Claude (JSONL), Codex (JSONL), Gemini + Qwen (JSON+JSONL,
  `~/.gemini/tmp/*/chats/`), OpenCode (**SQLite** `opencode.db` + JSON yedeği),
  Pi (JSONL), **Antigravity (SQLite + protobuf blob**, `gen_metadata` →
  `ChatModelMetadata/ModelUsageStats`), Grok (JSONL `updates.jsonl`,
  `costUsdTicks` **tam sayı tick**'ten maliyet — tick yoksa `None`, "$0"
  raporlanmaz).
- **Veri akışı — sıcak yol:** fiyat yalnız cache'ten (ağ yok) → dünden beri
  değişen dosyalar (mtime) → `cache.load_or_compute` (cache'li geçmiş + taze
  bugün) → günlük özetlerden toplam/model (ham kayıt gerekmez). **Soğuk yol:**
  tam parse + fiyat ağdan (LiteLLM, 1 sa TTL).
- **Cache:** `~/.toktrack/cache/{cli}_daily.json` (günlük özet; yeni kayıt
  gelen günler yeniden hesaplanır), `pricing.json`. README: Claude Code'un
  30 günde sildiği oturumların geçmişi **kalıcı** — değişmez günlük girdiler.
- **Performans teknikleri:** zero-copy serde (`&'a str`), in-place buffer
  (`&mut [u8]` → simd-json), SIMD (AVX2/NEON), rayon dosya paralelliği →
  ~1.0 GiB/s tek, ~3.0 GiB/s paralel; cache'li çalışma 0.04 sn.
- Normalizasyon: model adı tarih son ekini atma, nokta→tire, görünen ad
  (`claude-opus-4-5` → "Opus 4.5"), Copilot maliyet=0.
- TUI: 52 haftalık ısı haritası (renk körlüğüne uygun), Overview/Stats/Models
  sekmeleri, kaynak detay, günlük/haftalık/aylık, yardım/çıkış onayı.

## §8 kısa değerlendirme
| | |
|---|---|
| Data acquisition | 9 CLI; SQLite+protobuf dahil; mtime artımlı |
| Storage | Değişmez günlük özet cache — **saklama** çözümü |
| Performance | Sınıfının en iyisi (ölçülmüş) |
| Accuracy | `~` tahmin, `?` bilinmeyen; tick tabanlı maliyet `None` |
| Extensibility | Trait + tablo |
| Docs | AI-context belgeleri (ilginç: repo kendini ajana anlatıyor) |

## Platforma aktarılacaklar
1. **Collector trait** şekli (name/data_dir/pattern/parse_file/parse_recent/
   dedup).
2. **Günlük özet cache'i** ile kaynak silinse de geçmişin korunması (MP §26
   saklama politikası: ham silinir, toplam kalır).
3. Sıcak/soğuk yol ayrımı; fiyatın çevrimdışı çalışması.
4. simd-json + rayon performans çıtası (Rust seçilirse).

## Yan bulgu (güvenlik)
Repo `.claude/skills/` ve `.claude/hooks/` taşıyor; klonlanınca bu oturumda
**skill olarak göründü**. Üçüncü taraf repo klonlamak Claude Code'a skill/hook
enjekte edebiliyor — platformun "araştırma modu"nda ve dokümantasyonunda
tedarik zinciri uyarısı olmalı.
