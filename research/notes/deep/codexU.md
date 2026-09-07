# Derin analiz · codexU (Codex kota widget'ı, macOS)

**Okunan:** `Sources/CodexUsageWidget/Domain/CodexRateLimitNormalizer.swift`.
**Bilinen (önceki tur):** resmi Codex app-server JSON-RPC (`account/rateLimits/read`,
`account/usage/read`) üzerinden veri — **"resmi CLI'ye delege et"** kalıbı.
Swift, macOS.

## Rate-limit pencere normalizasyonu
- Sağlayıcı pencereleri **süreye göre sınıflandırılıyor** (isme göre değil):
  300 dk → 5 saat; 10 080 dk → 7 gün; 28–31 gün arası → aylık (Team hesapları
  43 800 dk ≈ 30.4 gün raporluyor). Uymayanlar `unclassified[]`.
- Her sınıf için **eşleşme sayısı** tutuluyor; tam olarak 1 eşleşme varsa
  atanıyor, 0 veya ≥2 ise **nil** (belirsizlikte tahmin yok).
- `isAuthoritative(hasWindowFields, hasMalformedWindow, normalized)` =
  alanlar var ∧ bozuk yok ∧ her sınıfta ≤1 ∧ unclassified boş. Aksi halde
  veri "yetkili değil" — UI bunu ayrı işliyor.
- `normalizeAvailableCount`: negatif kredi sayısı → nil.
- Palet rolü çözümleme: 5s primary, 7g secondary, aylık boşta kalan rolü alır
  (küçük ama iyi: **renk rolü pencere türüne bağlı, sabit değil**).

## Platforma aktarılacaklar
1. **Pencere sınıflandırması süreyle** — Anthropic `limits[]`'te `kind`
   (session/weekly_all/weekly_scoped) var ama diğer sağlayıcılar için süre
   tabanlı sınıflandırma + `unclassified` kovası gerekli (MP §27 birleşik
   model: `window{kind, duration_s, resets_at}`).
2. **`authoritative` bayrağı**: normalize edilmiş kota snapshot'ının "tam ve
   çelişkisiz" olup olmadığı; değilse Observed yerine **Inferred/partial**.
3. Sağlayıcı sürüm değişimi tespiti (MP §28): bilinmeyen pencere süresi
   `unclassified`'a düşünce **provider change** sinyali üret.
4. Codex adaptörü: app-server JSON-RPC birincil, rollout JSONL ikincil.
