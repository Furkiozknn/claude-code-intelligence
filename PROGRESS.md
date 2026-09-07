# İlerleme Günlüğü — Claude Code Intelligence Platform

Bu dosya otonom çalışmanın hafızası. Her turda: (1) burayı oku, (2) aktif
fazın sıradaki parçasını yap, (3) bulguları gerekçelendirerek kaydet,
(4) commit at. Faz sırasını atlama; **araştırma bitmeden platform kodu
yazma** (araştırma araçları serbest).

**Kapsam:** `D:\Repolar\claude-code-intelligence`.
**Sınır:** GitHub'a yayınlama yok (`raporlar/ONAY-BEKLEYENLER.md`).
**Dil:** Türkçe. Kaynak kod yorumları ASCII olabilir; kullanıcıya görünen
metin düzgün Türkçe.

---

## Faz haritası (MASTER_PROMPT bölümlerine eşlenmiş)

| Faz | İçerik | MP § | Durum |
|---|---|---|---|
| 0 | Kurulum: depo, katalog aracı, prototip derslerinin aktarımı | — | ✅ |
| 1 | **Keşif** — ≥100 repo (hedef 150–300), 15 kategori, farklı teknik yaklaşımlar | 2–4 | 🔄 |
| 2 | **Puanlama** — 13 kriter/100 puan, her puan gerekçeli | 5 | ⬜ |
| 3 | **Veri toplama analizi** — yaklaşımların accuracy/reliability/privacy/… kıyası | 6 | ⬜ |
| 4 | **Top 20** — kategori çeşitliliği korunarak | 7 | ⬜ |
| 5 | **Derin analiz** — Top 20 kaynak kod seviyesi + iki referans repo özel inceleme | 8–9 | ⬜ |
| 6 | **Sentez** — pattern'ler, anti-pattern'ler, çözülmemiş problemler, rekabet analizi | 38 | ⬜ |
| 7 | **Mimari** — sistem/veri/event/collector/analytics/quota/forecast/anomaly/privacy/plugin/UI | 10–36, 39–40 | ⬜ |
| 8 | **Ürün spesifikasyonu** — product/UX/dashboard/CLI/TUI/alert | 22–23 | ⬜ |
| 9 | **Öz-eleştiri** — 18 soru, mimariyi yeniden optimize et | 41 | ⬜ |
| 10 | **İmplementasyon** — Stage 1–16, sırayla | 42 | ⬜ |
| 11 | **Benchmark → eleştiri → iyileştirme** döngüsü | 43, final | ⬜ |

Faz 1 tamamlanma ölçütü: katalogda ≥100 repo, her kategori ≥3 örnek, her
veri toplama yaklaşımı ≥2 örnek, iki referans repo dahil.

---

## Araştırma katalog protokolü

- Yeni bulgular `research/inbox/batch-NN.json` olarak yazılır, sonra
  `python research/tools/catalog.py ingest research/inbox/batch-NN.json`.
- URL'ye göre tekilleştirme otomatik. Aynı repo tekrar bulunursa alanlar
  birleşir, derinlik yükselir.
- `depth`: `shallow` (yalnızca arama sonucu) → `fetched` (README okundu)
  → `deep` (kaynak kod incelendi). **Puan yalnızca `fetched`+ için.**
- Puan uydurma: bir kriteri değerlendirecek bilgi yoksa o kriter boş kalır,
  toplam eksik veriyle hesaplanır ve `confidence` düşük işaretlenir.
- `python research/tools/catalog.py stats` kategori boşluklarını gösterir;
  sıradaki aramalar boşluklara göre seçilir.

---

## Günlük

### 7 Eylül 2026 — Faz 0 · Kurulum
- Depo açıldı. Prototip (`claude-quota-monitor`) döngüsü durduruldu; işi
  git'te (13 sürüm, 14 commit). Dersleri `research/notes/00-*`'a aktarıldı.
- `research/tools/catalog.py` yazıldı: ingest / stats / list / score /
  top / report. Rubric MP §5 ile aynı (13 kriter, toplam 100).
- Seed: bu oturumda gerçekten arama sonuçlarında görülen 41 repo
  `research/inbox/batch-00-seed.json` olarak girildi. 16'sı README'si
  okunmuş (`fetched`), gerisi `shallow`.
- Faz 1 için ilk keşif turu başlatıldı: Claude Code dışı 12 kategoride
  arama (maliyet, gözlemlenebilirlik, proxy, kota, geliştirici
  verimliliği, coding-agent, TUI, tray, redaction, zaman serisi,
  çapraz sağlayıcı, local-first).

### Sıradaki
- Faz 1: arama sonuçlarını `batch-01.json`'a işle, ingest, `stats` ile
  boşlukları gör, boşluklara göre ikinci tur arama.
