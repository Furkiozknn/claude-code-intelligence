# Faz 6 · Sentez — kalıplar, anti-kalıplar, çözülmemiş problemler, rekabet

Girdi: `notes/deep/*.md` (20 repo, kaynak kod düzeyi), `notes/00–03`,
`reports/top20.md`, `reports/catalog.md` (batch-06 sonrası). Her iddianın
yanında kaynak repo kısaltması var; kaynak okunmadan yazılan hiçbir kalıp yok.

Kısaltmalar: CZ CodeZeno · CM claude-meter · CB codeburn · CU ccusage ·
TT toktrack · TY tycho · MK Maciek · VB vibe-bar · CP claude-pace · CX codexU ·
AW ActivityWatch · LL litellm · OL openllmetry · DS disler · ZQ zcquant ·
AT agenttrace · TK TokenTracker · CE cacheeconomics · VL VibeBill · TB tokentab.

Aşama etiketi (MP §36 "overbuild yok"): **Core** (Aşama 1) · **Adv** (2) ·
**Intel** (3) · **Eco** (4).

---

## 1. Kalıp kataloğu

### 1.1 Toplama (collection)
| # | Kalıp | Kaynak | Kanıt | Aşama |
|---|---|---|---|---|
| P1 | **Çok kaynaklı, sınıflandırılmış toplama:** resmî OTLP (metrik+olay+trace) birincil, transcript artımlı ikincil, statusline/hook yardımcı, kota poller ayrı | notes/01–02, CU, CB | Hook'ta token yok; OTel'de kota yok; transcript 30 günde siliniyor — hiçbiri tek başına yetmiyor | Core |
| P2 | **Sağlayıcı arayüzü** `discover / collect / normalize / capabilities / health` + `probeRoots` ("nereye baktım") + `SessionSource` (aynı sağlayıcı, birden çok kök) | CB, TT (`CLIParser`, `SourceInstance`), CU (adaptör crate'leri) | Üç lider araç bağımsız olarak aynı şekle yakınsadı | Core |
| P3 | **Kimlik dosyası okuma sertleştirmesi:** symlink reddi, mod bitleri, boyut sınırı, aç-öncesi/sonrası stat, yalnız bellek, asla diske | CB `readSecureFile`, CZ | Token sızması tek en büyük risk | Core |
| P4 | **Nazik kota poller:** sabit aralık (≥180 sn), 429'da `retry_after`/başlık (min 60 sn), 401'de bir kez yeniden oku, **asla token rotasyonu/yenileme**; bağlantı durumu enum'u (connected/stale/accessDenied/transient/terminal/rateLimited) | CB, CZ (429'da kota harcama yok), CP | onWatch anti-örneği; endpoint belgesiz | Core |
| P5 | **Hesap kimliği olmadan hesap seviyesi veri cache'lenmez** — kimlik yoksa `--` | CP karar kaydı | Foundry/Max karışması vakası | Core |
| P6 | **Reset toleransı** (180 sn) ve "taze pencere geri dolduruldu → tahmin yok" | VB, TK (cache reset anında erken sona erer) | Pencere geçişinde sahte oran | Core |
| P7 | Statusline betiği **iptal edilebilir**, hızlı, temp dosya bırakmayan | CP (3 008 yetim temp dosya) | Claude Code devam eden betiği öldürüyor | Adv |
| P8 | Hook'lar **fail-open**: her zaman exit 0, karar JSON'da, `async:true` | CB guard, TB SDK | Ölçüm kaybı kabul, iş kaybı değil | Core |
| P9 | OTLP alıcı: JSON + protobuf + gRPC üçü de; `/v1/logs` ve `/v1/traces` kabul; **hiçbir öznitelik atılmaz** | ZQ (karşı örnek), notes/02 | `api_request` olayı asıl zenginlik | Core |
| P10 | Heartbeat birleştirme (`pulsetime`): aynı değerli tekrarlı anlık görüntüler tek aralığa çöker | AW | Depolama/sorgu maliyeti | Adv |
| P11 | Süreye göre pencere sınıflandırma (300 dk / 10 080 dk / 28–31 gün) + `unclassified` + `authoritative` bayrağı | CX | Sağlayıcı değişim tespiti bedava | Core |

