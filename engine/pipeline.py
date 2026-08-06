#!/usr/bin/env python3
"""
Content OS — Pipeline completo (espelha o Creator AI).

Fluxo (igual ao app iacreatorsociety):
  1. Apify coleta reels (meu perfil + concorrentes)
  2. Filtra: meus top 8 / concorrentes top 10 (ultimos 60 dias, por views)
  3. Gemini transcreve cada video (le o video pela URL)
  4. Gemini extrai hook + power words (batch)
  5. Gemini analisa (call 1): top 5, 3 padroes, 10 hooks, takeaway
  6. Gemini roteiriza (call 2): 10 roteiros A/V ate 50s
  7. Escreve data/latest.json pra dashboard

Modelo: gemini-3.5-flash-lite (mesmo do Creator AI).
Keys: lidas de secrets.env (APIFY_TOKEN, GEMINI_API_KEY).
      No produto do aluno ficam EM BRANCO — ele pluga as dele.

Uso:
  python3 pipeline.py --me SEU_USUARIO --competitors CONCORRENTE --network instagram
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ---------- Config (igual ao Creator AI) ----------
APIFY_ACTOR_ID = "xMc5Ga1oCONPmWJIa"   # Instagram reel scraper
APIFY_BASE = "https://api.apify.com/v2"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "models/gemini-3.5-flash-lite"
DAYS_WINDOW = 60
MY_TOP = 8
COMP_TOP = 10
HTTP_TIMEOUT = 180


def log(msg):
    print(f"   📍 {msg}", flush=True)


def load_secrets(path):
    """Le secrets.env. No produto do aluno, as keys ficam em branco."""
    creds = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip()
    return creds


# ---------- HTTP helper ----------
def http_post_json(url, payload, timeout=HTTP_TIMEOUT):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


# ---------- STEP 1: Apify ----------
def scrape_reels(apify_token, username, limit=15):
    username = username.lstrip("@")
    url = f"{APIFY_BASE}/acts/{APIFY_ACTOR_ID}/run-sync-get-dataset-items?token={apify_token}"
    try:
        status, data = http_post_json(url, {"resultsLimit": limit, "username": [username]})
        if isinstance(data, list):
            return data
        return []
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        if e.code == 402:
            raise RuntimeError("Apify: saldo esgotado. Recarregue os creditos em apify.com.")
        if e.code == 401:
            raise RuntimeError("Apify: key invalida ou expirada.")
        raise RuntimeError(f"Apify error ({e.code}): {body}")


def sort_by_views(reels):
    return sorted(reels, key=lambda r: r.get("videoPlayCount") or 0, reverse=True)


# --- Ranking pela JUNÇÃO dos 3 sinais: views + likes + comentários ---
# Cada sinal é normalizado pelo máximo do conjunto (pra likes/comentários pesarem
# mesmo sendo ordens de grandeza menores que views) e somado com pesos.
# Lê os DOIS padrões de nome: IG/TikTok (videoPlayCount/likesCount/commentsCount)
# e YouTube (views/likes/comments) — assim o ranking vale nas 3 redes.
def _views_of(r):
    return r.get("videoPlayCount") or r.get("views") or 0


def _likes_of(r):
    return r.get("likesCount") or r.get("likes") or 0


def _comments_of(r):
    return r.get("commentsCount") or r.get("comments") or 0


def _eng_maxes(reels):
    return {
        "v": max(_views_of(r) for r in reels) or 1,
        "l": max(_likes_of(r) for r in reels) or 1,
        "c": max(_comments_of(r) for r in reels) or 1,
    }


def engagement_score(reel, mx):
    v = _views_of(reel) / mx["v"]
    l = _likes_of(reel) / mx["l"]
    c = _comments_of(reel) / mx["c"]
    return round(100 * (0.5 * v + 0.3 * l + 0.2 * c), 1)


def sort_by_engagement(reels):
    """Ordena pela junção views+likes+comentários (define os 'melhores')."""
    if not reels:
        return []
    mx = _eng_maxes(reels)
    return sorted(reels, key=lambda r: engagement_score(r, mx), reverse=True)


def filter_by_days(reels, days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for r in reels:
        ts = r.get("timestamp")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt >= cutoff:
                out.append(r)
        except Exception:
            continue
    return out


# ---------- STEP 3: Gemini transcribe ----------
TRANSCRIPTION_PROMPT = """**IDIOMA OBRIGATÓRIO: TODO O OUTPUT DEVE SER EM PORTUGUÊS BRASILEIRO (PT-BR).**

