# Derin analiz · getagentseal/codeburn

**Okunan:** `app/electron/quota/{types,security,claude}.ts`, `src/providers/types.ts`,
`src/guard/{cli,hooks}.ts`, `src/act/apply.ts`, `src/act/report.ts` (grep),
`src/sync/consent.ts`, `src/mcp/redact.ts`, `src/quota/index.ts`,
`app/electron/telemetry.ts` (grep), README. **Okunmayan:** `src/parser.ts`
(2 000+ satır), `src/classifier.ts`, `src/optimize.ts`, `src/sharing/*`.
TypeScript; CLI + Electron menü çubuğu + Windows (Tauri) + web panel; **46
sağlayıcı**; 10.9k★. Top-20'nin **en geniş kapsamlı** ürünü — MP'nin
"Control" boyutuna (guard/act) en yakın örnek.

## Sağlayıcı arayüzü (`src/providers/types.ts`)
```
Provider { name, displayName, network?, durableSources?, modelDisplayName(),
           toolDisplayName(), discoverSessions() → SessionSource[],
           createSessionParser(source, seenKeys, dateRange) → {parse(): AsyncGenerator<ParsedProviderCall>},
           probeRoots?() → ProbeRoot[]  // doctor için "nereye baktım" }
```
- `SessionSource{path, project, provider, sourceId/Label/Path, sourceKind:
  claude-config|claude-desktop, agentName, retainWhilePresent}` — **kaynak
  örneği** (aynı sağlayıcı, birden çok `CLAUDE_CONFIG_DIR`; Claude Desktop ayrı).
- `ParsedProviderCall`: token 4'lü + `cachedInputTokens` + `reasoningTokens` +
  `webSearchRequests`, `costUSD` + **`costIsEstimated`**, `tools[]`,
  `bashCommands[]`, `subagentTypes[]`, `skills[]`, `speed: standard|fast`,
  `deduplicationKey`, `locAdded/locRemoved/editFailed`, Copilot `nanoAiu`
  (1e9 nano-AIU = 1 kredi = $0.01) ve `requestMultiplier`, `turnId`,
  `toolSequence[][]`, **`userMessage: string`**, `sessionId`, `project(Path)`,
  `prLinks[]`, `workingDirectory`, `activeDurationMs`, `toolWaitMs`.
- `network: true` → parmak izi/artımlı cache yok, her çalıştırmada yeniden;
  `durableSources` → dış süreç budayabilir, **yetim girdiler tutulur** (aylık
  toplam düşmesin), 90 gün yaşlanma (`retainWhilePresent` muaf).
- `probeRoots` → `codeburn doctor` "araç yok mu, yol mu yanlış" ayrımı.

## Kota (`app/electron/quota/*` → `src/quota/*`'ya port)
- `QuotaProvider{provider, connection: connected|disconnected|accessDenied|
  loading|stale|transientFailure|terminalFailure, primary, details[],
  planLabel, footerLines, rateLimited}` — **bağlantı durumu enum'u** UI'a
  dürüst metin verir.
- Claude: `~/.claude/.credentials.json` (`readSecureFile`: symlink reddi,
  mod bitleri `0o077` kontrolü (Windows hariç), 64 KB sınır, `O_NOFOLLOW`,
  aç-öncesi/sonrası stat) → yoksa macOS keychain `/usr/bin/security` (90 sn:
  izin diyaloğu için; hex çıktı çözme; `accessDenied` ayrı durum).
  `rateLimitTier` → plan etiketi. Süresi dolmuşsa **yenilemez**, dosyayı yeniden
  okur; 401'de bir kez yeniden okuyup tekrar dener; 429'da gövdedeki
  `retry_after` (min 60, varsayılan 300 sn). `seven_day_opus/sonnet` alanları +
  `limits[]` `weekly_scoped`. **Primary = haftalık** (5 saatlik değil).
  `sanitizeError` Bearer/sk-ant/ya29/gh*/JWT desenlerini siler, 240 karakter.
  ⚠ `User-Agent: claude-code/2.1.0` **taklit** — etik/ToS gri alan; platformda
  kendi UA'mız olmalı.
