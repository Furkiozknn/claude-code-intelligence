# Claude Code Intelligence Platform

> Çalışma adı: `claude-code-intelligence` (CLI `cci`, daemon `ccid` — geçici).
> Ad ürün kararıyla değişebilir.

AI coding agent kullanımını (önce Claude Code, mimari olarak diğer
sağlayıcılar) **gözlemleyen, normalize eden, analiz eden, ölçen, tahmin
eden, anomali tespit eden, uyaran ve "şu anda ne yapmalıyım?" sorusuna
veriye dayalı cevap veren** yerel-öncelikli bir istihbarat/kontrol katmanı.

Bu bir usage monitor, token sayacı, kota görüntüleyici, pano, CLI aracı
veya taskbar widget'ı **değildir** — bunların birleşiminden büyük bir sistem
hedefleniyor. Araştırma ve mimari bitmeden platform kodu yazılmadı.

## Yöntem ve durum

```
Research → Discover → Score → Deep Analyze → Extract → Synthesize
        → Design → Critique → Implement → Benchmark → Improve
   ✅        ✅        ✅         ✅           ✅          ✅
                                            → ✅ Design (Faz 7–9) → 🔄 Implement (Stage 1–5 ✅, 6–7 🔄)
```

**Kod durumu:** `cci/` paketi — model (Stage 1), adaptör sözleşmesi (2),
toplayıcılar: zarf + ingest kapısı, transcript izleyici, kota poller, OTLP/JSON
alıcı (3), SQLite olay deposu (4), normalizasyon + dedup/birleştirme (5), fiyat
tablosu + özetler (6), pace v1 + boru hattı + snapshot + CLI (7).

```
uv sync && uv run pytest                    # 234 test
uv run cci scan                             # Claude Code + Codex transcript'lerini artımlı tara
uv run cci today | daily | sessions         # özetler (--json, --strict → koruma yasası ihlalinde çıkış 3)
uv run cci session <id>                     # oturum teşhisi (döngü, araç p95, context, sağlık)
uv run cci quota [--poll|--forecast|--backtest]
uv run cci advise [--apply|--undo <id>]     # "şu anda ne yapmalıyım" + geri alınabilir eylem
uv run cci alerts [--history]               # uyarı motoru (cooldown, sessiz saat, webhook)
uv run cci doctor                           # "bu sayılara güvenebilir miyim"
uv run cci setup otlp|statusline [--write]  # settings.json'a yedekli yazım
uv run cci run [--once]                     # daemon: OTLP 4318 + API 4319 + tarama + kota + uyarı + snapshot
uv run cci serve | tui | widget | statusline
uv run cci research proxy|unit-estimator|purge
uv run python benchmarks/bench.py           # → benchmarks/RESULTS.md
```

Stage 1–16 tamamlandı. Ölçülen performans ve tutmayan iki hedefin gerekçesi:
`docs/ARCHITECTURE.md` §11.

| Çıktı | Nerede |
|---|---|
| Görev tanımı (kullanıcı) | `docs/MASTER_PROMPT.md` |
| Fazlar, günlük, sıradaki işler | `PROGRESS.md` |
| Araştırma veri seti (232 repo, 13 kriter/100) | `research/catalog.jsonl`, `research/reports/catalog.md`, `research/tools/catalog.py` |
| Veri toplama yaklaşımları + resmî kaynak doğrulaması | `research/notes/01-*.md`, `02-resmi-kaynaklar.md`, `03-otel-genai-semconv.md` |
| Top 20 ve derin analizler (20 repo, kaynak kod düzeyi) | `research/reports/top20.md`, `research/notes/deep/*.md` |
| Sentez: 58 kalıp, 14 anti-kalıp, 10 açık problem, rekabet tablosu, D1–D10 | `research/reports/sentez.md` |
| Mimari | `docs/ARCHITECTURE.md` · `DATA_MODEL.md` · `EVENTS.md` · `PROVIDERS.md` · `PRIVACY.md` · `ANALYTICS.md` · `EXTENDING.md` · `RESEARCH_MODE.md` |
| Katkı kuralları | `CONTRIBUTING.md` |

## Temel ilkeler (baştan sabit; araştırmayla somutlaştı)

1. **Kanıt sınıfı her sayıda:** Observed / Derived / Vendor-estimated /
   Estimated / Predicted / Inferred. Para ve tahmin alanları `Figure`
   tipindedir; mutabakat kapısını geçmeyen sayı **basılmaz**.
2. **İçerik alanı yok.** Prompt, yanıt, araç argümanı, dosya içeriği hiçbir
   tipte tanımlı değildir; gizlilik incelemesi `grep` ile yapılabilir.
3. **Local-first.** Ağ envanteri iki hedeften ibarettir (kota ucu, isteğe
   bağlı fiyat yenileme); dışa aktarım yalnız açık rıza ile (Eco aşaması).
4. **Nazik veri toplama.** Token rotasyonu/yenileme, UA taklidi, kota harcayan
   sentetik istek yok; 429'a saygı, geri çekilme.
5. **Koruma yasası.** Her rapor `toplam = Σ parça`; `--strict` çıkış 3.
6. **Aşamalı inşa.** Core → Advanced → Intelligence → Ecosystem; "do not
   overbuild".
7. **Tekrarlanabilir analitik.** Türetimler saf fonksiyon; `cci replay`;
   sürümlü özet/estimator/fiyat.
8. **Tek gerçek kaynak.** Aynı bilgi iki yerde elle tutulmaz; kopya varsa
   testi vardır.

## Önceki çalışmayla ilişki

`D:\Repolar\claude-quota-monitor` bu platformun prototipidir; öğrenilenler
`research/notes/00-seed-from-claude-quota-monitor.md` içinde. Platform onu
**kapsayacak**, ona bağımlı olmayacak.

## Güvenlik notu (araştırmadan)

Üçüncü taraf repo klonlarken `.claude/skills` veya `hooks` taşıyan bir depo
Claude Code oturumuna skill enjekte edebilir (bu projede yaşandı). Klonları
geçici dizinde tutun; `.claude/` içeriğini çalıştırmayın. Ayrıntı:
`docs/PRIVACY.md` §5.
