# ANALYTICS — zekâ katmanları, tahmin, anomali, uyarı, öneri

Durum: Faz 7 taslağı. Kanıt: vibe-bar (harman), claude-pace (pace),
agenttrace (teşhis), VibeBill (atıf), cacheeconomics (rakam disiplini),
claude-meter (kota birimi), codeburn (realized-vs-estimated), Maciek (P90).

İlke: **basit yöntem önce, ölçülerek ilerle; ML yok** (MP §18). Her çıktı
`Figure`/`Estimate` taşır; `released=false` olan sayı hiçbir yüzeyde basılmaz.

## 1. Zekâ katmanları
### 1.1 Oturum zekâsı (MP §14)
Girdi: `usage_records`, `tool.call`, `session.compacted`, `statusline.tick`.
Çıktı `SessionSummary.diagnostics`:
- retry olayları ve maliyeti (`usage.error` + aynı prompt_id'de tekrar);
- döngü parmak izi: `(tool_name, result_hash)` ≥3 tekrar → `loop`;
- araç gecikmeleri p95/timeout/`is_slow`;
- context bütçesi: `context_window.used_percentage` + auto-compact eşiği
  farkındalığı; sabit bağlam tahmini (talimat dosyaları + SKILL.md + MCP
  şeması, içeriksiz);
- compaction sayısı ve sonrası maliyet artışı;
- kullanılmayan MCP araçları (tanımlı ama 0 çağrı, `mcp.connection` ile);
- **dikkat merdiveni** (deterministik): critical (sağlık<50) → failures →
  anomaly → context → loops → cost ≥ eşik → latency (≥300 sn) → warning → ok.
Sağlık skoru 0–100: 100 − (retry_oranı·30 + döngü·25 + timeout_oranı·20 +
context_risk·15 + compaction·10), kırpılmış; formül `estimator_version`'lı.

### 1.2 Proje zekâsı (MP §15)
Proje anahtarı = `cwd` hash'i (sensitive) → görünen ad kullanıcı eşlemesi.
Maliyet/gün, model karışımı, skill/agent/MCP kırılımı (transcript
`attribution*` + OTel öznitelikleri — bedava), commit atıfı (VibeBill:
0.6·dosya + 0.25·zaman + 0.15·dal, güven katmanı, waste/in-progress/overhead/
out-of-scope kovaları), **koruma yasası** her raporda.

### 1.3 Model zekâsı (MP §16)
Model başına: istek, token bileşimi, cache oranı, $/istek, $/çıktı token,
hata/refusal oranı; `fast`/`effort` etkisi; "aynı iş daha ucuz modelle olur
muydu" **yalnız gölge karşılaştırma** olarak (`shadow` fiyatı, toplamlara
karışmaz, açıkça etiketli).

### 1.4 Kota zekâsı (MP §17)
`QuotaSnapshot` serisi → pencere başına: kullanım, kalan, `resets_at`,
pace (v1), forecast (v2), model kapsamlı pencereler (`weekly_scoped`),
severity, "sıfırlanmaya kalan" ve **kota birimi** yalnız Research Mode
estimator'ından gelen bant. Token geçmişi kota tahmininde yalnız takvim
ağırlığı verir; token→yüzde dönüşümü yapılmaz.

### 1.5 Cache ekonomisi
Hit oranı = cache_read / input_total; yazma payı 5m/1h; `prompt_cache`
statusline alanları (warm, ttl, expires_at, miss_causes, recache_tokens_if_cold);
ölçülmüş TTL gerçekleri (5 dk: 300–420 sn; 1 sa: 56 dk); "soğuma riski"
uyarısı (`expires_at − now < 60 sn` ve `recache_tokens_if_cold` büyükse).