- Codex için keychain **kullanılmıyor** (menü çubuğu salt okunur cache'i
  `~/.codex/auth.json`'u yenileyen süreçle çakışırdı).

## Guard (`src/guard/hooks.ts`) — kontrol düzlemi
- Hook protokolü **belgeye karşı doğrulanmış** (2026-07-03) ve yorumda alan
  alan yazılı; **her zaman exit 0**, karar JSON'da → iç hata = "görüşüm yok"
  (**fail-open**).
- PreToolUse: transcript'ten oturum maliyeti (cache'li artımlı) → hard cap
  (varsayılan $15) → `permissionDecision: deny` + gerekçe; soft cap →
  `systemMessage` bir kez; `codeburn guard allow` oturum için kaldırır.
- SessionStart: optimize bulguları olan projeye `additionalContext` "açılış
  notu" (bayrak dosyası, bayatlık sınırı). Stop: checkpoint cap (düzenleme
  görmeden $X harcandıysa dürtme; asla engellemez).
- Kurulum `act` günlüğünden geçer → geri alınabilir.

## Act (`src/act/apply.ts`, `report.ts`) — geri alınabilir müdahale
- Tek mutasyon yolu: kilit → her dosyayı yedekle (yol başına ilk snapshot) →
  **bayat plan koruması** (beklenen hash) → uygula → hash → günlüğe yaz;
  hata olursa ters sırada geri al, hiçbir şey günlüğe girmez.
- `act report`: ≥3 gün sonra **tahmini vs gerçekleşen** tasarruf; güven
  (oturum hızı kayması), "ölçülemez" notları, MCP satırlarıyla çift sayım
  engeli; "işe yaramadı" → `--auto-revert`. **Tahminler gerçekle sınanıyor.**

## Gizlilik ve dışa akış
- Yerel: `session-cache` **`userMessage` saklıyor** (sınıflandırma için;
  `optimize` OPTIMIZE_TEXT_CAP ile kırpıyor) → yerel de olsa **içerik**
  depolanıyor; platformda SENSITIVE sınıfı, varsayılan kapalı.
- `sync` (kurumsal): "consent-once" — **alan anlamları listesi**
  (`CORE_SYNC_FIELD_MEANINGS`: ai.provider… git.sha), kabul parmak izi
  (org, hedef, alanlar, workMatching, kapsam, kadans) değişince yeniden rıza;
  makbuzlar.
- MCP sunucusu: proje adları tuzlu sha256 takma ad (`.mcp-salt` 0600), canlı
  oturumlar çıkarılır.
- Masaüstü telemetri: gün hassasiyetli, beyaz listeli olay adları, yaprak
  sayısı sınırı, yalnız paketli sürüm, opt-in.
- Paylaşım: LAN eşleştirme PIN'i ile cihazlar arası toplam.

## §8 değerlendirme
| | |
|---|---|
| Data acquisition | 46 sağlayıcı; dosya + SQLite + ağ; artımlı cache; `doctor` |
| Analytics | waste/optimize bulguları, A–F sağlık notu, kategori sınıflandırma, model önerisi |
| Control | guard cap'leri, act geri alınabilir uygulama, realized-vs-estimated |
| Privacy | Yerel varsayılan; içerik cache'i (−); dışa akışta rıza tasarımı (+) |
| Accuracy | `costIsEstimated`; Copilot AIU faturalama ham veri |
| Docs | README güçlü; kodda protokol notları |

## Platforma aktarılacaklar
1. Sağlayıcı arayüzü + `SessionSource` (kaynak örneği) + `probeRoots`.
2. Bağlantı durumu enum'u ve `rateLimited`; kimlik dosyası okuma sertleştirmesi.
3. **Guard hook kalıbı** (fail-open, JSON karar, oturum başına kaldırma) —
   Aşama 3 "kontrol" özelliği; hooks resmi belgeye karşı doğrulanmış.
4. **Act günlüğü**: yedek → hash → uygula → geri al; öneri motorunun ("Şu anda
   ne yapmalıyım") uygulama kolu, MP §21'in "geri alınabilir eylem" ilkesi.
5. Realized-vs-estimated raporu = estimator doğruluğunun kendi kendini
   denetlemesi (MP §29–30).
6. Rıza parmak izi + alan anlamları = dışa aktarım (varsa) için standart.
7. Reddedilen: UA taklidi; içerik cache'i; `primary=haftalık` (kullanıcıya
   sorulmalı).
