# Derin analiz · JARACH-209/VibeBill

**Okunan:** `docs/how-attribution-works.md`, `docs/contracts.md` (modül
sözleşmeleri + doğrulanmış log formatları). TypeScript, MIT, 4★, 32 commit.
**Kalıp değeri:** güvenli atıf + koruma yasası + doğrulanmış çoklu-ajan parser'ları.

## Atıf algoritması (tam spesifikasyon)
- **Usage event:** zaman, model, token, oturum, cwd, dal, **düzenlenen dosya
  yolları** (yalnız Edit/Write/MultiEdit/NotebookEdit `input.file_path`;
  içerik asla).
- **Aday commit:** `e.ts − 120 s ≤ authorTs(C) ≤ e.ts + 14 gün` (horizon ileri,
  grace geri — saat kayması ve "commit'ten hemen sonra yazma" sırası).
  **Author date** (rebase'e dayanıklı, cherry-pick doğru), merge commit'ler
  asla aday değil ($0; squash-merge normal commit).
- **Skor:** `0.6·fileScore + 0.25·timeScore + 0.15·branchScore`;
  file = |edited ∩ files(C)| / |edited|; time = 1 − (Δt/horizon) kırpılmış;
  branch = 1 eşit / 0.5 bilinmeyen / 0 farklı. Kazanan ≥1 dosya paylaşmalı;
  eşitlik: en yakın zaman, sonra en küçük hash — **rastgelelik yok**.
- **Güven:** high (file ≥0.8 ve (dal eşleşti veya tek aday)), medium (≥0.4),
  low (diğerleri + saf-zaman yedeği). `show` alt skorları yazar — "kanıt,
  yalnız hüküm değil".
- **Saf-zaman yedeği:** hiçbir aday dosya paylaşmıyorsa penceredeki sonraki
  commit, **low + advisory**.
- **Forward-attach:** düzenleme yapmayan olaylar (planlama, okuma) aynı
  oturumda **sonraki** düzenleme olayının atıfını alır; son düzenlemeden
  sonrakiler öncekini. Hiç düzenleme yoksa **overhead** (advisory).
- **Kovalar:** waste (hiç commit'e düşmeyen düzenleme) · in-progress (en yeni
  commit'ten yeni olan waste — azarlanmaz, üst satırda) · overhead · out-of-scope
  (başka repo cwd'si veya cwd yok — üyelik kanıtlanamaz, tahmin edilmez).
- **Koruma yasası (her komutta):** `toplam = atıflı + waste + overhead +
  out-of-scope`; tutmazsa gürültülü uyarı, `--strict` çıkış 3.
- **Determinizm:** saf fonksiyon (events, commits, config); "now" enjekte.

## Doğrulanmış format gerçekleri (contracts.md, 2026-07-14)
- **Claude Code `iterations` kuralı:** üst seviye usage > 0 ise onu kullan (çoklu
  iterasyonlu retry/fallback kayıtlarında üst seviye = **son** iterasyon,
  öncekiler başarısız denemeler — toplama); üst seviye sıfır ve `iterations`
  doluysa iterasyonları topla (16 gerçek kayıt); değilse sıfır.
- Dedup id: `message.id:requestId`, yoksa `sessionId:timestamp:sha256(usage)[:16]`.
  "Tekrarlar GERÇEK (2–3×)."
- **Codex:** `session_meta.payload.thread_source=="subagent"` → tüm olaylar
  sidechain; `input_tokens` cache'li girdiyi içerir; `apply_patch`
  argümanından yalnız `*** (Add|Update|Delete) File:` başlık satırları.
- **Gemini CLI:** `~/.gemini/tmp/<slug>/chats/*.jsonl` (+ eski tek dosya JSON);
  `$set.messages` geçmişi **değiştirir**, `$rewindTo` işaretleri yok sayılır
  (geri alınan çağrılar da token yaktı); `tokens{input,output,cached,thoughts,
  tool,total}` — input cached'i içerir, thoughts çıktı olarak faturalanır;
  proje kökü `<tmp>/<slug>/.project_root` işaret dosyasından.
- **aider:** `.aider.chat.history.md` markdown; yerel saat, zaman dilimi yok;
  `4.2k` gibi ~2 anlamlı basamak (doctor uyarır).
- **Ingest:** `manifest.json{schemaVersion, adapterVersions, files{size,mtimeMs,
  bytesConsumed}, dedupeIndexHash}`; değişen dosya yeniden; `startOffset` ile
  satır sınırından devam; bozuk cache → sessiz tam yeniden inşa; şema/adaptör
  sürümü artınca toptan geçersiz.
- **Fiyat:** bundled `prices.json` + `~/.config/vibebill/prices.json`
  (`refreshPricing` = "**TEK ağ çağrısı**", LiteLLM'den, asla otomatik);
  para **nanoUSD string**; her JSON çıktısında `schemaVersion`, `provenance`
  etiketleri, `accountingMismatch`.
- Kurallar: zod her güvensiz sınırda; saf çekirdek sıfır I/O; `execFile` dizi
  argümanla; transcript içeriği asla; adaptörler salt okunur; runtime bağımlılığı
  3 paket.

## §8 kısa değerlendirme
| | |
|---|---|
| Data acquisition | 4 adaptör (Claude/Codex/Gemini/aider), SCHEMA_VERIFIED bayrağı — **doğrulanmamış adaptör açıkça işaretli** |
| Data model | UsageEvent + LedgerEntry + Attribution{kind, confidence, advisory} |
| Storage | `<repo>/.vibebill/cache` manifest + ndjson; git notes (`refs/notes/vibebill`) |
| Analytics | Commit/sürüm başına maliyet; koruma defteri |
| Accuracy | En yüksek: olasılık + güven + kanıt + koruma + determinizm |
| Privacy | İçerik yok; yalnız araç adı ve dosya yolu |

## Platforma aktarılacaklar
1. **Koruma yasası** — her atıf/analitik çıktısında "toplam = parçalar" kontrolü
   ve `--strict`.
2. **Güven katmanları + advisory etiketi + kanıt görünürlüğü** (§10 Observed/
   Derived/Estimated/Inferred'in somut hali).
3. `iterations` kuralı ve dedup yedeği (tycho ile birlikte).
4. `SCHEMA_VERIFIED` bayrağı: sağlayıcı adaptörü doğrulanmış mı, kullanıcıya
   söyle.
5. Ingest manifest (size/mtime/bytesConsumed) ve tek ağ çağrısı ilkesi.
6. Gemini/aider format gerçekleri (Faz 7 adaptör tasarımı).