### 1.2 Normalizasyon ve tekilleştirme
| # | Kalıp | Kaynak | Aşama |
|---|---|---|---|
| P12 | Dedup anahtarı `(message.id, requestId, sessionId)`; `requestId` yoksa `message.id+session(+ts)`; **kazanan = en büyük token toplamı** (tie: yeni şema) | CU, TY (ADR 0002 max output) | Core |
| P13 | **Sidechain replay** (`/btw`, `isSidechain`): ebeveyn kalır, replay atılır | CU #913 | Core |
| P14 | **Advisor iterasyonları** `usage.iterations[type=advisor_message]` ayrı model satırı; üst seviye usage = son iterasyon; sıfırsa iterasyon toplamı | CU, VL | Core |
| P15 | Sentetik kayıtlar (`<synthetic>`, `isApiErrorMessage`) toplama girmez, ayrı sayılır; `codex-unknown` sınıfı; zaman damgası sınırı [2000, 2100) | TY | Core |
| P16 | `input_tokens` anlamı sağlayıcıya göre (Anthropic: cache hariç; OpenAI/Gemini/semconv: dahil) → **iki alan** (`input`, `input_total`) ve adaptör belgesi | TY, VL, notes/03 | Core |
| P17 | Cache yazımı **5m/1h ayrı**; karışık TTL işaretleri bilinemez → `None`, tahmin yok | TY, CE | Core |
| P18 | Model anahtarı eşleştirme: tarih son eki, bölge öneki, `::provider` bileşik; bilinmeyen model sayacı | TT, LL, VL | Core |
| P19 | Kaynak kapsamı `account | local` ve dışlama gerekçesi çıktıda; hesap seviyesi kaynaklarda LWW ve "yokluk ≠ silme" | TK | Adv |
| P20 | `retroactive_reconciliation`: bazı kaynaklar geçmiş günleri yeniden yazar → o günler tam kümeden yeniden hesaplanır | TT | Adv |