You are a Video Script Breakdown Agent. Transcribe the raw video into a clean script.
- Include notable visual elements.
- Maximum length: 2000 characters.
- No timestamps, no commentary. Output only the final script.
MANTER NO IDIOMA ORIGINAL: transcricoes de audio, hooks citados, @usernames e URLs."""


def _gemini_retry_delay(body, attempt, fallback_wait=65):
    """Lê o retryDelay do Google; fallback cobre a janela móvel de 1 minuto."""
    try:
        error = json.loads(body).get("error", {})
        for detail in error.get("details", []):
            delay = detail.get("retryDelay")
            if delay:
                match = re.search(r"([0-9.]+)s", str(delay))
                if match:
                    return max(5, int(float(match.group(1))) + 5)
        match = re.search(r"retry in\s+([0-9.]+)s", error.get("message", ""), re.I)
        if match:
            return max(5, int(float(match.group(1))) + 5)
    except Exception:
        pass
    return fallback_wait * attempt


def gemini_generate(gemini_key, parts, max_tokens=2048, retries=4, fallback_wait=65, json_mode=False):
    url = f"{GEMINI_BASE}/{GEMINI_MODEL}:generateContent?key={gemini_key}"
    generation_config = {"maxOutputTokens": max_tokens}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"
    payload = {"contents": [{"parts": parts}], "generationConfig": generation_config}
    for attempt in range(1, retries + 1):
        try:
            status, data = http_post_json(url, payload, timeout=120)
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code in (429, 503) and attempt < retries:
                wait = _gemini_retry_delay(body, attempt, fallback_wait)
                log(f"Gemini {e.code} — aguardando {wait}s (retry {attempt}/{retries})")
                time.sleep(wait)
                continue
            if e.code == 403:
                raise RuntimeError("Gemini 403: projeto sem acesso. Ative sua conta Google conforme a aula.")
            raise RuntimeError(f"Gemini error ({e.code}): {body[:500]}")
        except Exception as e:
            if attempt < retries:
                time.sleep(5)
                continue
            raise RuntimeError(f"Gemini falhou: {e}")
    return ""


def transcribe_video(gemini_key, video_url):
    parts = [
        {"text": TRANSCRIPTION_PROMPT},
        {"fileData": {"mimeType": "video/mp4", "fileUri": video_url}},
    ]
    try:
        # Alguns links de mídia do TikTok retornam 429 genérico enquanto o vídeo
        # seguinte funciona. Não prenda o pipeline por minutos no mesmo arquivo.
        return gemini_generate(gemini_key, parts, max_tokens=2048, retries=2, fallback_wait=15)
    except Exception as e:
        log(f"transcricao falhou ({str(e)[:60]})")
        return ""


# ---------- STEP 5+6: Gemini chat (analysis + scripts) ----------
def gemini_chat(gemini_key, system_prompt, user_message, max_tokens=8192, json_mode=False):
    parts = [{"text": system_prompt + "\n\n" + user_message}]
    return gemini_generate(gemini_key, parts, max_tokens=max_tokens, json_mode=json_mode)


def try_parse_json(raw):
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if "```" in cleaned else cleaned
        cleaned = cleaned.replace("json", "", 1).strip() if cleaned.lstrip().startswith("json") else cleaned
    bs, be = cleaned.find("{"), cleaned.rfind("}")
    if bs != -1 and be > bs:
        cleaned = cleaned[bs:be + 1]
    try:
        return json.loads(cleaned)
    except Exception:
        import re
        try:
            return json.loads(re.sub(r",(\s*[}\]])", r"\1", cleaned))
        except Exception:
            return None


def build_reel_summary(reels):
    """Compacta reels pro prompt (igual formatReelsForPrompt do Creator AI)."""
    out = []
    for r in reels:
        out.append({
            "url": r.get("url"),
            "ownerUsername": r.get("ownerUsername"),
            "caption": (r.get("caption") or "")[:500],
            "videoPlayCount": r.get("videoPlayCount") or 0,
            "likesCount": r.get("likesCount") or 0,
            "commentsCount": r.get("commentsCount") or 0,
            "timestamp": r.get("timestamp"),
            "transcript": (r.get("transcript") or "")[:1500],
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


def load_prompt_template():
    """Carrega o prompt-cerebro (o mesmo salvo em references/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    # Busca robusta: funciona tanto na skill (scripts/ + ../references/) quanto
    # no repo do aluno (engine/ + engine/references/). Também aceita override por env.
    candidates = [
        os.environ.get("CONTENT_OS_PROMPT", ""),
        os.path.join(here, "references", "prompt-analise-roteiros.md"),
        os.path.join(here, "..", "references", "prompt-analise-roteiros.md"),
    ]
    for ref in candidates:
        if not ref:
            continue
        ref = os.path.abspath(ref)
        if os.path.exists(ref):
            with open(ref) as f:
                content = f.read()
            # extrai o bloco entre a primeira e ultima cerca ```
            if "```" in content:
                block = content.split("```", 2)
                if len(block) >= 3:
                    return block[1].strip()
    return ""


def _days_ago(ts):
    if not ts:
        return 0
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 0


def _guess_format(reel):
    if reel.get("title") is not None and reel.get("videoPlayCount") is None:
        return "Vídeo"  # YouTube
    v = reel.get("videoPlayCount") or 0
    return "Reel" if v else "Post"


def build_dashboard_snapshot(result, me, competitors, my_reels, comp_reels, network, now):
    """Traduz a saida do Gemini pro formato EXATO que o app.js da dashboard consome."""
    net_label = {"instagram": "Instagram", "tiktok": "TikTok", "youtube": "YouTube"}.get(network, network.title())
    net_emoji = {"instagram": "📸", "tiktok": "🎵", "youtube": "▶️"}.get(network, "📱")

    # --- top videos -> networks/posts (cards) ---
    # Os cards saem dos DADOS REAIS (Apify), rankeados pela JUNÇÃO views+likes+comentarios.
    # O texto do Gemini (top_competitor_videos) serve só pra enriquecer o hook por URL.
    gem_by_url = {}
    for tv in result.get("top_competitor_videos", []):
        u = (tv.get("url") or "").strip()
        if u:
            gem_by_url[u] = tv

    ranked = sort_by_engagement(comp_reels or [])[:5]
    mx = _eng_maxes(comp_reels) if comp_reels else {"v": 1, "l": 1, "c": 1}
    posts = []
    for i, r in enumerate(ranked):
        u = (r.get("url") or "").strip()
        gem = gem_by_url.get(u, {})
        # hook: prioriza o do Gemini; senão título (YouTube) ou legenda (IG/TikTok)
        hook = gem.get("hook") or r.get("title") or (r.get("caption") or "")[:120]
        # perfil: ownerUsername (IG/TikTok) ou channel (YouTube)
        profile_raw = r.get("ownerUsername") or r.get("channel") or ""
        post = {
            "rank": i + 1,
            "score": engagement_score(r, mx),
            "profile": ("@" + str(profile_raw).lstrip("@")) if profile_raw else "",
            "hook": hook,
            "views": _views_of(r),
            "likes": _likes_of(r),
            "comments": _comments_of(r),
            "saves": 0,
            "format": _guess_format(r),
            "posted_days_ago": _days_ago(r.get("timestamp") or r.get("date")),
            "url": u,
        }
        # --- extras do YouTube: análise de thumbnail + título (do Gemini) ---
        if network == "youtube":
            post["no_likes"] = True  # actor do YouTube não retorna likes
            post["title"] = r.get("title") or gem.get("title") or ""
            post["thumbnail_url"] = r.get("thumbnail_url") or gem.get("thumbnail_url") or ""
            post["thumbnail_analysis"] = r.get("thumbnail_analysis") or gem.get("thumbnail_analysis") or ""
            post["power_words"] = r.get("power_words") or gem.get("power_words") or []
            post["hook_type"] = r.get("hook_type") or gem.get("hook_type") or ""
        posts.append(post)

    # --- hooks ---
    hooks = [{"hook": h.get("hook", ""), "why": h.get("why_it_works", "")}
             for h in result.get("hook_ideas", [])]

    # --- roteiros (A/V) ---
    roteiros = []
    for s in result.get("video_scripts", []):
        roteiros.append({
            "titulo": f"Roteiro {s.get('script_number', len(roteiros)+1)}",
            "rede": net_label,
            "duracao": s.get("estimated_duration", "até 50s"),
            "baseado_em": "top campeões",
            "hook_ref": s.get("hook_reference", ""),
            "av": s.get("script", ""),
        })

    # --- padroes (com barra de forca) ---
    patterns = []
    for i, p in enumerate(result.get("winning_patterns", [])):
        patterns.append({
            "titulo": p.get("pattern_name", ""),
            "detalhe": p.get("explanation", ""),
            "forca": 92 - i * 8,
        })

    # --- takeaway (texto + acoes) ---
    kt = result.get("key_takeaway", "")
    takeaway = {"texto": kt if isinstance(kt, str) else kt.get("texto", ""), "acoes": []}
    if isinstance(kt, dict):
        takeaway["acoes"] = kt.get("acoes", []) or kt.get("action_items", [])

    # --- analise (diagnostico voce vs campeoes) ---
    my_max = max((_views_of(r) for r in my_reels), default=0)
    comp_max = max((_views_of(r) for r in comp_reels), default=0)
    my_avg = int(sum(_views_of(r) for r in my_reels) / max(1, len(my_reels)))
    comp_avg = int(sum(_views_of(r) for r in comp_reels) / max(1, len(comp_reels)))
    my_likes = int(sum(_likes_of(r) for r in my_reels) / max(1, len(my_reels)))
    comp_likes = int(sum(_likes_of(r) for r in comp_reels) / max(1, len(comp_reels)))
    my_comm = int(sum(_comments_of(r) for r in my_reels) / max(1, len(my_reels)))
    comp_comm = int(sum(_comments_of(r) for r in comp_reels) / max(1, len(comp_reels)))
    unit = "vídeos" if network == "youtube" else "reels"
    analise = {
        "titulo": f"@{_handle(me)} vs. {', '.join('@'+_handle(c) for c in competitors)}",
        "insight": takeaway["texto"][:280] if takeaway["texto"] else "",
        "comparacao": [
            {"criterio": "Melhor vídeo (views)", "voce": _fmt(my_max), "campeoes": _fmt(comp_max),
             "status": "ok" if my_max >= comp_max else "warn"},
            {"criterio": "Média de views", "voce": _fmt(my_avg), "campeoes": _fmt(comp_avg),
             "status": "ok" if my_avg >= comp_avg else "warn"},
            {"criterio": "Média de likes", "voce": _fmt(my_likes), "campeoes": _fmt(comp_likes),
             "status": "ok" if my_likes >= comp_likes else "warn"},
            {"criterio": "Média de comentários", "voce": _fmt(my_comm), "campeoes": _fmt(comp_comm),
             "status": "ok" if my_comm >= comp_comm else "warn"},
            {"criterio": f"{unit.capitalize()} analisados", "voce": str(len(my_reels)), "campeoes": str(len(comp_reels)),
             "status": "ok"},
        ],
    }

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "nicho": "Inteligência Artificial",
        "resumo": {
            "posts_analisados": len(my_reels) + len(comp_reels),
            "redes": 1,
            "melhor_rede": net_label,
            "melhor_formato": "Reel",
        },
        "analise": analise,
        "networks": {
            network: {"label": net_label, "emoji": net_emoji, "posts": posts},
        },
        "hooks": hooks,
        "roteiros": roteiros,
        "patterns": patterns,
        "takeaway": takeaway,
        "calendar": build_calendar(result, network, now),
    }


