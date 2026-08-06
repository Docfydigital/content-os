#!/usr/bin/env python3
"""
Content OS — ORQUESTRADOR (roda as 3 redes e funde numa dashboard só).

É o comando ÚNICO que o aluno roda. Ele:
  1. Lê os perfis (seu + concorrentes) por rede do config.json
  2. Roda o pipeline pra cada rede ativada (Instagram, TikTok, YouTube)
  3. Funde tudo num único latest.json (multi-rede) que a dashboard consome
  4. (opcional) salva o snapshot anterior no history/

Uso:
  python3 run_all.py                      # usa config.json ao lado do secrets
  python3 run_all.py --config /caminho/config.json
  python3 run_all.py --only instagram,tiktok   # roda só essas redes
  python3 run_all.py --dashboard /caminho/content-os-dashboard

Config (config.json) — exemplo:
{
  "networks": {
    "instagram": { "me": "seu_user", "competitors": ["concorrente1", "concorrente2"] },
    "tiktok":    { "me": "seu_user", "competitors": ["concorrente1"] },
    "youtube":   { "me": "https://www.youtube.com/@seucanal",
                   "competitors": ["https://www.youtube.com/@concorrente"] }
  },
  "max_transcribe": 6
}
Redes sem 'me' preenchido são puladas automaticamente.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# Defaults PORTÁVEIS: relativos ao próprio pacote (funciona na máquina de qualquer aluno).
# Podem ser sobrescritos por variável de ambiente ou flag.
DEFAULT_SECRETS = os.environ.get("CONTENT_OS_SECRETS", os.path.join(HERE, "secrets.env"))
DEFAULT_CONFIG = os.environ.get("CONTENT_OS_CONFIG", os.path.join(HERE, "config.json"))
DEFAULT_DASHBOARD = os.environ.get(
    "CONTENT_OS_DASHBOARD",
    os.path.abspath(os.path.join(HERE, "..", "..", "content-os-dashboard")),
)
NETWORKS = ["instagram", "tiktok", "youtube"]


def log(msg):
    print(f"[run_all] {msg}", flush=True)


def load_config(path):
    if not os.path.exists(path):
        log(f"config nao encontrado em {path} — crie a partir de config.example.json")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_network(network, cfg_net, secrets, max_transcribe, out_path):
    me = str(cfg_net.get("me") or "").strip()
    comps = cfg_net.get("competitors") or []
    if not me or not comps:
        log(f"pulando {network}: 'me' ou 'competitors' vazios no config")
        return False
    comp_arg = ",".join(str(c).strip() for c in comps if str(c).strip())
    cmd = [
        sys.executable, os.path.join(HERE, "pipeline.py"),
        "--me", me,
        "--competitors", comp_arg,
        "--network", network,
        "--secrets", secrets,
        "--out", out_path,
        "--max-transcribe", str(max_transcribe),
    ]
    log(f"rodando {network}: @{me} vs {comp_arg} ...")
    t0 = time.time()
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        log(f"FALHA em {network} (exit {r.returncode})")
        return False
    log(f"{network} OK em {time.time()-t0:.0f}s -> {out_path}")
    return True


def merge(dashboard, produced, save_history=True):
    """Funde os snapshots single-rede no latest.json multi-rede da dashboard."""
    data_dir = os.path.join(dashboard, "data")
    latest = os.path.join(data_dir, "latest.json")
    os.makedirs(os.path.join(data_dir, "history"), exist_ok=True)

    # salva o snapshot atual no history antes de sobrescrever
    if save_history and os.path.exists(latest):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H%M UTC")
        hist = os.path.join(data_dir, "history", f"{stamp}.json")
        try:
            with open(latest, encoding="utf-8") as f:
                cur = f.read()
            with open(hist, "w", encoding="utf-8") as f:
                f.write(cur)
            log(f"snapshot anterior salvo em history/{stamp}.json")
        except Exception as e:
            log(f"nao consegui salvar history ({e}) — seguindo")

    merge_tool = os.path.join(dashboard, "tools", "merge_networks.py")
    cmd = [sys.executable, merge_tool, latest] + produced
    r = subprocess.run(cmd)
    if r.returncode != 0:
        log("FALHA ao fundir redes")
        return False
    log(f"fusao OK -> {latest}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--secrets", default=DEFAULT_SECRETS)
    ap.add_argument("--dashboard", default=DEFAULT_DASHBOARD)
    ap.add_argument("--only", default="", help="redes a rodar, ex: instagram,tiktok")
    ap.add_argument("--no-history", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    max_transcribe = int(cfg.get("max_transcribe", 6))
    nets_cfg = cfg.get("networks", {})

    only = [n.strip() for n in args.only.split(",") if n.strip()] if args.only else NETWORKS

    produced = []
    for net in NETWORKS:
        if net not in only:
            continue
        if net not in nets_cfg:
            continue
        out = os.path.join("/tmp", f"content-os-{net}.json")
        if run_network(net, nets_cfg[net], args.secrets, max_transcribe, out):
            produced.append(out)

    if not produced:
        log("nenhuma rede rodou (config vazio?). Nada a fundir.")
        sys.exit(1)

    ok = merge(args.dashboard, produced, save_history=not args.no_history)
    # limpa temporarios
    for p in produced:
        try:
            os.remove(p)
        except OSError:
            pass

    if not ok:
        sys.exit(1)

    log("PRONTO. Agora publique a dashboard:")
    log(f"  cd {args.dashboard} && vercel deploy --prod --yes --token SEU_VERCEL_TOKEN")


if __name__ == "__main__":
    main()
