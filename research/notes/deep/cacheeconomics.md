# Derin analiz · cacheeconomics

**Okunan:** `collectors/src/cacheeconomics_collector/events.py`,
`harness/cacheeconomics/analyzer.py` (ilk 260 satır). **Okunmayan:** `trace.py`,
`money.py`, `allocate.py`, `adapters/claude_code.py`, `checks.py`. Python.
**Kalıp değeri:** rakam yayınlama disiplini (Figure/withheld) + allow-list olay
şeması + ölçülmüş TTL gerçekleri.

## Olay şeması (`events.py`) — allow-list
- `FORBIDDEN_KEYS` (content, prompt, messages, body, tool_arguments…) her
  seviyede reddedilir (`assert_prompt_free` özyinelemeli); `EVENT_KEYS` dışı
  alan **hata**; tip/aralık kontrolü katı.
- Status tutarlılık kuralları: `outcome ∈ {ok,error,...}`, `code`, `error_type`
  birbirini doğrulamalı.
- `segments[]{id, role, tokens, cache_marked, index, ttl}` — prompt **yapısı**
  içerik olmadan (segment uzunluğu + cache işareti); `collector{name, version,
  source_type}`; HMAC tabanlı kimlikler.
- Hata mesajı bilerek jenerik ("invalid"): log'a alan adı sızmasın.
- Çarpanlar: cache read 0.1×, input 1×, 5m write 1.25×, 1h write 2×.

## Analiz ve rakam disiplini (`analyzer.py`)
- `Finding{code, title, severity, evidence_class: measured|modeled, detail,
  affected_requests, avoidable_usd_month: Figure, avoidable_usd_window: Figure,
  confidence, quality_risk, fix, structural, projection_why, projection_sample}`.
  Pencere ve aylık rakam **iki ayrı iddia** (ikincisi ayrıca ölçeklenebilir
  uzunlukta pencere ister); tek saatlik trace'ten "$180/ay" yayınlanmış bir
  hata bu ayrımın sebebi.
- **`money.Figure`**: `released`, `withheld_because`, `released_as: DRAFT|
  RECONCILED`, `projected`. Rakam **mutabakat kapısını** geçmedikçe
  `[figure withheld]` olarak render edilir — "güvenlik özelliği hatırlamaya
  bağlı değil: rakam istemenin yolu yok".
- Toplam, parçalarının **en zayıfının** durumunu miras alır (bir parça DRAFT
  → toplam DRAFT; biri withheld → toplam withheld, sebebi ilk withheld parça).
- `ALIGNMENT_FLOOR = 0.90`: post-hoc segmentasyon ölçülmüş gerçekle ≥%90
  örtüşmeden **yapısal** bulgu para taşıyamaz.
- `BAND_IS_RARE = 0.10` — iki kuralın aynı trace'te çelişen öneri vermesi
  yaşanmış, eşikler ayrıştırılmış.
- `blocking_notes`: bir rakamı niteleyen notlar **yapısal alan** — "notun
  türünü metnini arayarak belirlemek, yeniden yazımda blokeri sessizce
  provenance'a düşürür".
- **Ölçülmüş TTL (2026-07-28):** 5 dk girdi 300–420 sn arasında siliniyor;
  1 sa girdi 56 dk yaşadı.
- `_declared_ttl`: bir istekte **karışık TTL işaretleri** varsa tek toplam
  `cache_creation_input_tokens`'tan bölüştürme **bilinemez** → `None`, ilk
  işareti seçmek "rakam giymiş tahmin"; yalnız sağlayıcının kendi
  `ephemeral_5m/1h` kırılımı çözer.
- `tokens_counted` bayrağı: segment boyutu tokenizer'dan mı (prompt önekleri
  sağlayıcıya gönderilir!) yoksa byte tahmini mi — "hiçbir içerik dışarı
  çıkmadı" iddiası buna bağlı.

## Platforma aktarılacaklar
1. **Figure tipi**: her para/tahmin rakamı `{value, evidence_class, released,
   withheld_because, released_as, projected, estimator_version}` taşır;
   toplamlar en zayıf parçayı miras alır. MP §10 + §29'un somut uygulaması.
2. Pencere vs projeksiyon ayrımı; projeksiyon için asgari pencere ve örnek
   sayısı **bulgu başına** değerlendirilir.
3. Allow-list olay şeması; `segments` ile içeriksiz prompt yapısı (cache
   analitiği için yeterli).
4. TTL ölçümleri ve "karışık TTL bilinemez" kuralı → `ephemeral_5m/1h`
   kırılımı transcript'te olduğu için Claude Code'da çözülebilir, diğer
   sağlayıcılarda `None`.
5. Analitiğin "yan etki" uyarısı: tokenizer sayımı için içerik dışarı çıkıyorsa
   bunu raporda **söyle**.
