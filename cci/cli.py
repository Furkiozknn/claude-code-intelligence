"""`cci` komut satiri (docs/PRODUCT.md §4). Yuzey hesap yapmaz: boru hatti ve depo uzerinden calisir.

Cikis kodlari: 0 ok · 2 kullanim · 3 koruma yasasi ihlali (--strict) · 4 daemon/veri yok ·
5 kimlik/erisim yok.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from cci import __version__
from cci.adapters.base import ProbeRoot
from cci.adapters.claude_code.adapter import ClaudeCodeAdapter
from cci.adapters.claude_code.paths import credentials_path
from cci.analytics.summaries import ConservationError
from cci.api.http import ApiServer, load_or_create_token
from cci.api.snapshot import build_snapshot, read_snapshot, write_snapshot
from cci.alerts.engine import send_webhook
from cci.collectors.otlp import OtlpReceiver
from cci.collectors.quota import QuotaPoller
from cci.config import load_config
from cci.events.envelope import Envelope, SourceRef
from cci.model.evidence import EvidenceClass
from cci.model.ids import AccountRef
from cci.model.quota import QuotaSnapshot
from cci.pipeline import Pipeline
from cci.pricing.table import PricingTable
from cci.quota.pace import compute_pace
from cci.store.sqlite import EventStore

EXIT_OK, EXIT_USAGE, EXIT_CONSERVATION, EXIT_NO_DATA, EXIT_NO_CREDENTIALS = 0, 2, 3, 4, 5
DEFAULT_OTLP_PORT = 4318
DEFAULT_API_PORT = 4319


def default_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "cci"
    return Path.home() / ".cci"


def local_tz() -> ZoneInfo:
    name = os.environ.get("CCI_TZ") or os.environ.get("TZ")
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    try:
        return ZoneInfo("Europe/Istanbul") if os.environ.get("CCI_DEFAULT_TZ_TR") else ZoneInfo(datetime.now().astimezone().tzname() or "UTC")
    except Exception:
        return ZoneInfo("UTC")


class Context:
    def __init__(self, data_dir: Path, *, as_json: bool, env: dict[str, str] | None = None, home: Path | None = None) -> None:
        self.data_dir = data_dir
        self.as_json = as_json
        self.env = dict(os.environ if env is None else env)
        self.home = home if home is not None else Path.home()
        self.tz = local_tz()
        self.adapter = ClaudeCodeAdapter(env=self.env, home=self.home)
        self.table = PricingTable.load_bundled()
        self.config = load_config(self.data_dir / "config.toml")
        self._store: EventStore | None = None
        self._pipe: Pipeline | None = None

    @property
    def store(self) -> EventStore:
        if self._store is None:
            self._store = EventStore(self.data_dir / "events.db")
        return self._store

    @property
    def pipe(self) -> Pipeline:
        if self._pipe is None:
            self._pipe = Pipeline(self.store, self.table, self.tz, cursors_path=self.data_dir / "cursors.json",
                                  account=self.account())
        return self._pipe

    def account(self) -> AccountRef | None:
        """Hesap kimligi YALNIZ OTel `user.account_uuid`'den (depodaki son olay)."""
        for env in self.store.query(types=["usage.request", "quota.snapshot"]):
            pass
        last = None
        for env in self.store.query(types=["usage.request"]):
            if env.account_key:
                last = env.account_key
        return AccountRef(provider="anthropic", account_key=last) if last else None

    def credentials(self) -> Path | None:
        roots = self.adapter.roots()
        return credentials_path(roots[0]) if roots else None

    def snapshot_path(self) -> Path:
        return self.data_dir / "state" / "latest.json"

    def pipe_backtest(self, kind: str, now: datetime) -> dict:
        from cci.quota.forecast import backtest
        return backtest(self.pipe.quota_history(), kind, now)  # type: ignore[arg-type]

    def close(self) -> None:
        if self._store is not None:
            self._store.close()

    def out(self, data: Any, text: Callable[[], str]) -> None:
        if self.as_json:
            print(json.dumps(data, ensure_ascii=False, indent=1, default=str))
        else:
            print(text())


# ------------------------------------------------------------------ yardimcilar
def _fig(f) -> str:
    return f.render()


def latest_quota(ctx: Context) -> QuotaSnapshot | None:
    last: QuotaSnapshot | None = None
    for env in ctx.store.query(types=["quota.snapshot"]):
        try:
            last = QuotaSnapshot.from_payload(env.payload)
        except Exception:
            continue
    return last


