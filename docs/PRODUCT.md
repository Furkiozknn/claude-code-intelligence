# PRODUCT — ürün, UX, dashboard, CLI, TUI, uyarı spesifikasyonları

Durum: Faz 8 taslağı (MP §22–23, §43 Product). Kanıt: kullanıcı tercihi
(ekran alanı birincil ölçüt, minimal araç), prototip (`claude-quota-monitor`
widget/tray dersleri), vibe-bar/CodeZeno/claude-pace yüzeyleri, agenttrace
TUI, codeburn dashboard, ANALYTICS §5 merdiveni.

## 1. Ürün spesifikasyonu
**Kullanıcı:** Claude Code'u (Pro/Max ya da API) yoğun kullanan tek geliştirici;
ikincil: birden çok ajan/CLI kullanan geliştirici; üçüncül (Eco): ekip.
**İşler (jobs-to-be-done):**
1. "Kotam ne durumda, ne zaman biter, şimdi devam edeyim mi?" (kota zekâsı)
2. "Bugün/bu hafta ne harcadım, neye?" (usage + atıf)
3. "Bu oturumda bir şey ters mi gidiyor?" (teşhis, döngü, context)
4. "Ne yapmalıyım?" (öneri + kanıt + geri alınabilir eylem)
5. "Bu sayılara güvenebilir miyim?" (doctor, kanıt sınıfı)
**İlkeler:** ekran alanı sıfıra yakın (varsayılan yüzey statusline + tray);
her sayı kanıt rozeti taşır; tahmin gözlem gibi gösterilmez; yer tutucu
`--` dürüst; hiçbir yüzey hesap yapmaz (snapshot/API okur).
**Yapmayacakları:** kota atlatma, içerik gösterme/saklama, leaderboard,
tema pazarı, sürekli bildirim.

## 2. UX spesifikasyonu
### 2.1 Bilgi hiyerarşisi (her yüzeyde aynı sıra)
1. **Kota** (5s, 7g, model kapsamlı) — Observed; yaş etiketi (`12 sn önce`),
   `stale` ise soluk.
2. **Dikkat** — Advisor merdiveninin tek satırlık sonucu (ok/warning/…).
3. **Tahmin** — pace (v1) ve varsa forecast (v2) bant + güven; `learning`
   ise sayı yerine "öğreniyor (2/5 döngü)".
