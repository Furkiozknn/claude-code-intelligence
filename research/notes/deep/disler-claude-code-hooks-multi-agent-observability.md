# Derin analiz · disler/claude-code-hooks-multi-agent-observability

**Okunan:** `apps/server/src/db.ts`, `apps/server/src/types.ts`. **Bilinen:**
`.claude/hooks/*.py` her hook olayını HTTP ile Bun sunucusuna gönderir; Vue
istemci WebSocket'ten canlı akış çizer. Kategori: hook tabanlı çoklu-ajan
gözlemlenebilirlik (en çok yıldızlı hook örneği).

## Veri modeli
```
events(id, source_app, session_id, hook_event_type, payload TEXT(JSON),
       chat TEXT(JSON), summary, timestamp, humanInTheLoop, humanInTheLoopStatus, model_name)
```
- `payload` = hook stdin'inin **tamamı** (tool_input, prompt metni dahil);
  `chat` = **tüm transkript** (Stop hook'unda transcript_path okunup gönderiliyor);
  `summary` = LLM özet. → **İçerik depolama anti-kalıbı doğrulandı**: gizlilik
  sınıflandırması yok, redaksiyon yok, saklama politikası yok.
- Şema göçü: `PRAGMA table_info` ile sütun var mı bak, `ALTER TABLE ADD` —
  sürüm numarası yok.
- WAL + `synchronous=NORMAL` (pratik SQLite ayarı).
- Tema tabloları (`themes`, `theme_shares`, `theme_ratings`, `downloadCount`,
  `rating`) sunucuda — gözlemlenebilirlik sunucusunda tema pazarı: **kapsam
  şişmesi** örneği (MP §36 "overbuild").

## Human-in-the-loop (HITL)
`HumanInTheLoop{question, responseWebSocketUrl, type: question|permission|choice,
choices, timeout, requiresResponse}` + `HumanInTheLoopStatus{pending|responded|
timeout|error}`. Hook, kullanıcının **web panelinden** izin/cevap vermesini
bekleyebiliyor — "Control" boyutunun ilk örneği. Riskler: WebSocket URL'si
olay içinde taşınıyor; kimlik doğrulama yok; zaman aşımı sonrası davranış
istemciye bırakılmış.

## Platforma aktarılacaklar
1. **Hook toplayıcı** için pozitif ders: olay türü + oturum + kaynak uygulama +
   zaman damgası yeter; `payload`'un tamamı **asla** saklanmaz — allow-list
   (cacheeconomics) uygulanır; `tool_name`, `tool_use_id`, süre, başarı,
   hata türü alınır.
2. Çoklu-ajan görünümü (source_app × session_id şeridi) UX olarak iyi;
   platformun oturum haritası yüzeyine ilham.
3. HITL: **Aşama 4 (Ecosystem)**'e "kontrol düzlemi" olarak, loopback +
   yetki + zaman aşımı politikasıyla; çekirdeğe girmez.
4. Şema göçü sürüm numarasıyla yapılmalı (toktrack `CACHE_VERSION` gibi).
