# Araştırma

Bu klasör MASTER_PROMPT §2–9'un uygulaması: keşif, puanlama, veri toplama
analizi, Top 20, derin analiz.

## Dosyalar

| Yol | Ne |
|---|---|
| `catalog.jsonl` | Ana veri seti. Her satır bir repo. **Elle düzenleme; `catalog.py ingest` kullan.** |
| `inbox/batch-NN.json` | Bir keşif turunun ham girdisi. Ingest edildikten sonra da tarih kaydı olarak kalır. |
| `tools/catalog.py` | ingest / stats / list / score / top / report |
| `reports/` | Üretilen markdown raporlar (`catalog.md`, `top20.md` …) |
| `notes/` | Serbest analiz notları; derin analizler `notes/deep/<owner-repo>.md` |

## Kayıt şeması

```json
{
  "url": "https://github.com/owner/repo",
  "name": "owner/repo",
  "categories": ["claude-code", "quota"],
  "approach":   ["api-polling"],
  "surfaces":   ["tray"],
  "stars": 447,
  "summary": "Ne yapıyor, nasıl yapıyor, dikkat çeken şey.",
  "depth": "shallow | fetched | deep",
  "scores": {"data_collection": 8, "...": 0},
  "score_notes": {"data_collection": "neden 8"},
  "confidence": "low | medium | high",
  "source_queries": ["hangi aramadan çıktı"],
  "found_at": "2026-09-07"
}
```

### Kontrollü sözlükler

**categories** (MP §3):
`claude-code` `llm-usage` `cost` `quota` `dev-productivity` `coding-agent`
`observability` `proxy` `local-first` `timeseries` `desktop` `terminal`
`cross-provider` `privacy` `browser-ext` `statusline` `gui` `vscode`
`otlp` `meta` `library`

**approach** — veri nereden alınıyor (MP §4, §6):
`api-polling` (resmî/belgelenmemiş uç) · `jsonl-parsing` (yerel transcript)
· `proxy` (MITM / base_url) · `stdin-statusline` (Claude Code statusline
JSON'u) · `hooks` (Claude Code hook olayları) · `otlp` (OpenTelemetry
export) · `sdk-instrumentation` · `browser-scrape` · `os-monitor` ·
`log-parsing` · `sqlite-inspection` · `unknown`

**surfaces:**
`cli` `tui` `web` `tray` `taskbar` `menubar` `widget` `desktop-app`
`statusline` `vscode` `browser-ext` `daemon` `webhook` `library`
— keşifte eklenenler: `hardware` (ESP32 ekran, WiFi saat) · `mobile` ·
`gnome-shell` · `waybar` · `notch` (macOS çentik) · `mcp` (ajanın kendi
kullanımını sorgulayabildiği MCP sunucusu) · `skill` (Codex/Claude skill
olarak paketlenmiş pano) · `plugin` (Claude Code plugin) · `discord`
(uzaktan kontrol; izleme değil)

## Puanlama rubriği (MP §5)

Her kriter 0–10 puan; toplam = Σ (puan/10 × ağırlık), 0–100.

| Kriter | Ağırlık | 10 puan ne demek |
|---|---:|---|
| data_collection | 15 | Doğru kaynaktan, güvenilir, nazik, düşük maliyetle; yedek yol var |
| analytics | 12 | Oturum/proje/model/cache kırılımı, anlamlı türetilmiş metrikler |
| architecture | 12 | Temiz katmanlar (raw→normalize→analyze→present), test edilebilir |
| accuracy | 10 | Observed ile estimated ayrılmış; kaynağı belli; doğrulanabilir |
| prediction | 10 | Varış tahmini, güven aralığı, birden fazla yöntem |
| observability | 8 | Kendi sağlığını ölçüyor, hata modları görünür |
| ux | 7 | Bir bakışta anlaşılır, erişilebilir, tema, düşük bilişsel yük |
| extensibility | 7 | Yeni sağlayıcı/collector/UI çekirdeğe dokunmadan eklenebilir |
| privacy | 6 | Local-first, redaction, saklama politikası, dışarı sızmıyor |
| performance | 4 | Arka planda hafif; CPU/RAM/disk/ağ disiplinli |
| documentation | 3 | Kurulum + mimari + sınırlar dürüstçe yazılmış |
| community | 3 | Bakımlı, issue'lara yanıt, sürüm ritmi |
| cross_provider | 3 | Birden fazla sağlayıcı; adaptör arayüzü |

**Puan uydurma yasağı:** README/kaynak okunmadan (`shallow`) puan verilmez.
Bir kriter için bilgi yoksa boş bırakılır; `confidence` düşer.

## Anti-pattern listesi (baştan bilinen, araştırmayla büyür)

- **Token rotasyonu** ile sağlayıcı rate-limit'ini aşmak (onWatch). Hesap
  riski; "nazik toplama" ilkesine aykırı.
- **Headless tarayıcıyla scrape** (Gronsten). Kırılgan, ağır, sağlayıcı
  arayüzü değişince ölür.
- **Observed ile estimated'ı aynı sayı gibi göstermek.** Üç araç aynı
  veriden üç farklı "maliyet" üretti ($42 / $46 / $168) ve hiçbiri bunun
  tahmin olduğunu vurgulamadı.
- **Aynı bilginin iki yerde elle tutulması** (prototipte dört hata bundan).