### 1.3 Depolama ve saklama
| # | Kalıp | Kaynak | Aşama |
|---|---|---|---|
| P21 | **Ham → normalize → özet** üç katman; ham yalnız izinli sınıflarda; özetler ham silinse de kalır (transcript 30 gün) | CM, TT, notes/02 §H | Core |
| P22 | Sürümlü özet cache (`CACHE_VERSION`), uyuşmazlıkta geçmişi koru + yeniden hesaplanabilenleri yenile | TT | Core |
| P23 | Ingest manifest (`size, mtime, bytesConsumed`), satır sınırından devam, bozukta sessiz tam yeniden inşa | VL | Core |
| P24 | Atomik yazım (pid'li temp + replace) ve ayrı `.lock` dosyası | MK, TT, CB act | Core |
| P25 | Yetim/budanmış kaynak girdileri tutulur (aylık toplam düşmez), 90 gün yaşlanma, `retainWhilePresent` | CB | Adv |

### 1.4 Analitik
| # | Kalıp | Kaynak | Aşama |
|---|---|---|---|
| P26 | **Koruma yasası:** her toplam = parçaların toplamı; tutmazsa gürültülü uyarı, `--strict` çıkış kodu | VL | Core |
| P27 | Rakam disiplini: `Figure{value, evidence_class, released, withheld_because, released_as DRAFT/RECONCILED, projected}`; toplam en zayıf parçayı miras alır; pencere vs projeksiyon ayrı iddia | CE | Core |
| P28 | Oturum teşhis modeli: retry/döngü maliyeti, araç+sonuç hash döngü parmak izi, araç p95/timeout, context bütçesi kırılımı, kullanılmayan araç; **deterministik dikkat merdiveni** | AT | Adv |
| P29 | Atıf: commit adayı penceresi, `0.6·dosya + 0.25·zaman + 0.15·dal`, güven katmanları (high/medium/low + advisory), forward-attach, waste/in-progress/overhead/out-of-scope kovaları | VL | Adv |
| P30 | Transcript `attribution*` + OTel `agent/skill/plugin/mcp` öznitelikleri → skill/agent/MCP maliyet kırılımı **bedava** | TY, notes/02 | Core |
| P31 | Cache ekonomisi: hit ratio, 5m/1h payı, `prompt_cache` statusline alanları, ölçülmüş TTL (5 dk: 300–420 sn; 1 sa: 56 dk) | CE, TY, notes/02 §C | Adv |
| P32 | Sabit bağlam maliyeti tahmini (talimat dosyaları + SKILL.md + MCP şeması) — içeriksiz | TK | Adv |
| P33 | Tarihe göre fiyat tarifesi (`pricing_effective_at`), LiteLLM 5 bileşen + 200k kademe, bundled snapshot + tek ağ çağrısı (asla otomatik) | CU, LL, VL | Core |
| P34 | Realized-vs-estimated: her öneri/tahmin ≥N gün sonra gerçekle karşılaştırılır, "işe yaramadı" hükmü | CB act report | Intel |

### 1.5 Tahmin
| # | Kalıp | Kaynak | Aşama |
|---|---|---|---|
| P35 | **v1 doğrusal pace:** `Δ = kullanım − beklenen`, aşamalar ±2/±6/±12, ETA, `willLastToReset` | VB `UsagePace`, CP | Core |
| P36 | **v2 harman:** yakın eğim (0.52·güvenilirlik) + tarihsel medyan (0.34·g) + davranışsal takvim (0.14); güven = kapsama·0.38 + geçmiş·0.30 + tazelik·0.20 + aktivite·0.12; belirsizlik bandı; uyarlanabilir hedef; hüküm atRisk/watch/learning/surplus/enough (çift koşul) | VB | Intel |
| P37 | Kota birimi estimator'ı: aday sayaçlar × hesap genelinde kümülatif aralıklar × percentile bandı; <3 nokta → yalnız min/median/max | CM | Intel |
| P38 | Tahmin motoru **sürümlü** (`estimator_version`), her çıktı `Predicted` + güven; token geçmişi kota tahmininde yalnız takvim ağırlığı | VB, MP §29 | Core |
| P39 | Kişisel taban çizgisi (P90 blok hacmi) = **anomali eşiği**, "limit" değil | MK (yeniden konumlandırma), AT `CostAlert` | Adv |

### 1.6 Gizlilik ve güvenlik
| # | Kalıp | Kaynak | Aşama |
|---|---|---|---|
| P40 | **Yapısal gizlilik:** zarf tiplerinde içerik alanı yok; "gizlilik incelemesi = grep" | TY ADR 0001 | Core |
| P41 | Allow-list olay şeması + `FORBIDDEN_KEYS` özyinelemeli + jenerik hata mesajı; gövde boyut sınırı | CE, TB | Core |
| P42 | Yazılı tehdit modeli: loopback, 0700/0600, artık riskler | TB | Core |
| P43 | Hata metni redaksiyonu (Bearer/sk-ant/ya29/gh*/JWT), 240 karakter | CB | Core |
| P44 | Dışa akış varsa: alan anlamları listesi + rıza parmak izi (alanlar/hedef/kadans değişince yeniden rıza) + makbuz | CB sync | Eco |
| P45 | Proje adları tuzlu takma ad (`.salt` 0600) MCP/paylaşım yüzeylerinde | CB mcp | Adv |
| P46 | Tedarik zinciri: klonlanan repoların `.claude/` içeriği çalıştırılmaz; araştırma modu belgesinde uyarı | (bu oturum, TT klonu) | Core |

### 1.7 UX ve yüzeyler
| # | Kalıp | Kaynak | Aşama |
|---|---|---|---|
| P47 | Tek backend → **atomik durum dosyası** (JSON snapshot, `generated_at`, hesap kimliği) → hafif yüzeyler poll eder; HTTP/WS ek | MK state, CZ persist | Core |
| P48 | `time_until_display_change`: yüzey yalnız görünen değer değişince yenilenir | CZ | Adv |
| P49 | Dürüst yer tutucu (`--`), bağlantı durumu metni, "authoritative değil" işareti | CP, CB, CX | Core |
| P50 | Renk rolü pencere türüne bağlı; palet paketi; renk körlüğüne uygun ısı haritası | CX, TT | Adv |
| P51 | Explainability: tahmin diagnostics'i (projeksiyon adayları, kapsama, örnek sayısı) ve atıf alt skorları görünür | VB, VL | Adv |

### 1.8 Kontrol ve eylem
| # | Kalıp | Kaynak | Aşama |
|---|---|---|---|
| P52 | Guard: oturum maliyeti soft/hard/checkpoint cap'leri, `deny` + gerekçe, oturum başına kaldırma | CB | Intel |
| P53 | Act günlüğü: kilit → yedek → bayat plan hash kontrolü → uygula → hash → günlük; hata = ters sırada geri al | CB | Intel |
| P54 | HITL (soru/izin/seçim) ayrı, loopback + yetki + zaman aşımı; çekirdeğe girmez | DS (karşı örnek) | Eco |

### 1.9 Mühendislik disiplini
| # | Kalıp | Kaynak | Aşama |
|---|---|---|---|
| P55 | ADR + spec + "gerçek kazanır" kuralı; SCHEMA.md gerçek kayıtlardan sayılarla | TY | Core |
| P56 | Protokol alanları belgeye karşı doğrulanır, doğrulama tarihi kodda; `SCHEMA_VERIFIED` bayrağı | CB hooks, VL | Core |
| P57 | `doctor`: "bu sayılara güvenebilir miyim" — sayaçlar (atlanan satır, bilinmeyen model, sentetik, dedup) | TY, CB, TK | Core |
| P58 | Spesifikasyon = çalıştırılabilir modül + SQL/başka uygulama testle sabitlenir | TK dedup | Adv |

---

## 2. Anti-kalıplar (vaka ile)
| # | Anti-kalıp | Vaka | Neden yanlış |
|---|---|---|---|
| A1 | Token rotasyonu / istek limiti atlatma | onWatch | ToS ihlali, hesap riski |
| A2 | Kendi başına OAuth token yenileme ve diske yazma | TK Codex refresh, CZ `claude -p .` | Resmî istemciyle yarış, kota harcama, kimlik dosyası bozulması |
| A3 | Tam payload + transkript depolama, redaksiyon yok | DS (`payload`, `chat`) | Gizlilik sınıfı yok; sızıntı tek dosya uzağında |
| A4 | İçeriği yerel cache'te tutma (sınıflandırma bahanesiyle) | CB `userMessage` | Yerel olsa da SENSITIVE; yedeklere sızar |
| A5 | User-Agent taklidi | CB `claude-code/2.1.0` | Etik/ToS gri; sağlayıcı davranış değiştirince kırılır |
| A6 | Öznitelik atan, protobuf işlemeyen, logs/traces düşüren OTLP alıcı | ZQ | Sessiz veri kaybı; "200 OK" yalan |
| A7 | Hesap kimliği olmadan kota snapshot cache'i | CP v0.8.1 | Başka hesabın kotası gösterildi |
| A8 | "Limit" adıyla Inferred sayı sunmak | MK P90 | Kota birimi kanıtsız; kullanıcı yanlış karar verir |
| A9 | İlk-kazanır dedup, TTL ayırmayan fiyat | eski CU, prototip | %2/3 varyans hatası; kısmi kayıt kalır |
| A10 | Şema göçü sürümsüz (`PRAGMA` ile sütun ekleme), tema pazarı gibi kapsam şişmesi | DS | Bakım ve yeniden hesap imkânsız |
| A11 | Sabit çarpanlar (cache read = 0.1×) | CE çarpanları | Model başına oran değişiyor (fable-5-1: %2.5) |
| A12 | Rakamı mutabakatsız basmak, tek saatlik trace'ten aylık projeksiyon | CE'nin kendi geçmişi ($180/ay) | Güven kaybı |
| A13 | Temp+rename atomikliği iptal edilebilen süreçte | CP | Yetim dosya yığını |
| A14 | Kabuk rc dosyasına env yazmak | ZQ setup | Taşınabilir değil; `settings.json env` var |

---

## 3. Çözülmemiş problemler (deney planıyla)
| # | Problem | Bilinen | Hipotez / deney | Sahip faz |
|---|---|---|---|---|
| U1 | **Kota birimi** (token → yüzde) | Hiçbir araç kanıtlayamadı; `limits[]` model kapsamlı pencereler; cache/model ağırlıkları belirsiz | CM estimator'ı OTLP `api_request` + kota poller ile çalıştır; ≥30 gün veri; percentile bandı yayınla, nokta tahmin asla | Stage 3 |
| U2 | **OTLP alıcı kapalıyken** Claude Code davranışı | Belge sessiz; `[3P telemetry]` debug | Alıcıyı kapat, `claude --debug` çıktısını ve gecikmeyi ölç; tampon var mı | Stage 1 |
| U3 | **Hesap kimliği** çoklu hesap/sağlayıcıda | statusline'da yok; OTel `user.account_uuid` var; kimlik dosyasında `subscriptionType` | Kota snapshot anahtarı = OTel account_uuid ∨ kimlik dosyası parmak izi; yoksa `--` | Faz 7 |
| U4 | `/api/oauth/usage` istek sınırı ve `Retry-After` | ~5/token; codeburn gövdede `retry_after` okuyor | Tek 429 gözlemi (nazik), başlık ve gövde kaydı | Stage 1 |
| U5 | `output_tokens` akış ortası anlık görüntü | claude-code#27361 | Aynı message.id için son kayıt vs OTel `api_request.output_tokens` karşılaştır | Stage 2 |
| U6 | Sidechain/advisor/iterations çift sayımının **tam kümesi** | CU #913, VL iterations | Kendi transcript'lerimizde `message.id` çakışma taraması; `doctor` sayaçları | Stage 2 |
| U7 | Cache TTL karışımı (5m+1h aynı istek) | CE: bilinemez; TY: `ephemeral_5m/1h` var | Claude Code'da çözülür; diğer sağlayıcılarda `None` | Faz 7 |
| U8 | Claude Desktop oturumları (30 gün muaf, farklı token cache) | notes/02 §F, §H | Desktop adaptörü ayrı yaşam döngüsü; OSCrypt opt-in | Stage 4+ |
| U9 | OTel GenAI semconv `development` | alan adları değişebilir | Dışa aktarım çeviri tablosu sürümlü; iç model bağımsız | Faz 7 |
| U10 | "Aktif zaman" tanımı (Claude `active_time` vs insan-önünde) | AW afk | Opt-in AW adaptörü; iki metrik ayrı isimle | Eco |

---

## 4. Top-20 karşılaştırma matrisi (§8 boyutları)
● güçlü ◐ kısmi ○ yok/zayıf

| Repo | Toplama | Veri modeli | Depolama | Analitik | Tahmin | Doğruluk disiplini | Gizlilik | UX | Kontrol |
|---|---|---|---|---|---|---|---|---|---|
| CB codeburn | ● 46 sağlayıcı | ● | ● artımlı | ● waste/grade | ◐ | ● realized-vs-est | ◐ içerik cache | ● | ● guard/act |
| CU ccusage | ● 19 adaptör | ● | ◐ | ● | ◐ blok | ● dedup/sidechain | ● | ● | ○ |
| TY tycho | ◐ | ● zarf | ○ bellek | ● | ◐ | ● ADR/spec | ● yapısal | ◐ | ○ |
| TT toktrack | ● 9 CLI | ● | ● sürümlü cache | ◐ | ○ | ◐ | ● | ● TUI | ○ |
| VB vibe-bar | ● kota API | ◐ | ◐ | ◐ | ● harman | ● bail-out | ◐ | ● | ○ |
| CZ CodeZeno | ● kimlik zinciri | ○ yüzde | ◐ | ○ | ◐ | ◐ | ◐ | ● tema | ○ |
| CM claude-meter | ● proxy | ● Record | ◐ ham | ◐ | ● estimator | ◐ | ○ ham gövde | ○ | ○ |
| MK Maciek | ◐ | ◐ | ◐ | ◐ | ◐ P90 | ○ Inferred | ◐ | ● | ○ |
| CP claude-pace | ◐ stdin | ○ | ○ (bilerek) | ○ | ◐ pace | ● dürüst `--` | ● | ◐ | ○ |
| CX codexU | ● app-server | ● normalizer | ◐ | ○ | ◐ | ● authoritative | ◐ | ● | ○ |
| AW ActivityWatch | ● OS | ● bucket/event | ● | ◐ | ○ | ◐ | ● | ◐ | ○ |
| LL litellm (fiyat) | — | ● şema | — | — | — | ◐ tarihli | — | — | — |
| OL openllmetry | ● SDK | ● semconv | ○ | ○ | ○ | ◐ | ○ içerik attr | ○ | ○ |
| DS disler | ● hook | ○ payload | ◐ SQLite | ○ | ○ | ○ | ○ | ● canlı | ◐ HITL |
| ZQ zcquant | ◐ OTLP JSON | ○ | ○ | ○ | ○ | ○ | ◐ | ○ | ○ |
| AT agenttrace | ● 14 ajan | ◐ | ◐ | ● teşhis | ◐ | ◐ kanıt | ◐ | ● TUI | ○ |
| TK TokenTracker | ● 36 araç | ◐ | ◐ | ◐ context | ○ | ◐ LWW | ○ bulut | ● | ○ |
| CE cacheeconomics | ◐ collector | ● allow-list | ◐ | ● cache | ○ | ● Figure | ● | ○ | ○ |
| VL VibeBill | ● 4 adaptör | ● | ● manifest | ● atıf | ○ | ● koruma yasası | ● | ◐ | ○ |
| TB tokentab | ◐ SDK | ◐ | ◐ | ◐ | ○ | ◐ | ● tehdit modeli | ◐ | ○ |

Hiçbir repo **Toplama + Doğruluk disiplini + Tahmin + Gizlilik + Kontrol**
beşini birlikte taşımıyor. Platformun boşluğu burası.

---

## 5. Rekabet tablosu (MP §38)
| Özellik | Bizim yaklaşım | En iyi mevcut | Neden daha iyi | Onlar nerede daha iyi | Ne alınacak |
|---|---|---|---|---|---|
| Resmî kota % | Poller (P4) + statusline tap + `limits[]` tamamı; Observed etiketi | CZ, VB, CB | `limits[]` model kapsamlı pencereler, hesap kimliği (P5), authoritative (P11) | CZ kimlik zinciri (Desktop OSCrypt) ve tema motoru | Kimlik zinciri opt-in; 429 kuralı |
| Token muhasebesi | OTLP olay + transcript artımlı; dedup P12–P15; iki `input` alanı | CU (Rust), TY | Üç kaynağı mutabakatla birleştirme; `doctor` sayaçları | CU adaptör genişliği (19), TT hız (3 GiB/s) | CU dedup kuralları birebir; TT cache tasarımı |
| Maliyet | Tarihli 5 bileşenli fiyat (P33) + `Figure` (P27); vendor-estimated ayrı | CU, TY, VL | Rakam mutabakatsız basılmaz; TTL ayrımı zorunlu | CU `cc` modu pratikliği | LiteLLM eşleme kuralları |
| Tahmin | v1 pace → v2 harman (P35–36), sürümlü, bant + güven | VB | Kota + token + takvim tek motor, estimator sürümü, realized-vs-est | VB'nin macOS UI entegrasyonu | Ağırlıklar/eşikler başlangıç değeri |
| Kota birimi | Estimator (P37) yalnız Research Mode + bant | CM | Aday sayaç seti + OTLP ile proxy'siz | CM proxy ham gövde görür (gerektiğinde) | Interval/percentile mantığı |
| Anomali | Kişisel taban (P39) + oran uyarısı + teşhis (P28) | AT | Deterministik merdiven + kanıt + geri alınabilir eylem | AT 14 ajan format desteği | Diagnostics şeması |
| Atıf | Transcript+OTel öznitelikleri (P30) + commit atıfı (P29) + koruma yasası | VL, CB | Sıfır maliyetli skill/agent/MCP kırılımı + güvenli commit eşlemesi | CB "kategori sınıflandırma" (içerik okuyor) | VL algoritması birebir |
| Çapraz sağlayıcı | Adaptör sözleşmesi (P2) JSON şema, `SCHEMA_VERIFIED`, account/local kapsam | CB, CU, TT | Doğrulama durumu ve kapsam kullanıcıya görünür | CB/TT/CU genişlik | Format gerçekleri (Codex/Gemini/aider/Copilot) |
| Gizlilik | Yapısal zarf (P40) + allow-list (P41) + sınıflandırma + tehdit modeli (P42) | TY, CE, TB | Dört kalıp tek yerde; Research Mode ayrı depo | — | Hepsi |
| Çoklu yüzey | Durum dosyası (P47) + HTTP/WS; CLI/TUI/web/tray/statusline aynı backend | MK state, CZ tray, CP statusline | Tek kaynak, `time_until_display_change` | CZ/VB yerel widget cilası | Snapshot şeması |
| Kontrol | Guard/act (P52–53) Intel aşamasında, fail-open, geri alınabilir | CB | Öneri motoruyla kapalı döngü (realized-vs-est) | CB olgunluk | Act günlüğü tasarımı |
| Self-observability | `doctor` + toplayıcı sağlığı + sayaçlar (P57) | TY, CB | Her sayı için "güven" görünümü | — | Sayaç listesi |
| Research Mode | Proxy yalnız burada; ham gövde ayrı, işaretli depo; tedarik zinciri uyarısı | CM | Varsayılan kapalı, sınıflandırılmış | CM basitliği | Proxy iskeleti |

---

## 6. Faz 7'ye devredilen kararlar (D)
1. **D1 Toplama:** OTLP alıcı (metrik+log+trace) birincil; transcript artımlı
   ikincil (manifest P23); statusline tap + hook yardımcı; kota poller ayrı
   süreç/döngü, P4 kuralları. Proxy yalnız Research Mode.
2. **D2 Birleşik model:** zarf içerik alanı olmadan (P40); `tokens{input,
   input_total, output, cache_read, cache_write_5m, cache_write_1h, reasoning}`;
   `evidence_class ∈ {observed, derived, estimated, predicted, inferred,
   vendor_estimated}`; `Figure` her para/tahmin alanında.
3. **D3 Dedup ve doğruluk:** P12–P17 birebir; `doctor` sayaçları; koruma
   yasası her rapor komutunda; `--strict`.
4. **D4 Depolama:** ham (izinli sınıf) / normalize (SQLite, WAL) / özet
   (sürümlü günlük cache) — transcript silinince özet kalır.
5. **D5 Tahmin:** v1 pace Core; v2 harman Intel; estimator sürümlü; kota
   birimi estimator yalnız Research Mode; her çıktı bant + güven.
6. **D6 Gizlilik:** sınıflar PUBLIC/INTERNAL/SENSITIVE/SECRET alan düzeyinde;
   allow-list ingest; loopback; 0700/0600; tehdit modeli belgesi; içerik
   hiçbir modda çekirdek depoya girmez.
7. **D7 Yüzeyler:** tek backend + atomik snapshot dosyası + HTTP/WS; yüzey =
   ince istemci; `time_until_display_change`.
8. **D8 Sağlayıcı sözleşmesi:** `discover/collect/normalize/capabilities/
   health/probeRoots`, `SCHEMA_VERIFIED`, kapsam account/local, süreye göre
   pencere sınıflandırma; JSON şema ile dil bağımsız.
9. **D9 Kontrol:** Core'da yok; Intel aşamasında guard/act, fail-open,
   günlüklü ve geri alınabilir.
10. **D10 Dil/teknoloji:** karar Faz 7'de; kanıt: lider araç Rust'a geçti
    (CU), TT Rust 3 GiB/s; prototipimiz Python. Ölçüt: tek ikili dağıtım,
    Windows tray, OTLP protobuf kütüphanesi olgunluğu.