def store_quota(ctx: Context, snap: QuotaSnapshot) -> bool:
    if not snap.storable:
        return False
    env = Envelope(type="quota.snapshot", ts=snap.fetched_at,
                   source=SourceRef(collector="quota", instance_id="usage_api", collector_version=__version__, schema_version=1),
                   provider=snap.provider, account_key=snap.account.account_key if snap.account else None,
                   privacy_class="sensitive", evidence_class=EvidenceClass.OBSERVED, payload=snap.model_dump(mode="json"))
    if not ctx.pipe.gate.check(env).accepted:
        return False
    return ctx.store.append(env)


def quota_lines(snap: QuotaSnapshot | None, now: datetime) -> list[str]:
    if snap is None:
        return ["kota: -- (kayitli snapshot yok; `cci quota --poll` ya da OTLP kurulumu gerekli)"]
    age = int((now - snap.fetched_at).total_seconds())
    lines = [f"kota ({snap.source}, {age} sn once{'' if snap.authoritative else ', authoritative=false!'}):"]
    for w in snap.windows:
        util = "--" if w.utilization is None else f"{w.utilization * 100:5.1f}%●"
        label = w.kind + (f" [{w.scope.model_display}]" if w.scope.model_display else "")
        reset = "" if w.resets_at is None else f" reset {w.resets_at.astimezone(UTC).strftime('%m-%d %H:%M')}Z"
        pace = compute_pace(w, now, allow_post_reset_grace=True)
        ptxt = ""
        if pace is not None:
            arrow = "⇡" if pace.delta_pct > 0 else "⇣"
            ptxt = f"  {arrow}{abs(pace.delta_pct):.0f}%◐ {pace.stage}"
            if pace.eta_s is not None:
                ptxt += f"  ~tukenme {timedelta(seconds=int(pace.eta_s))}"
        lines.append(f"  {label:<24} {util}{reset}{ptxt}")
    return lines


# ------------------------------------------------------------------ komutlar
def cmd_scan(ctx: Context, args: argparse.Namespace) -> int:
    report = ctx.pipe.ingest_transcripts(ctx.adapter)
    data = {"instances": report.instances, "raw_items": report.raw_items, "records": report.records,
            "written": report.written, "duplicates": report.duplicates, "rejected": report.rejected,
            "skipped_lines": report.skipped_lines, "counters": dict(report.counters)}
    ctx.out(data, lambda: f"tarandi: {report.instances} kaynak, {report.raw_items} kayit, {report.written} yeni olay, "
                          f"{report.duplicates} tekrar, {report.rejected} red, {report.skipped_lines} bozuk satir")
    return EXIT_OK


