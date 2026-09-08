#!/usr/bin/env python3
"""
Content OS — funde snapshots single-rede em UM snapshot multi-rede.

Cada snapshot de entrada (gerado pelo pipeline) tem:
  generated_at, nicho, resumo, analise, networks{<rede>:{label,emoji,posts}},
  hooks[], roteiros[], patterns[], takeaway{}, calendar[]

Saída multi-rede: cada rede carrega o PACOTE COMPLETO dela, e o topo
guarda metadados + a ordem das redes. O app.js troca tudo ao clicar na rede.

Uso:
  python3 merge_networks.py OUT.json IN_A.json IN_B.json [IN_C.json ...]
"""
import json
import os
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def net_key(snap):
    """Descobre a chave de rede do snapshot (instagram/tiktok/youtube)."""
    nets = snap.get("networks", {})
    if nets:
        return list(nets.keys())[0]
    # fallback pelo resumo
    mr = (snap.get("resumo", {}) or {}).get("melhor_rede", "").lower()
    return mr or "rede"


def build(out_path, in_paths):
    # CARREGA o multi-rede existente primeiro (se houver) — preserva redes
    # que não estão sendo re-rodadas nesta chamada (ex: rodar --only tiktok
    # não deve apagar o instagram já salvo).
    existing = {}
    existing_order = []
    nicho = None
    if os.path.exists(out_path):
        try:
            prev = load(out_path)
            existing = dict(prev.get("networks", {}) or {})
            existing_order = list(prev.get("network_order", []) or existing.keys())
            nicho = prev.get("nicho")
        except Exception:
            pass  # latest.json corrompido/vazio — segue do zero

    merged = {
        "generated_at": None,
        "nicho": nicho,
        "multi_network": True,
        "network_order": list(existing_order),
        "networks": existing,
        # resumo agregado (recalculado)
        "resumo": {},
    }
    latest_gen = ""

    for p in in_paths:
        snap = load(p)
        key = net_key(snap)
        meta = snap.get("networks", {}).get(key, {})
        label = meta.get("label", key.title())
        emoji = meta.get("emoji", "")
        posts = meta.get("posts", [])

        # pacote completo da rede (SOBRESCREVE apenas esta rede)
        merged["networks"][key] = {
            "label": label,
            "emoji": emoji,
            "posts": posts,
            "resumo": snap.get("resumo", {}),
            "analise": snap.get("analise"),
            "hooks": snap.get("hooks", []),
            "roteiros": snap.get("roteiros", []),
            "patterns": snap.get("patterns", []),
            "takeaway": snap.get("takeaway"),
            "calendar": snap.get("calendar", []),
            # exclusivo do YouTube: pros/contras por canal concorrente
            "competitor_pros_contras": snap.get("competitor_pros_contras", []),
            # lista operacional de posts da semana (status de publicacao)
            "posts_semana": snap.get("posts_semana", []),
        }
        if key not in merged["network_order"]:
            merged["network_order"].append(key)

        g = snap.get("generated_at", "")
        if g > latest_gen:
            latest_gen = g
        if not merged["nicho"]:
            merged["nicho"] = snap.get("nicho")

    # resumo agregado: recalculado sobre TODAS as redes presentes (antigas + novas)
    total_posts = 0
    formats = []
    for key in merged["network_order"]:
        net = merged["networks"].get(key, {})
        r = net.get("resumo", {}) or {}
        total_posts += r.get("posts_analisados", 0)
        f = r.get("melhor_formato")
        if f:
            formats.append(f)

    merged["generated_at"] = latest_gen or None
    labels = [merged["networks"][k]["label"] for k in merged["network_order"]]
    merged["resumo"] = {
        "posts_analisados": total_posts,
        "redes": len(merged["network_order"]),
        "melhor_rede": " + ".join(labels),
        "melhor_formato": formats[0] if formats else "Reel",
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(merged['network_order'])} redes no total -> {out_path}")
    print("redes:", ", ".join(merged["network_order"]))
    print("posts agregados:", total_posts)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("uso: merge_networks.py OUT.json IN_A.json IN_B.json ...")
        sys.exit(1)
    build(sys.argv[1], sys.argv[2:])
