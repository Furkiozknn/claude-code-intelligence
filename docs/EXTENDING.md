# EXTENDING — eklenti mimarisi

Durum: Faz 7 taslağı. Kararlar: sentez D8, ARCHITECTURE §6 (dil bağımsız
adaptör). Kanıt: codeburn `plugins/` + manifest, toktrack `ParserRegistry`,
ccusage adaptör crate'leri.

## 1. Eklenti türleri
| Tür | Ne yapar | Örnek |
|---|---|---|
| `adapter` | sağlayıcı/ajan verisini birleşik modele çevirir (`PROVIDERS.md` §2) | codex, gemini-cli, aider |
| `collector` | yeni kanal (ör. IDE eklentisi, uzak snapshot) | vscode-otel-db |
| `estimator` | tahmin/analitik yöntemi | pace_v3, unit_estimator |
| `alert_sink` | uyarı kanalı (loopback) | desktop-notify, local-webhook |
| `surface` | yüzey (snapshot/WS okuyan) | waybar, gnome-shell, notch |
| `exporter` | dışa aktarım (Eco; rıza) | otlp-semconv, csv |

## 2. Manifest
```toml
[plugin]
name = "cci-adapter-codex"     version = "0.1.0"     kind = "adapter"
api_version = 1                                        # çekirdek sözleşme sürümü
entry = "python:cci_adapter_codex:main"               # veya "exec:./bin/adapter" (JSON-RPC/stdio)
[permissions]
fs_read  = ["~/.codex/sessions/**", "~/.codex/auth.json"]   # glob, salt okunur
fs_write = []                                                # adaptörler için her zaman boş
network  = []                                                # host listesi; boş = ağ yok
privacy_classes_produced = ["internal", "sensitive"]         # üretebileceği en yüksek sınıf
[capabilities]                                               # PROVIDERS.md §2 ile aynı anahtarlar
tokens = true  cost_vendor = false  quota = true  schema_verified = true  verified_at = "2026-09-07"
```
Kurallar: `fs_write` adaptörlerde boş olmalı (aksi red); `network` listesi
`ARCHITECTURE.md` §7 envanterine eklenir ve `doctor`'da görünür; `secret`
sınıfı üretemez (şema testi).

## 2b. Adaptör: bugün çalışan yol (Stage 2 + 15)

Manifest formatı (§2) hâlâ taslak. **Bugün gerçekten çalışan** ve testle
korunan yol Python giriş noktasıdır; üçüncü taraf paketi şunu yazar:

```toml
[project.entry-points."cci.adapters"]
my_tool = "cci_adapter_my_tool:build"
```

`build(env: Mapping[str, str], home: Path) -> ProviderAdapter` — `PROVIDERS.md
§2` arayüzünü karşılayan bir nesne döndürür. Keşif anında `assert_contract`
çalışır: geçmezse **yüklenmez**, nedeni `cci providers` çıktısında yazar, ve
çekirdek etkilenmez. Aynı adı birinci taraf bir adaptörle paylaşan eklenti de
reddedilir — sessizce üstüne yazmak, hangi adaptörün koştuğunu belirsizleştirir.

```
cci providers            # ulaşılabilen her adaptör + yüklenemeyenin nedeni
cci providers --strict   # bir eklenti yüklenemediyse çıkış 3
cci scan                 # kayıtlı her adaptörden toplar
```

Bunu ispatlayan testler `tests/test_adapter_plugins.py` içinde: adaptör paket
sınırının **dışına** yazılıyor (geçici dizin + kendi `.dist-info` meta verisi,
`pip install`in ürettiğinin aynısı) ve ürünün ona ulaşıp ulaşmadığı, kaydının
olay deposuna girip girmediği sorulıyor. Sözleşme testi bunu ispat edemez:
onun gördüğü adaptörler aynı dosyada, aynı elden yazılmış olanlardır.

## 3. Taşıma
- **In-process (Python entry point):** `[project.entry-points."cci.adapters"]`
  (§2b). Çalışıyor. İstisna eklentiyi devre dışı bırakır, çekirdeği değil;
  ayrı görev ve zaman aşımı henüz yok.
- **JSON-RPC 2.0 / stdio (`exec:`):** herhangi bir dil (Rust adaptör için
  yol). **Stage 15'te** (R-5); Core ve Adv yalnız in-process. Yöntemler
  `PROVIDERS.md` §2; çekirdek çocuk süreci başlatır, 30 sn yanıtsızlıkta
  öldürür, `health=down`. Ortam değişkenleri **iletilmez**
  (kimlik sızması); yalnız `CCI_PLUGIN_CONFIG` yolu.
- Sürüm uyumu: `api_version` eşleşmezse yüklenmez; şema `additionalProperties:
  false`.

## 4. Yaşam döngüsü
`discover` (dizin `~/.cci/plugins/*/manifest.toml` + yüklü paketler) →
`validate` (manifest şeması, izinler, imza opsiyonel) → `load` → `health`
periyodik → `disable` (hata eşiği: 5 ardışık) → `doctor` raporu.
Kullanıcı `cci plugin list|enable|disable|doctor`.

## 5. Test sözleşmesi (her eklenti)
- `fixtures/`: gerçek (redakte) örnek dosyalar + beklenen `Envelope` çıktısı
  (golden). Redaksiyon: içerik alanları `<redacted>`, kimlikler sahte.
- Şema testi: üretilen olaylar `EVENTS.md` allow-list'ine uyar; yasak anahtar
  yok.
- Dedup testi: aynı kayıt iki kez → tek `UsageRecord`.
- Koruma yasası testi: adaptörün günlük toplamı = kayıtların toplamı.
- Performans: 100 MB fixture ≤ 10 sn (in-process) / ≤ 30 sn (stdio).
- `schema_verified=true` ancak fixture'lar gerçek üründen ve tarihli ise.

## 6. Güvenlik incelemesi (kabul listesi)
1. `fs_write` boş; `network` gerekçeli ve minimum.
2. Kimlik dosyası okuyorsa `PROVIDERS.md` §3 kuralları (symlink, boyut, bellek).
3. Token yenileme/rotasyon **yok**; UA taklidi **yok**.
4. Log çıktısında redaksiyon testi geçer.
5. `.claude/` dizini veya hook/skill dosyası taşıyorsa **yüklenmez** (tedarik
   zinciri; bkz. `PRIVACY.md` §5).

## 7. Çekirdek genişletme noktaları (kod)

| Nokta | Durum |
|---|---|
| `cci.adapters.Registry.register()` / `builtin_registry()` / `cci.adapters` giriş noktası grubu | **çalışıyor** (§2b) |
| `estimators.register()` | henüz yok — estimator'lar `cci/forecast` içinde adıyla seçiliyor |
| `alerts.register_sink()` | henüz yok — kanallar `cci/alerts` içinde sabit |
| `surfaces.snapshot_schema` | sürümlü JSON şeması var; yüzeyler yalnız bunu okur |

Snapshot şeması geriye uyumlu: alan silme → major sürüm.

## 8. Ne yazıyor, ne çalışıyor

Bu belgenin geri kalanı (§2 manifest, §3 stdio, §4 `cci plugin` komutları,
§5–6 kabul listeleri) **tasarım**dır; kod karşılığı yoktur. Ayrımı yazmak,
belgeyi harfiyen izleyen birinin çağrılmayacak bir eklenti yazmasından iyidir.
