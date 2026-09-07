# Derin analiz · tokentab

**Okunan:** `docs/THREAT_MODEL.md`, `db/schema.ts`. **Okunmayan:** SDK
enstrümantasyonu, API sunucusu. TypeScript. Kategori: SDK enstrümantasyonu +
yerel sunucu + panel.

## Tehdit modeli (yazılı ve somut — Top-20'de tek)
- Sunucu **yalnız loopback**; dış arayüze bağlanmak açık bayrak ister.
- Veri dizini **0700**, DB dosyası **0600**.
- İstek gövdesi **1 MB üst sınır** (DoS/yanlışlıkla büyük içerik).
- **Ham içerik alanları kalıcılık öncesi reddedilir** (prompt/completion metni
  şemaya giremez).
- **SDK fail-open**: enstrümantasyon hata verirse uygulama çalışmaya devam
  eder; ölçüm kaybı kabul, kullanıcı iş kaybı kabul değil.
- API anahtarları yalnız ortam değişkeninden; DB'ye yazılmaz.
- Değerlendirme (eval) verisinin dış servise gönderimi **ayrı rıza bayrağı**.
- Artık riskler listelenmiş (aynı makinedeki başka kullanıcı süreçleri, yedek
  kopyalar, panelin XSS yüzeyi).

## Şema (özet)
Olay tablosu: sağlayıcı, model, token türleri, gecikme, durum, maliyet;
oturum/etiket boyutları; içerik alanı yok. (Ayrıntı için `db/schema.ts`.)

## Platforma aktarılacaklar
1. `docs/PRIVACY.md` (MP §25) **tehdit modeli** bölümü içermeli: yüzeyler,
   varsayılanlar (loopback, 0700/0600, boyut sınırı), artık riskler.
2. **Fail-open** kuralı: hiçbir toplayıcı (hook, statusline, OTLP alıcı)
   Claude Code'un çalışmasını engelleyemez — hook `async: true`, zaman aşımı
   kısa, hata = sessiz düşüş + self-observability sayacı.
3. Gövde boyut sınırı ve içerik-alanı reddi ingest sınırında (cacheeconomics
   allow-list ile aynı katman).
4. Dışa veri gönderimi (varsa) için ayrı rıza bayrağı.
