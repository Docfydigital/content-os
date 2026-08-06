#!/usr/bin/env python3
"""
Content OS — publicador Postpeer (calendario -> POST /v1/posts).

Lê o calendario da dashboard (latest.json, multi-rede) e cria os posts no Postpeer.
Cada item do calendario vira um POST /v1/posts (agendado via scheduledFor).

IMPORTANTE — SEGURO POR PADRÃO:
  - Roda em DRY-RUN por padrão: só MOSTRA o que enviaria, NÃO publica nada.
  - Só publica de verdade com a flag --confirm.
  - Precisa do accountId de cada rede (pegue em GET /v1/connect/{platform} depois de
    conectar suas contas no Postpeer). Passe via --accounts '{"instagram":"acc_x","tiktok":"acc_y"}'
    ou no config.json em "postpeer_accounts".

Uso:
  python3 publish_postpeer.py                          # DRY-RUN (nao publica)
  python3 publish_postpeer.py --confirm                # PUBLICA de verdade
  python3 publish_postpeer.py --network instagram      # so uma rede
  python3 publish_postpeer.py --timezone America/Sao_Paulo

Auth: header 'x-access-key: <POSTPEER_API_KEY>' (nao e Bearer). Base https://api.postpeer.dev/v1
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

POSTPEER_BASE = "https://api.postpeer.dev/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
# Defaults PORTÁVEIS: relativos ao próprio pacote (funciona na máquina de qualquer aluno).
DEFAULT_SECRETS = os.environ.get("CONTENT_OS_SECRETS", os.path.join(HERE, "secrets.env"))
DEFAULT_CONFIG = os.environ.get("CONTENT_OS_CONFIG", os.path.join(HERE, "config.json"))
DEFAULT_DASHBOARD = os.environ.get(
    "CONTENT_OS_DASHBOARD",
    os.path.abspath(os.path.join(HERE, "..", "dashboard")),
)
# Postpeer usa nomes de plataforma proprios
PLATFORM_MAP = {"instagram": "instagram", "tiktok": "tiktok", "youtube": "youtube"}


def load_env(path):
    d = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def postpeer_post(api_key, payload):
    req = urllib.request.Request(
        f"{POSTPEER_BASE}/posts",
        data=json.dumps(payload).encode("utf-8"),
        headers={"x-access-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        return e.code, {"error": body[:300]}
    except Exception as e:
        return 0, {"error": str(e)[:200]}


# dias da semana PT -> índice (segunda=0)
_WD = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "sáb": 5, "dom": 6}


def build_scheduled_for(item, base=None):
    """Converte a data do calendario em ISO-8601.
    Aceita ISO explícito ('data'+'hora') OU o formato relativo do Content OS
    ('dia' = 'Sem 1 · Ter 12h'), que vira uma data real futura a partir de hoje."""
    # 1) formato explícito, se existir
    date = item.get("data") or item.get("date") or ""
    if date:
        hora = item.get("hora") or item.get("time") or "12:00"
        try:
            return datetime.fromisoformat(f"{date}T{hora}:00").isoformat()
        except ValueError:
            return date
    # 2) formato relativo: "Sem N · <Dia> <Hh>h"
    dia = str(item.get("dia") or "").lower()
    if not dia:
        return None
    base = base or datetime.now()
    m = re.search(r"sem\s*(\d+)", dia)
    week = int(m.group(1)) if m else 1
    wd = None
    for k, v in _WD.items():
        if k in dia:
            wd = v
            break
    hm = re.search(r"(\d{1,2})\s*h", dia)
    hour = int(hm.group(1)) if hm else 12
    if wd is None:
        return None
    # próxima ocorrência do dia-da-semana + (week-1) semanas
    days_ahead = (wd - base.weekday()) % 7
    target = base + timedelta(days=days_ahead + (week - 1) * 7)
    target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
    return target.isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secrets", default=DEFAULT_SECRETS)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--dashboard", default=DEFAULT_DASHBOARD)
    ap.add_argument("--network", default="", help="publicar so uma rede (instagram/tiktok/youtube)")
    ap.add_argument("--accounts", default="", help='JSON: {"instagram":"acc_id", ...}')
    ap.add_argument("--timezone", default="America/Sao_Paulo")
    ap.add_argument("--confirm", action="store_true", help="PUBLICA de verdade (sem isso e dry-run)")
    args = ap.parse_args()

    secrets = load_env(args.secrets)
    api_key = secrets.get("POSTPEER_API_KEY", "")
    if not api_key or api_key == "SUA_KEY_AQUI":
        print("ERRO: POSTPEER_API_KEY nao configurada no secrets.env")
        sys.exit(1)

    # accountId por rede (obrigatorio pra publicar de verdade)
    accounts = {}
    if args.accounts:
        accounts = json.loads(args.accounts)
    elif os.path.exists(args.config):
        cfg = json.load(open(args.config, encoding="utf-8"))
        accounts = cfg.get("postpeer_accounts", {}) or {}

    latest = os.path.join(args.dashboard, "data", "latest.json")
    data = json.load(open(latest, encoding="utf-8"))
    networks = data.get("networks", {})
    order = data.get("network_order", list(networks.keys()))

    mode = "PUBLICANDO" if args.confirm else "DRY-RUN (nada sera publicado)"
    print(f"=== Postpeer — {mode} ===")
    total, sent, failed = 0, 0, 0

    for net in order:
        if args.network and net != args.network:
            continue
        pkg = networks.get(net, {})
        cal = pkg.get("calendar", []) or []
        platform = PLATFORM_MAP.get(net, net)
        acc_id = accounts.get(net, "")
        print(f"\n[{net}] {len(cal)} posts no calendario | accountId={acc_id or 'FALTANDO'}")

        for item in cal:
            total += 1
            content = (item.get("legenda") or item.get("caption") or item.get("ideia")
                       or item.get("hook_sugerido") or item.get("titulo") or item.get("tema") or "")
            scheduled = build_scheduled_for(item)
            payload = {
                "content": content,
                "platforms": [{"platform": platform, "accountId": acc_id}],
                "timezone": args.timezone,
            }
            if scheduled:
                payload["scheduledFor"] = scheduled
            else:
                payload["publishNow"] = False

            label = (content or "(sem legenda)")[:60].replace("\n", " ")
            if not args.confirm:
                when = scheduled or "sem data"
                print(f"  DRY  {when} | {label}")
                continue
            if not acc_id:
                print(f"  SKIP {label} — accountId ausente pra {net}")
                failed += 1
                continue
            status, resp = postpeer_post(api_key, payload)
            if 200 <= status < 300:
                pid = resp.get("id") or resp.get("postId") or ""
                print(f"  OK   {scheduled} | {label} -> {pid}")
                sent += 1
            else:
                print(f"  ERRO ({status}) {label}: {resp.get('error','')[:120]}")
                failed += 1

    print(f"\n=== resumo: {total} no calendario | publicados={sent} | falhas={failed} ===")
    if not args.confirm:
        print("Isto foi um DRY-RUN. Para publicar de verdade, rode com --confirm")
        print("(e garanta que os accountId de cada rede estao no config.json em 'postpeer_accounts').")


if __name__ == "__main__":
    main()