## 2. Tahmin motoru (MP §18–19)
### 2.1 v1 — doğrusal pace (Core)
```
expected = elapsed/duration·100 ; delta = used − expected
aşama: |Δ|≤2 onTrack · ≤6 slightly · ≤12 ahead/behind · >12 far
rate = used/elapsed ; eta = (100−used)/rate ; willLast = eta ≥ remaining
kural: elapsed==0 ∧ used>0 → hesaplama yok ; reset sonrası 180 sn tolerans
```
### 2.2 v2 — harman (Intelligence)
Adaylar: yakın eğim (`0.52·min(1,n/6)`), tarihsel medyan (`0.34·min(1,k/5)`),
davranışsal takvim (`0.14`); `projected = max(used, ağırlıklı ort.)`;
güven = kapsama·0.38 + geçmiş·0.30 + tazelik·0.20 + aktivite·0.12
(≥0.72 high, ≥0.35 medium, altı learning); bant = clamp(max(4, 18(1−conf))
+ min(12, 0.35·MAD·1.4826 + 0.5·spread), 4, 28); hedef = clamp(5 + (1−conf)·8,
5, 13); hüküm: atRisk (proj≥100) → watch (upper≥100) → learning → surplus
(medyan fazla ≥25 ∧ kötümser ≥10) → enough. Diagnostics saklanır.
### 2.3 Yöntem karşılaştırma protokolü (backtest)
Kaydedilmiş `quota_snapshots` üzerinde, her pencere döngüsü için t anında
tahmin edilen "reset'teki kullanım" vs gerçek; ölçütler MAE, bant kapsama
(%), hüküm doğruluğu. Adaylar: sabit (son değer), doğrusal, yakın eğim,
tarihsel medyan, harman. En iyi yöntem **sürümlü konfigürasyon** olarak
yayınlanır; asla otomatik model eğitimi. Rapor `cci estimator backtest`.
### 2.4 Estimator sürümleme (MP §29)
`estimators/registry.py`: `{id, version, params_hash, since}`; her
`Estimate` bunu taşır; sürüm değişince eski tahminler kalır, `realized`
alanı gerçekle dolar (`recommendation.evaluated`/`estimate.realized`).

## 3. Anomali tespiti (MP §20)
Kişisel taban çizgisi (P39): 5 saatlik blok hacmi P50/P90 (Maciek'in P90'ı
**limit değil, taban**), saatlik oran, oturum maliyeti dağılımı. Kurallar:
- oran uyarısı: `current/baseline ≥ 2` (warning) / `≥ 4` (critical), en az
  N=20 örnek;
- döngü parmak izi (§1.1), retry fırtınası (≥5/10 dk), 429 patlaması;
- context riski (`used ≥ %85` ve auto-compact yakın);
- kota pace `farAhead` + forecast `atRisk`;
- sağlayıcı: gecikme p95 kayması, `provider.schema_change`.
Her anomali `evidence[] {metric, value, baseline, ratio}` taşır.

## 4. Uyarı motoru (MP §21-öncesi)
Kural = koşul + severity + cooldown + dedupe_key + kanal. Kanallar: tray
bildirimi, CLI çıkışı, snapshot `alerts[]`, yerel webhook (loopback).
Fırtına önleme: aynı `dedupe_key` cooldown içinde tekrar etmez; dakikada ≤3
bildirim; sessiz saatler; severity yükselince cooldown kırılır. Uyarı
yalnız **Observed/Derived** kanıta dayanırsa "kesin", Predicted'e dayanırsa
"olası" etiketi.

## 5. "Şu anda ne yapmalıyım?" (MP §21)
Girdi: aktif oturum teşhisi, kota pace/forecast, cache durumu, taban çizgisi,
zaman (reset'e kalan), proje bağlamı. Deterministik merdiven:
1. Kota `atRisk` ve reset yakın → "reset'i bekle / işi böl" (Predicted, güven).
2. Kota `atRisk` ve reset uzak → "ucuz modele geç / effort düşür" (gölge
   karşılaştırma ile tahmini tasarruf).
3. Döngü/retry tespit → "oturumu durdur, bağlamı temizle" (Observed).
4. Context ≥ %85 → "compaction öncesi özetle / yeni oturum" (Observed).
5. Cache soğumak üzere ve büyük yeniden yazım → "şimdi devam et" (Observed).
6. Sabit bağlam ≥ 20k token → "kullanılmayan MCP/skill'i kapat" (Derived).
7. Hiçbiri → "yolunda; sonraki kontrol <t>".
Her öneri: kanıt listesi, beklenen etki (`Figure`, çoğu `estimated`),
geri alınabilir eylem (Intel: act günlüğü), sonradan `realized`.

## 6. Yeniden üretilebilirlik (MP §30)
- Tüm türetimler saf fonksiyon (events, config, now); `cci replay`.
- `summary_version`, `estimator.version`, `pricing_version`,
  `pricing_effective_at` her çıktıda.
- Aynı `events` + aynı sürümler → bit-eşit özet (golden test).
- Fiyat yenileme yeni `pricing_version`; eski maliyetler yeniden hesaplanmaz,
  istenirse `cci replay --pricing <v>`.

## 7. Raporlar (Core)
`cci today|daily|weekly|monthly|session <id>|project <k>|model|quota|cache|
doctor` — hepsi `--json` ve `--strict` (koruma yasası ihlali → çıkış 3).