def cmd_daily(ctx: Context, args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    since = now - timedelta(days=args.days) if args.days else None
    try:
        days = ctx.pipe.daily(since=since, strict=args.strict)
    except ConservationError as exc:
        print(f"KORUMA YASASI IHLALI: {exc}", file=sys.stderr)
        return EXIT_CONSERVATION
    if args.today:
        today = datetime.now(ctx.tz).date()
        days = [d for d in days if d.day == today]
    if not days:
        ctx.out({"days": []}, lambda: "veri yok (once `cci scan` ya da OTLP kurulumu)")
        return EXIT_NO_DATA

    def text() -> str:
        lines = []
        for d in days:
            t = d.totals
            flag = "" if d.conservation.ok else "  !koruma"
            lines.append(f"{d.day} [{d.tz}]  istek {t.requests:>5}  token {t.tokens.billable_total:>10,}  "
                         f"maliyet {_fig(t.cost):>10}≈  satici {_fig(t.vendor_cost)}{flag}")
            for m in d.models:
                lines.append(f"    {m.display:<16} istek {m.totals.requests:>4}  token {m.totals.tokens.billable_total:>10,}  {_fig(m.totals.cost)}")
        return "\n".join(lines)

    ctx.out({"days": [d.model_dump(mode="json") for d in days]}, text)
    return EXIT_OK


def cmd_sessions(ctx: Context, args: argparse.Namespace) -> int:
    try:
        sessions = ctx.pipe.sessions(strict=args.strict)
    except ConservationError as exc:
        print(f"KORUMA YASASI IHLALI: {exc}", file=sys.stderr)
        return EXIT_CONSERVATION
    sessions = sorted(sessions, key=lambda s: s.last_at, reverse=True)[: args.limit]
    if not sessions:
        ctx.out({"sessions": []}, lambda: "oturum yok")
        return EXIT_NO_DATA
    diags = {s.session_id: ctx.pipe.diagnose(s.session_id, cost=s.totals.cost) for s in sessions}

    def text() -> str:
        return "\n".join(f"{s.last_at.astimezone(ctx.tz).strftime('%m-%d %H:%M')}  {s.session_id[:8]}…  istek {s.totals.requests:>4}  "
                         f"token {s.totals.tokens.billable_total:>10,}  {_fig(s.totals.cost):>9}  "
                         f"alt-ajan {s.subagent_requests}  saglik {diags[s.session_id].health:>3}  {diags[s.session_id].attention}"
                         f"  {'proje ' + s.project_key[:8] if s.project_key else ''}" for s in sessions)

    ctx.out({"sessions": [{**s.model_dump(mode="json"), "diagnostics": diags[s.session_id].model_dump(mode="json")} for s in sessions]}, text)
    return EXIT_OK


def cmd_session(ctx: Context, args: argparse.Namespace) -> int:
    summaries = ctx.pipe.sessions()
    match = [s for s in summaries if s.session_id == args.session_id or s.session_id.startswith(args.session_id)]
    if len(match) != 1:
        print("oturum bulunamadi ya da belirsiz: " + ", ".join(s.session_id[:8] for s in match) if match else "oturum bulunamadi", file=sys.stderr)
        return EXIT_NO_DATA
    s = match[0]
    d = ctx.pipe.diagnose(s.session_id, cost=s.totals.cost)

    def text() -> str:
        lines = [f"oturum {s.session_id}  {s.started_at.astimezone(ctx.tz).strftime('%m-%d %H:%M')} → {s.last_at.astimezone(ctx.tz).strftime('%H:%M')}",
                 f"saglik {d.health}/100  dikkat: {d.attention}" + (f"  ({'; '.join(d.reasons)})" if d.reasons else ""),
                 f"istek {d.requests}  hata {d.errors} (retry {d.retry_events})  compaction {d.compactions}  "
                 f"token {s.totals.tokens.billable_total:,}  maliyet {_fig(s.totals.cost)}≈  satici {_fig(s.totals.vendor_cost)}"]
        if d.context:
            lines.append(f"context %{d.context.used_pct:.0f} ({d.context.risk})")
        for t in d.tools:
            lines.append(f"  arac {t.tool_name:<16} cagri {t.calls:>4}  hata {t.failures:>3}  timeout {t.timeouts:>2}  "
                         f"p95 {'-' if t.p95_ms is None else f'{t.p95_ms / 1000:.1f}s'}{'  YAVAS' if t.is_slow else ''}")
        for lp in d.loops:
            lines.append(f"  DONGU {lp.tool_name} ×{lp.count} ({lp.severity}) [{lp.first_index}-{lp.last_index}]")
        for m in s.models:
            lines.append(f"  model {m.display:<14} istek {m.totals.requests:>4}  {_fig(m.totals.cost)}")
        return "\n".join(lines)

    ctx.out({"session": s.model_dump(mode="json"), "diagnostics": d.model_dump(mode="json")}, text)
    return EXIT_OK


def cmd_quota(ctx: Context, args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    snap = None
    if args.poll:
        creds = ctx.credentials()
        if creds is None or not creds.exists():
            print("kimlik dosyasi yok: Claude Code ile giris yapilmali (`claude`)", file=sys.stderr)
            return EXIT_NO_CREDENTIALS
        poller = QuotaPoller(creds, account=ctx.account())
        result = poller.poll_once()
        if result.snapshot is None:
            print(f"kota alinamadi: {result.health.error_class} — {result.health.detail}", file=sys.stderr)
            return EXIT_NO_CREDENTIALS if result.health.error_class in ("no_credentials", "expired", "unauthorized", "credentials_unsafe") else EXIT_NO_DATA
        snap = result.snapshot
        stored = store_quota(ctx, snap)
        if not stored and not ctx.as_json:
            print("not: hesap kimligi (OTel user.account_uuid) yok -> snapshot saklanmadi, yalniz canli gosteriliyor")
    else:
        snap = latest_quota(ctx)
    if args.backtest:
        reports = {k: ctx.pipe_backtest(k, now) for k in ("session_5h", "weekly_all")}
        ctx.out({"backtest": reports}, lambda: "\n".join(
            f"{k}: dongu {r['cycles']} degerlendirme {r['evaluations']} en iyi {r['best']} "
            + " ".join(f"{m}={v['mae']}" for m, v in r["methods"].items()) + f" bant-kapsama {r['blend_band_coverage']}"
            for k, r in reports.items()))
        return EXIT_OK
    forecasts = ctx.pipe.forecasts(now) if args.forecast else {}
    ctx.out({"quota": snap.model_dump(mode="json") if snap else None,
             "pace": {w.kind: (compute_pace(w, now, allow_post_reset_grace=True).model_dump(mode="json") if compute_pace(w, now, allow_post_reset_grace=True) else None)
                      for w in (snap.windows if snap else ())},
             "forecast": {k: f.model_dump(mode="json") for k, f in forecasts.items()}},
            lambda: "\n".join(quota_lines(snap, now) + [
                f"  tahmin {k}: {f.verdict} ({f.confidence}, {f.cycles_completed} dongu) "
                + (f"reset'te ~%{float(f.projected_at_reset.median):.0f} [{float(f.projected_at_reset.band.lo):.0f}-{float(f.projected_at_reset.band.hi):.0f}]"
                   if f.projected_at_reset else f.value.render()) for k, f in forecasts.items()]))
    return EXIT_OK if snap is not None else EXIT_NO_DATA


def cmd_alerts(ctx: Context, args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    if args.history:
        rows = [{"ts": e.ts.isoformat(), "type": e.type, **{k: e.payload.get(k) for k in ("rule_id", "severity", "basis", "message", "dedupe_key")}}
                for e in ctx.store.query(types=["alert.raised", "alert.resolved"])]
        ctx.out({"history": rows}, lambda: "\n".join(f"{r['ts'][:19]}  {r['type']:<14} {r.get('severity') or '':<8} {r.get('rule_id') or ''}  {r.get('message') or ''}" for r in rows) or "gecmis yok")
        return EXIT_OK
    raised, engine = ctx.pipe.evaluate_alerts(now, ctx.config.alerts, persist=not args.dry_run, now_local=datetime.now(ctx.tz))
    if raised and ctx.config.alerts.webhook_url and not args.dry_run:
        send_webhook(ctx.config.alerts.webhook_url, raised)
    anomalies, base = ctx.pipe.anomalies(now)
    active = engine.snapshot_alerts()
    data = {"raised_now": [a.model_dump(mode="json") for a in raised], "active": active,
            "suppressed": engine.suppressed, "anomalies": [a.model_dump(mode="json") for a in anomalies], "baseline": base.as_dict()}
    ctx.out(data, lambda: "\n".join(
        [f"yeni: {len(raised)}  aktif: {len(active)}  bastirilan: {len(engine.suppressed)}"] +
        [f"  [{a['severity']}] {a['rule_id']} ({a['basis']}): {a['message']}" for a in active] +
        [f"  anomali [{a.severity}] {a.kind}: {a.message}" for a in anomalies] +
        [f"  taban: {n}" for n in base.notes]))
    return EXIT_OK


def cmd_doctor(ctx: Context, args: argparse.Namespace) -> int:
    health = ctx.adapter.health()
    probes: list[ProbeRoot] = list(ctx.adapter.probe_roots())
    stats = ctx.store.stats()
    quota = latest_quota(ctx)
    telemetry_env = {k: ctx.env.get(k) for k in ("CLAUDE_CODE_ENABLE_TELEMETRY", "OTEL_METRICS_EXPORTER", "OTEL_LOGS_EXPORTER",
                                                  "OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_ENDPOINT")}
    data = {
        "version": __version__, "data_dir": str(ctx.data_dir),
        "adapter": {"name": ctx.adapter.name, "health": health.model_dump(mode="json"),
                    "capabilities": ctx.adapter.capabilities().model_dump(mode="json"),
                    "instances": [i.model_dump(mode="json") for i in ctx.adapter.discover()],
                    "probe_roots": [p.model_dump(mode="json") for p in probes]},
        "store": stats, "dedup_counters": dict(ctx.pipe.dedup_counters),
        "pricing": {"version": ctx.table.version, "fetched_at": ctx.table.fetched_at.isoformat(), "models": len(ctx.table)},
        "quota": None if quota is None else {"fetched_at": quota.fetched_at.isoformat(), "authoritative": quota.authoritative,
                                             "source": quota.source, "windows": len(quota.windows)},
        "account_key_known": ctx.account() is not None,
        "telemetry_env": telemetry_env, "snapshot_file": str(ctx.snapshot_path()),
        "snapshot_exists": ctx.snapshot_path().exists(),
    }

    def text() -> str:
        lines = [f"cci {__version__}  veri: {ctx.data_dir}",
                 f"adaptor {ctx.adapter.name}: {health.status} ({health.error_class or health.detail})"]
        for p in probes:
            lines.append(f"  {'✓' if p.exists else '✗'} {p.label:<28} {p.path}")
        lines.append(f"depo: {stats['events']} olay, {stats['db_bytes']:,} bayt, sema v{stats['schema_version']}")
        for k, v in sorted(stats["by_type"].items()):
            lines.append(f"  {k:<26} {v}")
        lines.append(f"fiyat tablosu: {ctx.table.version} ({len(ctx.table)} model)")
        lines.append(f"hesap kimligi (OTel): {'var' if data['account_key_known'] else 'YOK -> kota snapshot saklanmaz'}")
        lines.append("kota: " + ("yok" if quota is None else f"{quota.source} {quota.fetched_at.isoformat()} authoritative={quota.authoritative}"))
        lines.append("telemetri env: " + ", ".join(f"{k}={v or '-'}" for k, v in telemetry_env.items()))
        lines.append(f"snapshot: {ctx.snapshot_path()} ({'var' if data['snapshot_exists'] else 'yok'})")
        return "\n".join(lines)

    ctx.out(data, text)
    return EXIT_OK


def cmd_snapshot(ctx: Context, args: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    days = ctx.pipe.daily()
    today_local = datetime.now(ctx.tz).date()
    today = next((d for d in days if d.day == today_local), None)
    health = {"adapter": ctx.adapter.health().model_dump(mode="json"), "store_events": ctx.store.count()}
    attention, _ = ctx.pipe.attention(now)
    engine = ctx.pipe.alert_engine(ctx.config.alerts)
    snap = build_snapshot(now=now, quota=latest_quota(ctx), today=today, health=health, attention=attention,
                          forecasts=ctx.pipe.forecasts(now), alerts=engine.snapshot_alerts())
    path = Path(args.out) if args.out else ctx.snapshot_path()
    write_snapshot(path, snap)
    ctx.out({"written": str(path), "generated_at": snap["generated_at"]}, lambda: f"snapshot yazildi: {path}")
    return EXIT_OK


def statusline_text(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "cci --"
    parts: list[str] = []
    windows = {w["kind"]: w for w in snapshot.get("quota", {}).get("windows", [])}
    for kind, short in (("session_5h", "5h"), ("weekly_all", "7d")):
        w = windows.get(kind)
        if w is None or w.get("utilization_pct") is None:
            parts.append(f"{short} --")
            continue
        s = f"{short} {w['utilization_pct']:.0f}%{w.get('badge', '')}"
        pace = w.get("pace")
        if pace:
            s += f" {'⇡' if pace['delta_pct'] > 0 else '⇣'}{abs(pace['delta_pct']):.0f}%"
        if w.get("stale"):
            s += "(eski)"
        parts.append(s)
    today = snapshot.get("today")
    if today:
        cost = today["cost"]
        parts.append(cost["text"] + ("≈" if cost["released"] else ""))
    parts.append(snapshot.get("attention", "ok"))
    return " · ".join(parts)


def cmd_statusline(ctx: Context, args: argparse.Namespace) -> int:
    print(statusline_text(read_snapshot(ctx.snapshot_path())))
    return EXIT_OK


OTLP_ENV = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1", "OTEL_METRICS_EXPORTER": "otlp", "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:{port}",
    "OTEL_METRIC_EXPORT_INTERVAL": "60000", "OTEL_LOGS_EXPORT_INTERVAL": "5000",
}


def otlp_env_block(port: int) -> dict[str, str]:
    return {k: v.format(port=port) for k, v in OTLP_ENV.items()}


def _write_settings(settings: Path, mutate: Callable[[dict[str, Any]], None]) -> tuple[Path | None, dict[str, Any]] | None:
    """settings.json'i yedekle, `mutate` uygula, atomik yaz. Gecersiz JSON -> None (dokunma)."""
    doc: dict[str, Any] = {}
    backup: Path | None = None
    if settings.exists():
        try:
            doc = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            return None
        backup = settings.with_name(f"{settings.name}.bak-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(settings, backup)
    else:
        settings.parent.mkdir(parents=True, exist_ok=True)
    mutate(doc)
    tmp = settings.with_name(settings.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, settings)
    return backup, doc


def cmd_setup(ctx: Context, args: argparse.Namespace) -> int:
    settings = Path(args.settings) if args.settings else (ctx.home / ".claude" / "settings.json")
    if args.what == "statusline":
        cmd = statusline_command()
        if not args.write:
            ctx.out({"settings": str(settings), "statusLine": {"type": "command", "command": cmd}, "written": False},
                    lambda: f"{settings} icine yazilacak (uygulamak icin --write):\n  statusLine: {cmd}")
            return EXIT_OK
        res = _write_settings(settings, lambda doc: doc.__setitem__("statusLine", {"type": "command", "command": cmd}))
        if res is None:
            print(f"{settings} gecerli JSON degil; dokunulmadi", file=sys.stderr)
            return EXIT_USAGE
        backup, _ = res
        ctx.out({"settings": str(settings), "backup": str(backup) if backup else None, "written": True},
                lambda: f"yazildi: {settings}" + (f" (yedek: {backup})" if backup else ""))
        return EXIT_OK
    if args.what != "otlp":
        print("desteklenen: setup otlp | setup statusline", file=sys.stderr)
        return EXIT_USAGE
    block = otlp_env_block(args.port)
    if not args.write:
        ctx.out({"settings": str(settings), "env": block, "written": False},
                lambda: f"{settings} icine yazilacak env blogu (uygulamak icin --write):\n" +
                        "\n".join(f"  {k}={v}" for k, v in block.items()))
        return EXIT_OK
    doc: dict[str, Any] = {}
    if settings.exists():
        try:
            doc = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            print(f"{settings} gecerli JSON degil; dokunulmadi", file=sys.stderr)
            return EXIT_USAGE
        backup = settings.with_name(f"{settings.name}.bak-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(settings, backup)
    else:
        settings.parent.mkdir(parents=True, exist_ok=True)
        backup = None
    env = dict(doc.get("env") or {})
    env.update(block)
    doc["env"] = env
    tmp = settings.with_name(settings.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, settings)
    ctx.out({"settings": str(settings), "backup": str(backup) if backup else None, "env": block, "written": True},
            lambda: f"yazildi: {settings}" + (f" (yedek: {backup})" if backup else "") + "\nClaude Code'u yeniden baslat.")
    return EXIT_OK


def api_data_provider(ctx: Context) -> Callable[[str, str | None], Any]:
    """API icin istek basina salt okunur depo: daemon'un yazar baglantisiyla thread paylasmaz."""
    from cci.pipeline import Pipeline as _P

    def provider(name: str, ident: str | None) -> Any:
        if not (ctx.data_dir / "events.db").exists():
            return None
        with EventStore(ctx.data_dir / "events.db", read_only=True) as store:
            pipe = _P(store, ctx.table, ctx.tz, account=None)
            now = datetime.now(UTC)
            if name == "today":
                today_local = datetime.now(ctx.tz).date()
                return [d.model_dump(mode="json") for d in pipe.daily() if d.day == today_local]
            if name == "sessions":
                sessions = sorted(pipe.sessions(), key=lambda s: s.last_at, reverse=True)[:50]
                return [{**s.model_dump(mode="json"), "attention": pipe.diagnose(s.session_id, cost=s.totals.cost).attention} for s in sessions]
            if name == "session" and ident:
                for s in pipe.sessions():
                    if s.session_id == ident or s.session_id.startswith(ident):
                        return {"session": s.model_dump(mode="json"), "diagnostics": pipe.diagnose(s.session_id, cost=s.totals.cost).model_dump(mode="json")}
                return None
            if name == "quota":
                last = None
                for env in store.query(types=["quota.snapshot"]):
                    last = env.payload
                return {"quota": last, "now": now.isoformat()}
            if name == "doctor":
                return {"store": store.stats(), "pricing": ctx.table.version, "adapter": ctx.adapter.health().model_dump(mode="json")}
        return None

    return provider


def start_api(ctx: Context, port: int) -> ApiServer:
    token = load_or_create_token(ctx.data_dir / "api_token")
    return ApiServer(snapshot_path=ctx.snapshot_path(), token=token, data=api_data_provider(ctx), port=port).start()


def cmd_serve(ctx: Context, args: argparse.Namespace) -> int:
    api = start_api(ctx, args.port)
    print(f"cci pano: {api.url}", file=sys.stderr)
    if args.once:
        api.stop()
        return EXIT_OK
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        api.stop()
    return EXIT_OK


def cmd_widget(ctx: Context, args: argparse.Namespace) -> int:
    from cci.surfaces.widget import run_widget, widget_lines
    if args.print:
        print("\n".join(widget_lines(read_snapshot(ctx.snapshot_path()), detailed=args.detailed)))
        return EXIT_OK
    run_widget(ctx.snapshot_path(), always_on_top=not args.no_top)  # pragma: no cover - GUI
    return EXIT_OK


def cmd_run(ctx: Context, args: argparse.Namespace) -> int:
    """Daemon dongusu: OTLP alici + API + periyodik transcript taramasi + (opsiyonel) kota + snapshot."""
    receiver = OtlpReceiver(lambda env: ctx.store.append(env), port=args.otlp_port, gate=ctx.pipe.gate).start()
    api = start_api(ctx, args.api_port) if not args.no_api else None
    if api is not None:
        print(f"cci pano: {api.url}", file=sys.stderr)
    poller = None
    creds = ctx.credentials()
    if not args.no_quota and creds is not None and creds.exists():
        poller = QuotaPoller(creds, account=ctx.account())
    next_quota = 0.0
    engine = ctx.pipe.alert_engine(ctx.config.alerts)
    down_since: dict[str, float] = {}
    print(f"ccid: OTLP {receiver.endpoint}  veri {ctx.data_dir}  aralik {args.interval}s  kota {'acik' if poller else 'kapali'}", file=sys.stderr)
    try:
        while True:
            report = ctx.pipe.ingest_transcripts(ctx.adapter)
            if poller is not None and time.monotonic() >= next_quota:
                result = poller.poll_once()
                if result.snapshot is not None:
                    store_quota(ctx, result.snapshot)
                next_quota = time.monotonic() + result.next_in_s
            days = ctx.pipe.daily()
            today_local = datetime.now(ctx.tz).date()
            today = next((d for d in days if d.day == today_local), None)
            health = {"adapter": ctx.adapter.health().model_dump(mode="json"), "otlp": dict(receiver.counters),
                      "quota": poller.last_health.model_dump(mode="json") if poller else None,
                      "scan": {"written": report.written, "rejected": report.rejected}}
            now = datetime.now(UTC)
            attention, _ = ctx.pipe.attention(now)
            # toplayici sagligi -> collector.down kurali icin sure takibi
            adapter_health = ctx.adapter.health()
            mono = time.monotonic()
            if adapter_health.status == "down":
                down_since.setdefault("transcript", mono)
            else:
                down_since.pop("transcript", None)
            coll = {name: {"status": "down", "down_since_s": mono - since, "error_class": adapter_health.error_class}
                    for name, since in down_since.items()}
            raised, engine = ctx.pipe.evaluate_alerts(now, ctx.config.alerts, engine=engine, collector_health=coll,
                                                      now_local=datetime.now(ctx.tz))
            if raised and ctx.config.alerts.webhook_url:
                send_webhook(ctx.config.alerts.webhook_url, raised)
            write_snapshot(ctx.snapshot_path(), build_snapshot(now=now, quota=latest_quota(ctx), today=today, health=health,
                                                               attention=attention, forecasts=ctx.pipe.forecasts(now),
                                                               alerts=engine.snapshot_alerts()))
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        receiver.stop()
        if api is not None:
            api.stop()
    return EXIT_OK


def cmd_research(ctx: Context, args: argparse.Namespace) -> int:
    """Research Mode (docs/RESEARCH_MODE.md): ayri dizin; cekirdege yalniz gozlem (kota basliklari) ve ozet parametre gecer."""
    from cci.research import ResearchProxy, estimate_unit
    rdir = ctx.data_dir / "research"
    if args.what == "proxy":
        def sink(snap):
            store_quota(ctx, snap)
        proxy = ResearchProxy(research_dir=rdir, upstream=args.upstream, port=args.port, capture_bodies=args.capture_bodies,
                              quota_sink=sink, account=ctx.account()).start()
        print(f"research proxy: {proxy.base_url}  ->  {args.upstream}\n"
              f"Claude Code icin: ANTHROPIC_BASE_URL={proxy.base_url}  (govde yakalama: {'ACIK' if args.capture_bodies else 'kapali'})\n"
              f"meta: {rdir / 'requests.jsonl'}", file=sys.stderr)
        if args.once:
            proxy.stop()
            return EXIT_OK
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            proxy.stop()
        return EXIT_OK
    if args.what == "unit-estimator":
        res = estimate_unit(ctx.pipe.quota_history(), ctx.pipe.records(), args.kind, table=ctx.table)
        ctx.out(res, lambda: "\n".join(
            [f"kota birimi estimator {res['version']} ({res['kind']}): {res['n_intervals']} aralik"
             + ("  [ogreniyor: <3 aralik]" if res["learning"] else f"  en tutarli: {res['most_consistent']}")] +
            [f"  {name:<17} n={c['n']:<3} cv={c['cv']}  cap p50={c['implied_cap']['p50']} [{c['implied_cap']['p10']}–{c['implied_cap']['p90']}]"
             + (f"  min/med/max={c['implied_cap']['min']}/{c['implied_cap']['median']}/{c['implied_cap']['max']}" if res["learning"] else "")
             for name, c in res["candidates"].items()]))
        return EXIT_OK
    if args.what == "purge":
        if not args.yes:
            print(f"silinecek: {rdir} (onay icin --yes)", file=sys.stderr)
            return EXIT_USAGE
        if rdir.exists():
            shutil.rmtree(rdir)
        ctx.out({"purged": str(rdir)}, lambda: f"silindi: {rdir}")
        return EXIT_OK
    print("desteklenen: research proxy | unit-estimator | purge", file=sys.stderr)
    return EXIT_USAGE


def statusline_command() -> str:
    """Claude Code'un calistiracagi komut: bu yorumlayici ile `cci statusline` (PATH bagimsiz)."""
    return f'"{sys.executable}" -m cci.cli statusline'


# ------------------------------------------------------------------ giris
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cci", description="Claude Code Intelligence Platform")
    p.add_argument("--data-dir", default=None, help="veri dizini (varsayilan: %LOCALAPPDATA%/cci ya da ~/.cci)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", action="version", version=f"cci {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="transcript'leri artimli tara").set_defaults(fn=cmd_scan)
    for name, today in (("today", True), ("daily", False)):
        s = sub.add_parser(name, help="gunluk ozet")
        s.add_argument("--days", type=int, default=0)
        s.add_argument("--strict", action="store_true")
        s.set_defaults(fn=cmd_daily, today=today)
    s = sub.add_parser("sessions"); s.add_argument("--limit", type=int, default=20); s.add_argument("--strict", action="store_true"); s.set_defaults(fn=cmd_sessions)
    s = sub.add_parser("session", help="oturum teshisi"); s.add_argument("session_id"); s.set_defaults(fn=cmd_session)
    s = sub.add_parser("quota"); s.add_argument("--poll", action="store_true", help="canli sorgu (kimlik dosyasi gerekir)")
    s.add_argument("--forecast", action="store_true", help="harman tahmin v2 (>=5 dongu)")
    s.add_argument("--backtest", action="store_true", help="yontem karsilastirma (MAE, bant kapsama)"); s.set_defaults(fn=cmd_quota)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("alerts", help="uyarilari degerlendir/goster"); s.add_argument("--history", action="store_true")
    s.add_argument("--dry-run", action="store_true", help="olay yazma, sadece goster"); s.set_defaults(fn=cmd_alerts)
    s = sub.add_parser("snapshot"); s.add_argument("--out", default=None); s.set_defaults(fn=cmd_snapshot)
    sub.add_parser("statusline").set_defaults(fn=cmd_statusline)
    s = sub.add_parser("setup"); s.add_argument("what"); s.add_argument("--write", action="store_true")
    s.add_argument("--settings", default=None); s.add_argument("--port", type=int, default=DEFAULT_OTLP_PORT); s.set_defaults(fn=cmd_setup)
    s = sub.add_parser("run", help="daemon dongusu"); s.add_argument("--once", action="store_true")
    s.add_argument("--interval", type=float, default=60.0); s.add_argument("--otlp-port", type=int, default=DEFAULT_OTLP_PORT)
    s.add_argument("--api-port", type=int, default=DEFAULT_API_PORT); s.add_argument("--no-api", action="store_true")
    s.add_argument("--no-quota", action="store_true"); s.set_defaults(fn=cmd_run)
    s = sub.add_parser("serve", help="yalniz API + pano"); s.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    s.add_argument("--once", action="store_true"); s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("research", help="arastirma modu (ayri dizin)"); s.add_argument("what")
    s.add_argument("--port", type=int, default=4320); s.add_argument("--upstream", default="https://api.anthropic.com")
    s.add_argument("--capture-bodies", action="store_true"); s.add_argument("--once", action="store_true")
    s.add_argument("--kind", default="session_5h"); s.add_argument("--yes", action="store_true"); s.set_defaults(fn=cmd_research)
    s = sub.add_parser("widget", help="masaustu widget (tkinter)"); s.add_argument("--print", action="store_true")
    s.add_argument("--detailed", action="store_true"); s.add_argument("--no-top", action="store_true"); s.set_defaults(fn=cmd_widget)
    return p


def main(argv: list[str] | None = None, *, env: dict[str, str] | None = None, home: Path | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    ctx = Context(Path(args.data_dir) if args.data_dir else default_data_dir(), as_json=args.json, env=env, home=home)
    try:
        return int(args.fn(ctx, args))
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
