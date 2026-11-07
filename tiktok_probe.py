#!/usr/bin/env python3
"""SOUZA LIVE - Spike de conexão TikTok LIVE (descartável, somente leitura).

Conecta a uma live pelo @usuário, registra eventos em JSONL e gera um relatório.
NÃO envia mensagens, NÃO usa session ID, NÃO guarda credenciais.

Exemplos:
  python tiktok_probe.py nome_do_usuario --duration 300 --label T1
  python tiktok_probe.py nome_do_usuario --sign-url http://127.0.0.1:8080 --label T2

AVISO: escrito sem acesso à internet nem à biblioteca instalada. Nomes de campos
da biblioteca são lidos de forma defensiva e o esquema real é registrado no log
("schema"). Se algo falhar, envie o erro: isso é informação útil do teste.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from streak_analyzer import FinalizedGift, GiftObservation, StreakAnalyzer


# ----------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def first_attr(obj: Any, *names: str, default: Any = None) -> Any:
    """Primeiro atributo existente e não vazio (leitura defensiva)."""
    if obj is None:
        return default
    for n in names:
        try:
            v = getattr(obj, n)
        except Exception:
            continue
        if v not in (None, ""):
            return v
    return default


def describe(obj: Any) -> Optional[Dict[str, str]]:
    """Lista campos públicos não-callable e seus tipos (descoberta de esquema)."""
    if obj is None:
        return None
    out: Dict[str, str] = {}
    for n in dir(obj):
        if n.startswith("_"):
            continue
        try:
            v = getattr(obj, n)
        except Exception:
            out[n] = "<erro ao ler>"
            continue
        if callable(v):
            continue
        out[n] = type(v).__name__
    return out


class Masker:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.salt = os.urandom(8).hex()

    def __call__(self, v: Any) -> Any:
        if not self.enabled or v in (None, ""):
            return v
        return "u_" + hashlib.sha256((self.salt + str(v)).encode()).hexdigest()[:8]


def _scrub_any(v: Any, fn: Callable[[str], str]) -> Any:
    if isinstance(v, str):
        return fn(v)
    if isinstance(v, dict):
        return {k: _scrub_any(x, fn) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scrub_any(x, fn) for x in v]
    return v


class JsonlLog:
    def __init__(self, path: Path, scrub: Callable[[str], str] = lambda x: x) -> None:
        self.path = path
        self._scrub = scrub
        self._fh = open(path, "a", encoding="utf-8")

    def write(self, kind: str, **data: Any) -> None:
        rec = {"ts": now_iso(), "kind": kind, **_scrub_any(data, self._scrub)}
        self._fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


def explain_error(exc: BaseException) -> str:
    name = type(exc).__name__
    text = f"{name}: {exc}"
    low = text.lower()
    if "offline" in low or "not live" in low or "not currently live" in low:
        return text + "  -> Dica: o usuário provavelmente NÃO está em live agora."
    if "notfound" in low.replace(" ", "") or "not found" in low:
        return text + "  -> Dica: confira o @usuário (sem espaços, sem a URL)."
    if "sign" in low or "429" in low or "rate" in low or "too many" in low:
        return text + "  -> Dica: problema no servidor de assinatura (limite, indisponível ou URL errada)."
    return text


def configure_sign(sign_url: Optional[str], sign_api_key: Optional[str]) -> Dict[str, Any]:
    """Ajusta o servidor de assinatura via WebDefaults (nome dos campos conforme a documentação da lib)."""
    info: Dict[str, Any] = {"sign_url": sign_url or "(padrão da biblioteca)", "api_key": bool(sign_api_key)}
    if not sign_url and not sign_api_key:
        return info
    WebDefaults = None
    for mod in (
        "TikTokLive.client.web.web_settings",
        "TikTokLive.client.web.web_base",
        "TikTokLive.client.web",
    ):
        try:
            m = __import__(mod, fromlist=["WebDefaults"])
            WebDefaults = getattr(m, "WebDefaults", None)
            if WebDefaults is not None:
                break
        except Exception:
            continue
    if WebDefaults is None:
        raise RuntimeError(
            "Não encontrei WebDefaults nesta versão da biblioteca. "
            "Envie a saída de: pip show TikTokLive  (a configuração do servidor de assinatura "
            "precisará ser ajustada)."
        )
    if sign_url:
        WebDefaults.tiktok_sign_url = sign_url
    if sign_api_key:
        WebDefaults.tiktok_sign_api_key = sign_api_key
    return info


# ----------------------------------------------------------------------
# sessão de teste
# ----------------------------------------------------------------------
class Session:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        if args.anonymize and args.save_comments:
            print("[AVISO] --anonymize desativa --save-comments (comentários podem conter dados pessoais).")
            args.save_comments = False
        self.mask = Masker(args.anonymize)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_dir = Path(args.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        base = f"{args.label}_{stamp}"
        self.jsonl_path = self.out_dir / f"{base}.jsonl"
        self.report_path = self.out_dir / f"{base}_relatorio.md"
        self.log = JsonlLog(self.jsonl_path, self.scrub)
        self.analyzer = StreakAnalyzer(stale_timeout_s=args.stale_timeout)
        self.counters: Counter = Counter()
        self.finals: List[FinalizedGift] = []
        self.gift_events_total = 0
        self.gift_events_with_id = 0
        self.gift_events_with_handle = 0
        self.errors: List[str] = []
        self.connected_at: Optional[float] = None
        self.started_at = time.time()
        self.ended_at: Optional[float] = None
        self.schema_logged: set = set()
        self.lib_version = "desconhecida"
        self.sign_info: Dict[str, Any] = {}
        self.room_id: Any = None
        self._finished = False

    # ---------------- registro ----------------
    def scrub(self, text: str) -> str:
        """Com --anonymize, remove o @ do streamer de qualquer texto (erros, mensagens)."""
        if not self.args.anonymize:
            return text
        name = self.args.username.lstrip("@")
        if not name:
            return text
        import re
        return re.sub(re.escape(name), "u_streamer", text, flags=re.IGNORECASE)

    def add_error(self, msg: str) -> None:
        self.errors.append(self.scrub(msg))

    def schema_once(self, name: str, obj: Any) -> None:
        if name in self.schema_logged:
            return
        self.schema_logged.add(name)
        self.log.write("schema", name=name, fields=describe(obj))

    def user_fields(self, user: Any) -> Dict[str, Any]:
        uid = first_attr(user, "id", "user_id")
        handle = first_attr(user, "unique_id", "display_id")
        nick = first_attr(user, "nickname", "nick_name")
        return {
            "user_id": self.mask(str(uid)) if uid is not None else "",
            "handle": self.mask(handle) if handle else "",
            "nickname": self.mask(nick) if nick else "",
        }

    def emit_final(self, f: FinalizedGift) -> None:
        self.finals.append(f)
        self.log.write(
            "gift_final",
            user=f.user_key, gift_id=f.gift_id, gift_name=f.gift_name, diamonds=f.diamonds,
            count=f.count, total_diamonds=f.total_diamonds, events_seen=f.events_seen,
            naive_sum=f.naive_sum, ended_by=f.ended_by, duration_s=f.duration_s,
            anomalies=f.anomalies,
        )
        flag = f"  [anomalias: {', '.join(f.anomalies)}]" if f.anomalies else ""
        print(
            f"[PRESENTE FINAL] {f.user_key} -> {f.gift_name} x{f.count} "
            f"({f.total_diamonds} diamantes) fim={f.ended_by} eventos={f.events_seen}{flag}"
        )

    # ---------------- handlers ----------------
    def register(self, client: Any, events: Dict[str, Any]) -> None:
        def guard(fn: Callable[..., Any]) -> Callable[..., Any]:
            async def wrapper(event: Any) -> None:
                try:
                    await fn(event)
                except Exception as exc:  # um campo inesperado não pode derrubar a conexão
                    msg = f"erro no handler {fn.__name__}: {type(exc).__name__}: {exc}"
                    self.add_error(msg)
                    self.log.write("handler_error", handler=fn.__name__, error=msg)
                    print("[ERRO HANDLER]", self.scrub(msg))
            return wrapper

        if events.get("ConnectEvent"):
            @client.on(events["ConnectEvent"])
            @guard
            async def on_connect(event: Any) -> None:
                self.connected_at = time.time()
                rid = getattr(client, "room_id", None)
                self.room_id = self.mask(rid) if rid is not None else None
                self.counters["connect"] += 1
                self.log.write("connect", room_id=self.room_id)
                print(f"[CONECTADO] room_id={self.room_id}")

        if events.get("DisconnectEvent"):
            @client.on(events["DisconnectEvent"])
            @guard
            async def on_disconnect(event: Any) -> None:
                self.counters["disconnect"] += 1
                self.log.write("disconnect")
                print("[DESCONECTADO]")

        if events.get("LiveEndEvent"):
            @client.on(events["LiveEndEvent"])
            @guard
            async def on_end(event: Any) -> None:
                self.counters["live_end"] += 1
                self.log.write("live_end")
                print("[LIVE ENCERRADA]")

        if events.get("CommentEvent"):
            @client.on(events["CommentEvent"])
            @guard
            async def on_comment(event: Any) -> None:
                self.counters["comment"] += 1
                self.schema_once("CommentEvent", event)
                self.schema_once("CommentEvent.user", getattr(event, "user", None))
                text = first_attr(event, "comment", "content", default="")
                rec = self.user_fields(getattr(event, "user", None))
                if self.args.save_comments:
                    rec["text"] = text
                else:
                    rec["text_len"] = len(str(text))
                self.log.write("comment", **rec)
                if self.counters["comment"] <= 5:
                    print(f"[COMENTARIO #{self.counters['comment']}] recebido (len={len(str(text))})")

        if events.get("LikeEvent"):
            @client.on(events["LikeEvent"])
            @guard
            async def on_like(event: Any) -> None:
                self.counters["like"] += 1
                self.schema_once("LikeEvent", event)
                rec = self.user_fields(getattr(event, "user", None))
                rec["count"] = first_attr(event, "count", "like_count")
                rec["total"] = first_attr(event, "total", "total_likes")
                self.log.write("like", **rec)

        if events.get("GiftEvent"):
            @client.on(events["GiftEvent"])
            @guard
            async def on_gift(event: Any) -> None:
                self.counters["gift_event"] += 1
                self.gift_events_total += 1
                gift = getattr(event, "gift", None)
                user = getattr(event, "user", None)
                self.schema_once("GiftEvent", event)
                self.schema_once("GiftEvent.gift", gift)
                self.schema_once("GiftEvent.user", user)

                uf = self.user_fields(user)
                if uf["user_id"]:
                    self.gift_events_with_id += 1
                if uf["handle"]:
                    self.gift_events_with_handle += 1
                user_key = uf["user_id"] or uf["handle"] or ""

                gift_id = str(first_attr(gift, "id", default=""))
                gift_name = str(first_attr(gift, "name", default="(sem nome)"))
                diamonds = int(first_attr(gift, "diamond_count", "diamonds", default=0) or 0)
                streakable = bool(first_attr(gift, "streakable", default=False))
                repeat_count = int(first_attr(event, "repeat_count", default=1) or 1)
                repeat_end = bool(first_attr(event, "repeat_end", default=False))
                lib_streaking = getattr(event, "streaking", None)

                self.log.write(
                    "gift_event", **uf, gift_id=gift_id, gift_name=gift_name, diamonds=diamonds,
                    streakable=streakable, repeat_count=repeat_count, repeat_end=repeat_end,
                    lib_streaking=lib_streaking,
                )
                print(
                    f"[GIFT] {user_key or '(usuario?)'} {gift_name} repeat={repeat_count} "
                    f"end={repeat_end} streakavel={streakable}"
                )
                fin = self.analyzer.feed(
                    GiftObservation(
                        ts=time.time(), user_key=user_key, gift_id=gift_id, gift_name=gift_name,
                        diamonds=diamonds, streakable=streakable,
                        repeat_count=repeat_count, repeat_end=repeat_end,
                    )
                )
                if fin:
                    self.emit_final(fin)

    # ---------------- execução ----------------
    async def run(self) -> int:
        args = self.args
        try:
            import importlib.metadata as md
            self.lib_version = md.version("TikTokLive")
        except Exception:
            pass

        try:
            from TikTokLive import TikTokLiveClient
        except Exception as exc:
            msg = f"Não foi possível importar TikTokLive ({type(exc).__name__}: {exc}). Rode: pip install -r requirements.txt"
            self.add_error(msg)
            self.log.write("fatal", error=msg)
            print("[FATAL]", self.scrub(msg))
            return 3

        events: Dict[str, Any] = {}
        try:
            import TikTokLive.events as ev
            for name in ("ConnectEvent", "DisconnectEvent", "LiveEndEvent", "CommentEvent", "LikeEvent", "GiftEvent"):
                events[name] = getattr(ev, name, None)
        except Exception as exc:
            msg = f"Falha ao importar TikTokLive.events: {exc}"
            self.add_error(msg)
            print("[FATAL]", self.scrub(msg))
            return 3

        try:
            self.sign_info = configure_sign(args.sign_url or os.environ.get("TIKTOK_SIGN_URL"),
                                            args.sign_api_key or os.environ.get("TIKTOK_SIGN_API_KEY"))
        except Exception as exc:
            msg = f"Falha ao configurar servidor de assinatura: {exc}"
            self.add_error(msg)
            self.log.write("fatal", error=msg)
            print("[FATAL]", self.scrub(msg))
            return 3

        self.log.write(
            "start", username=self.mask(args.username), label=args.label,
            lib_version=self.lib_version, python=sys.version.split()[0],
            platform=platform.platform(), sign=self.sign_info, duration=args.duration,
        )
        print(f"Biblioteca TikTokLive {self.lib_version} | sign: {self.sign_info['sign_url']}")
        print(f"Conectando a @{args.username} ... (Ctrl+C para encerrar e gerar o relatório)")

        client = TikTokLiveClient(unique_id="@" + args.username.lstrip("@"))
        self.register(client, events)

        task = None
        try:
            task = await client.start()
            while not task.done():
                await asyncio.sleep(1)
                for f in self.analyzer.flush_stale(time.time()):
                    self.emit_final(f)
                if args.duration and (time.time() - self.started_at) >= args.duration:
                    print("Duração configurada atingida; encerrando.")
                    break
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("Encerrando por solicitação do usuário...")
        except Exception as exc:
            msg = explain_error(exc)
            self.add_error(msg)
            self.log.write("connect_error", error=msg, exc_type=type(exc).__name__)
            print("[ERRO]", self.scrub(msg))
        finally:
            if task is not None and task.done() and not task.cancelled():
                try:
                    exc = task.exception()
                    if exc is not None:
                        msg = explain_error(exc)
                        self.add_error(msg)
                        self.log.write("connection_task_error", error=msg, exc_type=type(exc).__name__)
                        print("[ERRO]", self.scrub(msg))
                except Exception:
                    pass
            try:
                await client.disconnect()
            except BaseException:
                pass
        return 0 if self.connected_at else 1

    # ---------------- relatório ----------------
    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.ended_at = time.time()
        for f in self.analyzer.flush_all():
            self.emit_final(f)
        self.log.write("end", counters=dict(self.counters), errors=self.errors)
        self.log.close()
        self.report_path.write_text(self._report(), encoding="utf-8")
        print(f"\nLog:       {self.jsonl_path}")
        print(f"Relatório: {self.report_path}")

    def _report(self) -> str:
        a = self.args
        dur = (self.ended_at or time.time()) - self.started_at
        connected = "SIM" if self.connected_at else "NÃO"
        lines: List[str] = []
        w = lines.append
        w(f"# Relatório do teste {a.label}")
        w("")
        w(f"- Data/hora de início: {datetime.fromtimestamp(self.started_at).isoformat(timespec='seconds')}")
        w(f"- Duração da sessão: {dur:.0f} s")
        w(f"- Python: {sys.version.split()[0]} | SO: {platform.platform()}")
        w(f"- TikTokLive: {self.lib_version}")
        w(f"- Servidor de assinatura: {self.sign_info.get('sign_url')} | chave de API usada: {self.sign_info.get('api_key')}")
        w(f"- Conectou à live: **{connected}** (room_id={self.room_id})")
        w(f"- Anonimizado: {a.anonymize} | comentários salvos: {a.save_comments}")
        w("")
        w("## Eventos recebidos")
        if self.counters:
            for k, v in sorted(self.counters.items()):
                w(f"- {k}: {v}")
        else:
            w("- nenhum")
        w("")
        w("## Presentes")
        w(f"- Eventos de presente brutos: {self.gift_events_total}")
        w(f"- Com ID de usuário: {self.gift_events_with_id} | com @handle: {self.gift_events_with_handle}")
        w(f"- Presentes consolidados: {len(self.finals)}")
        total_dia = sum(f.total_diamonds for f in self.finals)
        w(f"- Total de diamantes consolidado: {total_dia}")
        w("")
        if self.finals:
            w("| Usuário | Presente | Qtd final | Diamantes | Eventos brutos | Soma ingênua | Fim | Anomalias |")
            w("|---|---|---|---|---|---|---|---|")
            for f in self.finals:
                w(
                    f"| {f.user_key} | {f.gift_name} | {f.count} | {f.total_diamonds} | "
                    f"{f.events_seen} | {f.naive_sum} | {f.ended_by} | {', '.join(f.anomalies) or '-'} |"
                )
            w("")
            by_end = Counter(f.ended_by for f in self.finals)
            w("Como as sequências terminaram: " + ", ".join(f"{k}={v}" for k, v in by_end.items()))
            w("")
        w("## Erros")
        if self.errors:
            for e in self.errors:
                w(f"- {e}")
        else:
            w("- nenhum registrado")
        w("")
        w("## Conclusões (preencher manualmente)")
        w("- Conectou? Foi estável? Quanto tempo?")
        w("- Os presentes enviados por você batem com os consolidados? (compare com sua tabela de verdade)")
        w("- O usuário (ID e @) foi identificado em todos os presentes?")
        w("- repeat_end sempre chegou? Houve contagem diminuindo ou duplicada?")
        w("")
        return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Spike de conexão TikTok LIVE (somente leitura).")
    p.add_argument("username", help="@ do streamer que está em live (com ou sem @)")
    p.add_argument("--label", default="T1", help="rótulo do teste (T1, T2, T3...)")
    p.add_argument("--duration", type=int, default=0, help="segundos; 0 = até Ctrl+C")
    p.add_argument("--sign-url", default=None, help="URL de um servidor de assinatura próprio (opcional)")
    p.add_argument("--sign-api-key", default=None, help="chave de API de assinatura (opcional; prefira variável TIKTOK_SIGN_API_KEY)")
    p.add_argument("--anonymize", action="store_true", help="mascara IDs, @ e apelidos nos arquivos gerados")
    p.add_argument("--save-comments", action="store_true", help="salva o texto dos comentários (padrão: só o tamanho)")
    p.add_argument("--stale-timeout", type=float, default=10.0, help="segundos sem repeat_end para considerar o streak encerrado")
    p.add_argument("--out-dir", default="logs", help="pasta de saída")
    return p.parse_args()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # evita UnicodeEncodeError no console do Windows
        except Exception:
            pass
    args = parse_args()
    session = Session(args)
    code = 1
    try:
        code = asyncio.run(session.run())
    except KeyboardInterrupt:
        print("Interrompido.")
    finally:
        session.finish()
    return code


if __name__ == "__main__":
    sys.exit(main())