4. **Bugün** — oturum, token, maliyet (`Figure`; withheld ise `—` + sebep
   tooltip'i), istek.
5. **Modeller / atıf** — payı.
6. **Uyarılar** — aktif olanlar; çözülmüşler gizli.
### 2.2 Kanıt rozetleri
`●` observed · `◐` derived · `≈` estimated/vendor-estimated · `~` predicted
(bant ile) · `?` inferred. Rozet metnin parçasıdır (renge bağımlı değil;
renk körlüğü).
### 2.3 Renk anlamı
Yalnız severity için: normal / warning (≥70 %) / critical (≥90 %) — eşikler
ayarlanabilir; `light-dark()` ile tema; kontrast ≥ 4.5:1 testi (prototipten).
### 2.4 Dürüstlük kuralları
- Hesap kimliği yok → kota `--` (cache yok).
- `authoritative=false` snapshot → `!` işareti ve tooltip.
- `Figure.released=false` → sayı yok, `withheld_because` görünür.
- Pace `elapsed=0` → gösterilmez.
### 2.5 Açıklanabilirlik
Her tahmin/öneri tıklanınca "işini göster": adaylar, ağırlıklar, kapsama,
örnek sayısı, kanıt listesi (vibe-bar diagnostics, VibeBill alt skorları).
### 2.6 Minimal ayak izi modları
`statusline` (tek satır ≤ 40 karakter) → `tray` (ikon + tooltip) → `widget`
(120×40 px, tıklayınca büyür) → `TUI` → `web`. Kullanıcı tek moda kilitleyebilir.

## 3. Dashboard (web, loopback) spesifikasyonu
Sayfalar: **Şimdi** (hiyerarşi §2.1, canlı WS) · **Oturumlar** (liste;
dikkat sırası; teşhis detayı; zaman çizgisi) · **Projeler** (maliyet/gün,
atıf, waste kovaları, koruma yasası satırı) · **Modeller** (karışım, $/çıktı,
cache oranı, gölge karşılaştırma ayrı sekme) · **Kota** (pencere geçmişi,
reset takvimi, backtest sonuçları) · **Uyarılar/Öneriler** (geçmiş, realized
vs estimated) · **Doctor** (toplayıcı sağlığı, sayaçlar, sürümler, ağ
envanteri, telemetri değişkenleri) · **Ayarlar** (eşikler, saklama, sınıflar,
fiyat yenileme düğmesi).
Teknik: statik HTML+JS (CDN yok, inline), CSP, token'lı loopback API,
WS canlı; veri bağlama snapshot şeması + `/api/v1/*`. Tablo/grafikler
kendi minimal çizimi (bağımlılık yok).

## 4. CLI spesifikasyonu (`cci`)
```
cci now                      # hiyerarşi §2.1 tek ekran; --json
cci today|daily|weekly|monthly [--since --until --project --model --by agent|skill|mcp]
cci session <id>|--active    # teşhis + zaman çizgisi
cci project <key>            # maliyet, atıf, waste, koruma yasası
cci model                    # karışım, cache, $/çıktı; --shadow ayrı
cci quota [--history]        # pencereler, pace, forecast, backtest özeti
cci alerts [--history] | cci advise   # öneri + kanıt; --apply (Intel, act günlüğü) --undo <id>
cci doctor                   # sağlık, sayaçlar, "güvenebilir miyim"
cci setup [--otlp --statusline --hooks]   # settings.json env/statusLine/hooks yazımı (yedekli, geri alınabilir)
cci pricing refresh|show     # tek ağ çağrısı
cci replay [--from]          # türetilmiş tabloları yeniden üret
cci research …               # ayrı mod (RESEARCH_MODE.md)
cci daemon start|stop|status
```
Çıktı: tablo (TTY) veya `--json` (şema sürümlü); çıkış kodları: 0 ok ·
2 kullanım · 3 koruma yasası ihlali (`--strict`) · 4 daemon yok (salt okur
devam eder, uyarı) · 5 kimlik/erişim yok. Renk `NO_COLOR`'a saygı.

## 5. TUI spesifikasyonu
Ekranlar: Şimdi · Oturumlar · Projeler · Kota · Doctor. Tuşlar: `1–5`
ekran, `j/k` seçim, `enter` detay, `e` kanıt paneli, `a` öneri uygula
(onay), `r` yenile, `?` yardım, `q` çıkış. 2 sn canlı yenileme (snapshot),
80×24'te tam çalışır; renk körlüğü uyumlu; agenttrace sıralama/arama kalıbı.

## 6. Uyarı spesifikasyonu
| Kural | Koşul | Severity | Kanıt | Cooldown |
|---|---|---|---|---|
| quota.threshold | pencere ≥ %70 / %90 | warning / critical | Observed | pencere başına bir kez; severity artınca kırılır |
| quota.pace | pace `farAhead` ∧ reset > 1 sa | warning | Derived | 30 dk |
| quota.forecast | forecast `atRisk` (conf ≥ medium) | warning | Predicted ("olası") | 30 dk |
| session.loop | döngü parmak izi ≥ 3 | warning | Observed | oturum başına |
| session.retry_storm | ≥ 5 hata / 10 dk | critical | Observed | 10 dk |
| session.context | context ≥ %85 | warning | Observed | oturum başına |
| cost.spike | oturum maliyeti ≥ 2× / 4× taban | warning / critical | Derived (n ≥ 20) | oturum başına |
| cache.cooling | `expires_at − now < 60 sn` ∧ `recache_tokens_if_cold` ≥ 50k | info | Observed | 5 dk |
| provider.schema_change | yeni/eksik alan, sınıflanamayan pencere | info | Derived | gün başına |
| collector.down | toplayıcı ≥ 5 dk sağlıksız | warning | Derived | 15 dk |
Kanallar: snapshot `alerts[]`, tray bildirimi (critical + kullanıcı seçimi),
CLI `cci alerts`, yerel webhook. Fırtına önleme: dakikada ≤ 3, sessiz
saatler, aynı `dedupe_key` cooldown içinde tekrar etmez. Metin kuralı:
ne oldu · kanıt · ne yapılabilir (tek cümle) — asla "belki".

## 7. Tray / widget / statusline
- **Statusline** (≤ 50 ms, snapshot okur): `5h 72%● ⇡4% · 7d 84%● · $18.42≈ · ok`
  (rozetler dahil; alan yoksa `--`).
- **Tray** ikonu: yüzde halkası (5s), renk severity; tooltip hiyerarşi §2.1;
  menü: Aç (web), Öneri, Duraklat bildirim, Çıkış. `time_until_display_change`
  ile yenileme.
- **Widget** (prototipten): 120×40 px, her zaman üstte opsiyonel, tıkla →
  240×160 ayrıntı; sürüklenebilir; konum kalıcı.
