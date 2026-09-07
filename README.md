# Claude Code Intelligence Platform

> Çalışma adı: `claude-code-intelligence`. Ad geçicidir; araştırma bitince
> ürün adına karar verilir.

AI coding agent kullanımını (önce Claude Code, mimari olarak diğer
sağlayıcılar) **gözlemleyen, normalize eden, analiz eden, ölçen, tahmin
eden, anomali tespit eden, uyaran ve "şu anda ne yapmalıyım?" sorusuna
veriye dayalı cevap veren** yerel-öncelikli bir istihbarat/kontrol katmanı.

Bu bir usage monitor, token sayacı, kota görüntüleyici, pano, CLI aracı
veya taskbar widget'ı **değildir** — bunların birleşiminden büyük bir sistem
hedefleniyor. Ama araştırma bitmeden tek satır platform kodu yazılmayacak.

## Yöntem

```
Research → Discover → Score → Deep Analyze → Extract → Synthesize
        → Design → Critique → Implement → Benchmark → Improve
```

Kaynak belge: `docs/MASTER_PROMPT.md` (kullanıcının görev tanımı).
Fazlar ve günlük: `PROGRESS.md`.
Araştırma veri seti: `research/catalog.jsonl` + `research/tools/catalog.py`.

## Temel ilkeler (araştırmadan bağımsız, baştan sabit)

1. **Observed / Derived / Estimated / Predicted / Inferred** ayrımı her
   yüzeyde açıkça korunur. Tahmin, gözlem gibi gösterilmez.
2. **Local-first.** Prompt, yanıt, kimlik bilgisi, token, oturum verisi
   gereksiz yere dışarı çıkmaz. Ham veri ile anonim analitik ayrılır.
3. **Nazik veri toplama.** Sağlayıcı korumalarını aşan hiçbir teknik
   (token rotasyonu vb.) kullanılmaz. Backoff vardır, hile yoktur.
4. **Aşamalı inşa.** Core → Advanced → Intelligence → Ecosystem.
   "Do not overbuild."
5. **Tekrarlanabilir analitik.** Her tahminin nasıl üretildiği ve hangi
   estimator sürümüyle üretildiği açıklanabilir.
6. **Tek gerçek kaynak.** Aynı bilgi iki yerde elle tutulmaz; kopya varsa
   testi vardır. (Prototipte öğrenilen ders — bkz. `research/notes/00-*`.)

## Önceki çalışmayla ilişki

`D:\Repolar\claude-quota-monitor` bu platformun prototipidir. Orada
öğrenilenler (resmî `/api/oauth/usage` şeması, `limits` dizisi, kod adı
gürültüsü, nazik sorgulama politikası, yerel JSONL atıfı, `light-dark()`,
tutarlılık testleri) `research/notes/00-seed-from-claude-quota-monitor.md`
içinde araştırma girdisi olarak duruyor. Platform onu **kapsayacak**, ona
bağımlı olmayacak.

## Durum

Bkz. `PROGRESS.md`.