def build_calendar(result, network, start=None):
    """Organiza os 10 roteiros num calendario de postagem (cadencia 3x/semana,
    melhores dias/horarios pro nicho de IA). Deterministico, sem custo de LLM."""
    net_label = {"instagram": "Instagram", "tiktok": "TikTok"}.get(network, network.title())
    scripts = result.get("video_scripts", [])
    hooks = result.get("hook_ideas", [])
    # 3 posts/semana em dias de maior alcance pra conteudo de IA/tech
    slots = [
        ("Seg", "09h"), ("Ter", "12h"), ("Qua", "18h"),
        ("Qui", "09h"), ("Sex", "12h"), ("Sáb", "11h"), ("Dom", "19h"),
    ]
    # cadencia: Ter / Qui / Sab (3x semana) — melhores dias p/ IA
    cadence = [("Ter", "12h"), ("Qui", "18h"), ("Sáb", "11h")]
    start = start or datetime.now(timezone.utc)
    cal = []
    for i, s in enumerate(scripts):
        week = i // 3 + 1
        dia_nome, hora = cadence[i % 3]
        hook_ref = s.get("hook_reference", "")
        # tenta achar o hook completo correspondente
        ideia = hook_ref or (hooks[i].get("hook", "") if i < len(hooks) else "")
        cal.append({
            "dia": f"Sem {week} · {dia_nome} {hora}",
            "rede": net_label,
            "formato": s.get("estimated_duration", "Reel até 50s"),
            "ideia": f"Roteiro {s.get('script_number', i+1)}: " + (ideia[:90] if ideia else "gravar roteiro"),
            "hook_sugerido": hook_ref[:80] if hook_ref else "",
        })
    return cal


