# Derin analiz · Maciek-roboblog/Claude-Code-Usage-Monitor

**Okunan:** `src/claude_monitor/core/p90_calculator.py`, `src/claude_monitor/output/state.py`.
**Bilinen:** Python + Rich TUI, plan profilleri (pro/max5/max20/custom), 5 saatlik
blok modeli (ccusage türevi), burn rate, P90 otomatik limit. Kategori:
transcript tabanlı CLI monitör — **kota yüzdesini bilmiyor**, token limitini
**tahmin ediyor**.

## P90 limit tahmini (`p90_calculator.py`)
- Girdi: bloklar `{isGap, isActive, totalTokens}`.
- Aday = tamamlanmış (gap değil, aktif değil) ve `totalTokens ≥ limit·eşik`
  koşulunu **bilinen limitlerden** (COMMON_TOKEN_LIMITS) en az biri için
  sağlayan bloklar ("limite çarpmış" oturumlar); hiç yoksa tüm tamamlanmış
  bloklar; o da yoksa `default_min_limit`.
- Sonuç: `quantiles(n=10)[8]` = **P90**, alt sınır `default_min_limit`.
- 1 saatlik TTL'li `lru_cache` (anahtar = `time//ttl`).
- **Eleştiri:** "limit" = kullanıcının **geçmişte ulaştığı** en yüksek token
  toplamlarının P90'ı; gerçek kotayla ilişkisi kanıtsız (kota biriminin token
  olmadığı biliniyor — bkz. claude-meter). Kullanıcıya "limit" diye sunulması
  MP §10'a göre en fazla **Estimated**, dürüstçe **Inferred**. Prototipimiz bu
  yüzden resmi yüzdeyi tercih etmişti.

## Durum dosyası (`state.py`, #184)
- Aynı anlık görüntüyü `~/.claude-monitor/state/latest.json`'a **atomik**
  (pid'li temp + `os.replace`) yazar; "yol arkadaşları" (status bar, tray,
  dashboard) **dosyayı poll eder**. Headroom'un `~/.claude/headroom-usage.json`
  örneğiyle aynı kalıp.
- Not: tek paylaşılan dosya; eşzamanlı monitörler birbirini ezerse profil/oturum
  anahtarı eklenecek (yazılı TODO).

## Platforma aktarılacaklar
1. **Çoklu yüzey için "durum dosyası" kalıbı**: tek backend → atomik JSON
   snapshot → hafif yüzeyler (statusline, tray, waybar) poll eder. Bizim
   tasarımda IPC seçeneklerinden biri (HTTP/WS'e ek, en düşük bağımlılık).
   Snapshot şemasına **hesap kimliği** ve `generated_at` zorunlu (claude-pace
   dersi).
2. P90 yaklaşımı: **kullanıcı token-limit tahmini** olarak değil, "senin
   tipik 5 saatlik hacmin" (kişisel taban çizgisi, anomali için) olarak
   yeniden konumlandırılabilir.
3. Plan profilleri fikri → platformda `plan` yalnız etiket; limit sayısı
   kullanıcıdan istenmez, resmi yüzdeden okunur.
