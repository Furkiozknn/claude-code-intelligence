# Derin analiz · vibe-bar (macOS menü çubuğu)

**Okunan:** `Sources/VibeBarCore/Services/QuotaPaceForecast.swift` (ilk 300 satır),
`Services/UsagePace.swift`. **Okunmayan:** `UsageForecastTimelineStore`,
`QuotaForecastBarProjection`, sağlayıcı istemcileri. Swift, macOS'a özel.
**Kalıp değeri:** Top-20 içindeki **en gelişmiş kota tahmin motoru** — ve
hâlâ "gereksiz ML yok" ilkesine uyuyor (medyan, MAD, ağırlıklı harman).

## İki katman

### 1. `UsagePace` — doğrusal pace (açıklanabilir taban)
- `expected = elapsed/duration·100`, `delta = actual − expected`.
- Aşamalar: |Δ| ≤ 2 onTrack · ≤ 6 slightly · ≤ 12 ahead/behind · > 12 far.
- `eta = (100 − actual) / (actual/elapsed)`; `willLastToReset` eğer eta ≥ kalan.
- **Kenar durumlar:** `elapsed == 0 && actual > 0` → **nil** ("taze pencere,
  geri doldurulmuş durum" — yanlış oran üretme); reset sonrası **180 sn
  tolerans** (`QuotaWindowEvaluation`): sağlayıcı snapshot'ı yenilenirken
  tahmin bağlamı düşmesin ama bayat cache "güncel döngü" sayılmasın.
- Çizim anında snapshot'tan hesaplanıyor → saat ilerledikçe rakam ilerliyor
  (snapshot anında donmuyor).

### 2. `QuotaPaceForecast` — harmanlanmış tahmin
Yalnız **kota gözlemleri** tüketimi tahmin eder; token/maliyet geçmişi sadece
**takvim ağırlığı** (kullanıcı ne zaman aktif) verir, asla token→kota dönüşümü
yapılmaz (MP §17 ile birebir).

Adaylar ve ağırlıklar:
| Aday | Değer | Ağırlık |
|---|---|---|
| Yakın eğim | `actual + recentRate·futureActivity` (rate > 0 ise) | `0.52 · min(1, n/6)` |
| Tarihsel | `actual + median(tamamlanmış döngülerde aynı ilerlemeden sonra eklenen)·trend` | `0.34 · min(1, k/5)` |
| Davranışsal zaman | `actual / behavioralProgress · trend` (heatmap yoksa doğrusal) | `0.14` sabit |

`projected = max(actual, ağırlıklı ortalama)`; `trend` = günlük aktivite
trend çarpanı.

**Güven skoru** = `obsCoverage·0.38 + historyCoverage·0.30 + freshness·0.20 +
activityCoverage·0.12`; obsCoverage = `0.65·min(1,n/10) + 0.35·(gözlem
süresi/geçen süre)`; freshness = son örnek yaşı / (3 × doğal aralık: 5 dk
kısa pencere, 1 sa uzun). Eşik: ≥0.72 high, ≥0.35 medium, altı learning.

**Belirsizlik bandı** = `clamp(max(4, 18·(1−conf)) + min(12, 0.35·MAD·1.4826
+ 0.5·recentSpread), 4, 28)`; `lower = max(actual, proj − u)`, `upper = proj + u`.
**Uyarlanabilir güvenlik hedefi** = `clamp(5 + (1−conf)·8, 5, 13)` %.

**Hüküm:** `atRisk` (proj ≥ 100) → `watch` (upper ≥ 100) → `learning` →
`surplus` (medyan fazla ≥ 25 **ve** kötümser fazla ≥ 10) → `enough`.
"Yüksek kalan tahmini tek başına israf demek değil": iki koşul birden.
`potentialUnusedPercent` = "olası israf, iş üretme talimatı değil".

**Diagnostics** yapısı bilerek tutuluyor: yakın/tarihsel/davranışsal
projeksiyonlar, kapsama yüzdeleri, örnek sayıları — "kara kutu hüküm yerine
işini göster" (MP §10/§17 açıklanabilirlik).

Performans notu: saat tablosu tek sefer kuruluyor (önceden döngü başına
yeniden — O(n²)); gözlem şeridi sıralı → iki binary search.

## Platforma aktarılacaklar
1. Forecast motoru **v1 = UsagePace** (doğrusal, aşamalı), **v2 = harman**
   (yakın eğim + tarihsel medyan + davranışsal). Ağırlıklar/eşikler bu
   dosyadan başlangıç değeri; **estimator sürümlemesiyle** (MP §29) kayıt.
2. Güven skoru dört bileşenli (kapsama, geçmiş, tazelik, aktivite) —
   Predicted etiketine güven eşlik eder.
3. Belirsizlik bandı + uyarlanabilir hedef; "surplus" için çift koşul.
4. Reset toleransı ve "taze pencere geri dolduruldu" bail-out kuralları.
5. Kota tahmini token geçmişine **yalnız takvim ağırlığı** için dokunur.
