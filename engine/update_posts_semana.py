#!/usr/bin/env python3
"""
Content OS — atualiza o status dos posts da semana (posts_semana[]) no
latest.json SEM re-rodar a análise (zero custo Apify/Gemini).

Uso:
  # marca item(s) por índice (1-based, na ordem exibida na dashboard):
  python3 update_posts_semana.py --status agendado --items 1,4
  python3 update_posts_semana.py --status publicado --items 2 --link "https://instagram.com/p/xxx"
  python3 update_posts_semana.py --status falhou --items 3 --motivo "Apify sem crédito"

  # marca pelo dia (match exato do campo 'dia', ex: "Sem 1 · Ter 12h"):
  python3 update_posts_semana.py --status publicado --dia "Sem 1 · Ter 12h" --link "..."

  # rede opcional (instagram/tiktok/youtube) — sem isso, aplica à rede que casar:
  python3 update_posts_semana.py --status publicado --dia "Sem 1 · Ter 12h" --rede instagram

Só aceita status: pendente | agendado | publicado | falhou.
Após atualizar, a dashboard precisa ser re-deployada (vercel deploy --prod).
"""
import argparse
import json
import os
import sys

VALID_STATUS = {"pendente", "agendado", "publicado", "falhou"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", required=True, choices=sorted(VALID_STATUS))
    ap.add_argument("--items", default="", help="índices 1-based, ex: 1,4")
    ap.add_argument("--dia", default="", help="match exato do campo dia")
    ap.add_argument("--rede", default="", help="filtrar por rede (instagram/tiktok/youtube)")
    ap.add_argument("--link", default="", help="URL da publicação (status publicado)")
    ap.add_argument("--motivo", default="", help="motivo (gravado no campo ideia em [ ] quando falhou)")
    ap.add_argument("--latest", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard", "data", "latest.json"))
    args = ap.parse_args()

    latest = os.path.abspath(args.latest)
    if not os.path.exists(latest):
        print(f"ERRO: {latest} não encontrado"); sys.exit(1)

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    networks = data.get("networks", {})
    if args.rede and args.rede not in networks:
        print(f"ERRO: rede '{args.rede}' não está no latest.json ({list(networks)})"); sys.exit(1)
    targets = [args.rede] if args.rede else list(networks.keys())

    idxs = set()
    if args.items:
        try:
            idxs = {int(x) for x in args.items.split(",") if x.strip()}
        except ValueError:
            print("ERRO: --items deve ser ex: 1,4"); sys.exit(1)
    if not idxs and not args.dia:
        print("ERRO: informe --items ou --dia"); sys.exit(1)

    changed = 0
    for net in targets:
        ps = networks.get(net, {}).get("posts_semana") or []
        for i, p in enumerate(ps, start=1):
            match = (i in idxs) or (args.dia and p.get("dia") == args.dia)
            if not match:
                continue
            p["status"] = args.status
            if args.link:
                p["link_publicado"] = args.link
            if args.motivo:
                p["motivo"] = args.motivo
            changed += 1

    if not changed:
        print("Nenhum item casou com o filtro — nada alterado."); sys.exit(1)

    with open(latest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"OK: {changed} item(ns) -> status '{args.status}' gravado em {latest}")
    print("Lembre de re-deployar: cd dashboard && vercel deploy --prod --yes --token $VT")


if __name__ == "__main__":
    main()