def _fmt(n):
    n = n or 0
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if n >= 1_000:
        return f"{n/1_000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(n)


def _handle(s):
    """Extrai o handle limpo de uma URL do YouTube ou de um @usuario."""
    s = str(s or "").strip().rstrip("/")
    if "youtube.com/" in s or "youtu.be/" in s:
        s = s.split("/")[-1]
    return s.lstrip("@")


def run_instagram(me, competitors, gemini, apify, max_transcribe):
    """Pipeline Instagram: coleta reels, transcreve, gera analise+roteiros."""
    # STEP 1: coleta
    log(f"Coletando reels de @{me}...")
    my_raw = scrape_reels(apify, me, 15)
    my_reels = sort_by_engagement(filter_by_days(my_raw, DAYS_WINDOW))[:MY_TOP]
    if not my_reels:
        my_reels = sort_by_engagement(my_raw)[:MY_TOP]
    log(f"@{me}: {len(my_reels)} reels selecionados")

    comp_reels = []
    for c in competitors:
        log(f"Coletando reels de @{c}...")
        raw = scrape_reels(apify, c, 15)
        filt = sort_by_engagement(filter_by_days(raw, DAYS_WINDOW))[:COMP_TOP]
        if len(filt) < 5:
            filt = sort_by_engagement(raw)[:COMP_TOP]
        comp_reels.extend(filt)
        log(f"@{c}: {len(filt)} reels")

    # STEP 3: transcricao (limitada pra custo/tempo)
    my_quota = (max_transcribe + 1) // 2
    comp_quota = max_transcribe // 2
    to_transcribe = my_reels[:my_quota] + comp_reels[:comp_quota]
    log(f"Transcrevendo {len(to_transcribe)} videos com Gemini...")
    for i, r in enumerate(to_transcribe):
        vurl = r.get("videoUrl")
        if vurl:
            r["transcript"] = transcribe_video(gemini, vurl)
            log(f"  video {i+1}/{len(to_transcribe)} transcrito ({len(r.get('transcript',''))} chars)")

    # STEP 5: analise + roteiros (prompt-cerebro)
    template = load_prompt_template()
    if not template:
        raise RuntimeError("prompt-cerebro nao encontrado em references/")

    prompt = (template
              .replace("{{your_username}}", me)
              .replace("{{my_reels_data}}", build_reel_summary(my_reels))
              .replace("{{competitor_reels_data}}", build_reel_summary(sort_by_views(comp_reels))))

    log("Gerando analise + roteiros (Gemini)...")
    result = None
    for attempt in range(1, 3):
        raw = gemini_chat(gemini, prompt, "Gere o JSON completo agora.", max_tokens=16384)
        result = try_parse_json(raw)
        if result and result.get("video_scripts"):
            log(f"JSON parseado OK (tentativa {attempt}): {len(result.get('video_scripts',[]))} roteiros")
            break
        result = None
    return result, my_reels, comp_reels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--me", required=True, help="Seu @ (sem o @)")
    ap.add_argument("--competitors", required=True, help="Concorrentes separados por virgula")
    ap.add_argument("--network", default="instagram", choices=["instagram", "tiktok", "youtube"])
    ap.add_argument("--secrets", default="/root/content-os/secrets.env")
    ap.add_argument("--out", default="/root/projects/content-os-dashboard/data/latest.json")
    ap.add_argument("--max-transcribe", type=int, default=6, help="Limite de videos a transcrever (custo/tempo)")
    args = ap.parse_args()

    creds = load_secrets(args.secrets)
    apify = creds.get("APIFY_TOKEN")
    gemini = creds.get("GEMINI_API_KEY")
    if not apify or not gemini:
        print("ERRO: faltam APIFY_TOKEN e/ou GEMINI_API_KEY no secrets.env")
        sys.exit(1)

    me = args.me.lstrip("@")
    competitors = [c.strip().lstrip("@") for c in args.competitors.split(",") if c.strip()]
    t0 = time.time()

    creds = {"APIFY_TOKEN": apify, "GEMINI_API_KEY": gemini}

    # roteamento por rede
    if args.network == "tiktok":
        import net_tiktok
        result, my_reels, comp_reels = net_tiktok.run_tiktok(me, competitors, creds, args.max_transcribe, log)
    elif args.network == "youtube":
        import net_youtube
        result, my_reels, comp_reels = net_youtube.run_youtube(me, competitors, creds, log)
    else:
        result, my_reels, comp_reels = run_instagram(me, competitors, gemini, apify, args.max_transcribe)

    if not result or not result.get("video_scripts"):
        print("ERRO: pipeline nao retornou roteiros validos")
        sys.exit(1)

    # monta latest.json NO FORMATO que a dashboard (app.js) consome
    now = datetime.now(timezone.utc)
    snapshot = build_dashboard_snapshot(result, me, competitors, my_reels, comp_reels, args.network, now)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    dt = time.time() - t0
    log(f"✅ Concluido em {dt:.0f}s")
    print(f"\nRESUMO ({args.network}):")
    print(f"  hooks: {len(snapshot.get('hooks', []))}")
    print(f"  roteiros: {len(snapshot.get('roteiros', []))}")
    print(f"  top videos: {len(snapshot.get('networks', {}).get(args.network, {}).get('posts', []))}")
    print(f"  padroes: {len(snapshot.get('patterns', []))}")
    print(f"  calendario: {len(snapshot.get('calendar', []))} posts")
    print(f"  saida: {args.out}")


if __name__ == "__main__":
    main()
