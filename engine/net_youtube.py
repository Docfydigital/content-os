#!/usr/bin/env python3
"""
Content OS — Módulo YouTube (porta do YouTube OS do Creator AI, JS -> Python).

Substitui o pipeline JS de 3 fases por um módulo Python autocontido (urllib puro),
que se integra ao pipeline.py do Content OS.

FASES (fiéis ao youtube.js):
  Fase 1 — Niche Outliers:
      Faz scrape dos canais concorrentes (Apify youtube-scraper), pega os vídeos
      recentes (últimos 6 meses), top 10 por views por canal, detecta OUTLIERS
      (views >= 3x a média do conjunto) e analisa as POWER WORDS dos títulos.
  Fase 2 — Broad/Niche Search:
      Busca no YouTube (Apify search) o top 5 SEMANAL do nicho amplo e o top 5
      DIÁRIO do nicho específico; analisa power words dos títulos.
  Fase 3 — Comments + Creative Agent:
      Faz scrape do MEU canal, coleta comentários dos meus top 5 vídeos
      (Apify comments-scraper), extrai insights de audiência e roda o
      AGENTE CRIATIVO (Gemini) que sintetiza TODOS os dados em um plano criativo.

Diferença p/ Instagram/TikTok: YouTube trabalha com TÍTULOS + DESCRIÇÕES +
COMENTÁRIOS (não transcreve o vídeo). Por isso NÃO há chamada de transcrição.

Modelo: gemini-3.5-flash-lite (reutiliza gemini_chat do pipeline.py).
Import permitido: from pipeline import gemini_chat, try_parse_json.

Contrato de saída (consumido por build_dashboard_snapshot em pipeline.py):
  run_youtube(me_channel, competitor_channels, creds, log_fn)
    -> (result_dict, my_videos, comp_videos)
"""
import json
import re
import urllib.request
import urllib.error
import base64
import concurrent.futures

# Reutiliza o mesmo LLM helper + parser do pipeline Instagram (mesmo modelo).
from pipeline import gemini_chat, gemini_generate, try_parse_json

# ---------- Config (igual ao youtube.js) ----------
YOUTUBE_SCRAPER_ACTOR = "streamers~youtube-scraper"
YOUTUBE_COMMENTS_ACTOR = "streamers~youtube-comments-scraper"
APIFY_BASE = "https://api.apify.com/v2"
APIFY_TIMEOUT = 300  # segundos

# Nicho do Content OS (output sempre em PT-BR, nicho de IA).
DEFAULT_NICHE = "Inteligência Artificial"
DEFAULT_BROAD_NICHE = "Tecnologia e Inovação"

SIX_MONTHS_DAYS = 180


# ---------- HTTP helper (urllib puro, mesmo estilo do pipeline.py) ----------
def http_post_json(url, payload, timeout=APIFY_TIMEOUT):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


# ---------- Apify helpers (espelham apifyRun/scrapeChannel/...) ----------
def extract_channel_id(url):
    m = re.search(r"youtube\.com/(?:channel/|c/|@)([^/?]+)", url or "")
    return m.group(1) if m else (url or "")


def apify_run(apify_token, actor_name, input_obj):
    url = f"{APIFY_BASE}/acts/{actor_name}/run-sync-get-dataset-items?token={apify_token}"
    try:
        status, data = http_post_json(url, input_obj)
        return data if isinstance(data, list) else []
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        if e.code == 402:
            raise RuntimeError("Apify: saldo esgotado. Recarregue seus créditos em apify.com.")
        if e.code == 401:
            raise RuntimeError("Apify: key inválida ou expirada. Verifique em apify.com -> Settings -> Integrations.")
        if e.code == 404:
            raise RuntimeError(f"Apify: actor {actor_name} não encontrado.")
        if e.code == 429:
            raise RuntimeError("Apify: muitas requisições. Aguarde alguns minutos.")
        raise RuntimeError(f"Apify error ({e.code}): {body}")


def scrape_channel(apify_token, channel_url, max_results=30):
    return apify_run(apify_token, YOUTUBE_SCRAPER_ACTOR, {
        "startUrls": [{"url": channel_url}],
        "maxResults": max_results or 30,
        "sortBy": "date",
    })


def scrape_search(apify_token, search_query, max_results=5, date_filter=None):
    input_obj = {
        "searchKeywords": search_query,
        "maxResults": max_results or 5,
        "sortBy": "relevance",
    }
    if date_filter:
        input_obj["dateFilter"] = date_filter
    return apify_run(apify_token, YOUTUBE_SCRAPER_ACTOR, input_obj)


def scrape_comments(apify_token, video_urls, max_comments=100):
    return apify_run(apify_token, YOUTUBE_COMMENTS_ACTOR, {
        "startUrls": [{"url": u} for u in video_urls],
        "maxComments": max_comments or 100,
        "sortBy": "top",
    })


# ---------- Outlier detection + normalização (fiéis ao JS) ----------
def _views_of(v):
    return v.get("viewCount") or v.get("views") or 0


def detect_outliers(videos):
    """Outlier = views >= 3x a média do conjunto; retorna top 10 desc."""
    if not videos:
        return []
    views = [_views_of(v) for v in videos]
    avg = sum(views) / len(views) if views else 0
    threshold = avg * 3
    filtered = [v for v in videos if _views_of(v) >= threshold]
    filtered.sort(key=_views_of, reverse=True)
    return filtered[:10]


def normalize_video(v):
    return {
        "title": v.get("title") or "",
        "url": v.get("url") or v.get("videoUrl") or "",
        "views": v.get("viewCount") or v.get("views") or 0,
        "likes": v.get("likes") or 0,
        "comments": v.get("commentsCount") or v.get("numberOfComments") or 0,
        "thumbnail_url": v.get("thumbnailUrl") or v.get("thumbnail") or "",
        "channel": v.get("channelName") or v.get("channelTitle") or "",
        "date": v.get("date") or v.get("uploadDate") or "",
        "description": (v.get("description") or "")[:500],
    }


def _parse_json_array(raw):
    """try_parse_json foca em objetos {}. Aqui parseamos arrays [] (analisador de títulos)."""
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        nl = cleaned.find("\n")
        if nl > -1:
            cleaned = cleaned[nl + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
        cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, list) else None
    except Exception:
        bs, be = cleaned.find("["), cleaned.rfind("]")
        if bs != -1 and be > bs:
            try:
                parsed = json.loads(cleaned[bs:be + 1])
                return parsed if isinstance(parsed, list) else None
            except Exception:
                return None
    return None


# ---------- Prompts (COPIADOS FIEL do youtube.js, em PT-BR) ----------
TITLE_ANALYZER_SYSTEM = "\n".join([
    "# Title Power Word Analyzer",
    "",
    "Voce e um especialista em YouTube copywriting.",
    "Analise os titulos fornecidos e extraia as power words/frases que contribuem para o alto desempenho.",
    "Power words criam curiosidade, urgencia, valor ou apelo emocional.",
    "",
    "## Output Format (JSON array):",
    "[",
    '  { "title": "titulo original", "power_words": ["word1", "word2"], "hook_type": "curiosity/fear/value/authority/emotion" },',
    "  ...",
    "]",
    "",
    "Retorne APENAS o JSON array. Sem markdown, sem code fences.",
])

COMMENT_ANALYZER_SYSTEM = "\n".join([
    "# YouTube Comment Analyzer",
    "",
    "**IDIOMA OBRIGATORIO: PT-BR**",
    "",
    "Voce e um analista de audiencia expert. Analise os comentarios do canal do YouTube",
    "e extraia insights acionaveis.",
    "",
    "## Categorize em 3 grupos:",
    "1. **doing_well**: O que a audiencia ELOGIA e quer MAIS (min 5 items)",
    "2. **audience_dislikes**: O que a audiencia NAO gosta ou reclama (min 3 items)",
    "3. **audience_wants**: O que a audiencia PEDE ou sugere (min 5 items)",
    "",
    "## Output Format (JSON):",
    "{",
    '  "doing_well": ["insight 1 com exemplo de comentario", ...],',
    '  "audience_dislikes": ["insight 1 com exemplo", ...],',
    '  "audience_wants": ["insight 1 com exemplo", ...]',
    "}",
    "",
    "Retorne APENAS JSON valido. Sem markdown, sem code fences.",
])


def build_creative_agent_prompt(config):
    """Agente Criativo (Fase 3). Base FIEL ao buildCreativeAgentPrompt do youtube.js,
    porém o <output_structure> foi MAPEADO para o contrato do Content OS
    (top_competitor_videos / winning_patterns / hook_ideas / video_scripts / key_takeaway),
    e os roteiros ajustados para 'ate 50 segundos' em formato A/V (Áudio/Vídeo)."""
    niche = config.get("niche") or "nao especificado"
    broad_niche = config.get("broad_niche") or "nao especificado"
    channel_description = config.get("channel_description") or "nao especificado"
    return "\n".join([
        "**IDIOMA OBRIGATORIO: TODO O OUTPUT DEVE SER EM PORTUGUES BRASILEIRO (PT-BR).**",
        "",
        "<role>",
        "Voce e um diretor criativo ELITE de YouTube. Voce transforma dados de pesquisa em ideias de video virais.",
        "</role>",
        "",
        "<context>",
        "Nicho: " + niche,
        "Nicho amplo: " + broad_niche,
        "Descricao do canal: " + channel_description,
        "</context>",
        "",
        "<mission>",
        "Com base em TODOS os dados fornecidos (outliers, trends, buscas, comentarios da audiencia),",
        "gere um plano criativo completo para conteudo curto (ate 50 segundos).",
        "</mission>",
        "",
        "<output_structure>",
        "Retorne APENAS JSON valido:",
        "{",
        '  "winning_patterns": [',
        '    { "pattern_name": "Nome do padrao vencedor", "explanation": "Por que funciona, baseado nos dados" }',
        "  ],",
        '  "hook_ideas": [',
        '    { "hook": "Frase de gancho para os primeiros 3 segundos", "why_it_works": "Por que prende a atencao" }',
        "  ],",
        '  "video_scripts": [',
        "    {",
        '      "script_number": 1,',
        '      "hook_reference": "hook usado como base",',
        '      "estimated_duration": "ate 50s",',
        '      "script": "Roteiro completo em formato A/V. Use linhas ÁUDIO: (fala/narração) e VÍDEO: (o que aparece na tela). Ate 50 segundos."',
        "    }",
        "  ],",
        '  "key_takeaway": "Insight principal em 2-3 frases"',
        "}",
        "",
        "REQUISITOS:",
        "- winning_patterns: EXATAMENTE 3 padroes, extraidos dos dados reais (outliers/trends/comentarios).",
        "- hook_ideas: EXATAMENTE 10 ganchos, usando as power words identificadas na analise.",
        "- video_scripts: EXATAMENTE 10 roteiros, cada um em formato A/V (ÁUDIO:/VÍDEO:), com ate 50 SEGUNDOS de duracao.",
        "- Cada roteiro deve referenciar um hook e ser baseado em dados REAIS.",
        "- key_takeaway: 2-3 frases com o insight mais acionavel.",
        "",
        "Resposta = JSON valido puro (sem markdown, sem code fences).",
        "</output_structure>",
    ])


# ---------- Analisadores (Gemini) ----------
def analyze_titles_batch(gemini_key, videos, log_fn):
    if not videos:
        return []
    user_msg = "\n\n".join(
        f"--- VIDEO {i + 1} ---\nTitle: {v.get('title', '')}\nViews: {v.get('views', 0)}\nChannel: {v.get('channel', '')}"
        for i, v in enumerate(videos)
    )
    system_prompt = TITLE_ANALYZER_SYSTEM + f"\n\nVoce esta analisando {len(videos)} titulos de uma vez."
    try:
        raw = gemini_chat(gemini_key, system_prompt, user_msg, max_tokens=4096)
    except Exception as e:
        log_fn(f"analise de titulos falhou ({str(e)[:60]})")
        return [{"power_words": [], "hook_type": ""} for _ in videos]
    parsed = _parse_json_array(raw)
    if parsed is not None:
        return parsed
    log_fn("analise de titulos: JSON invalido, seguindo sem power words")
    return [{"power_words": [], "hook_type": ""} for _ in videos]


# ---------- Analisador de THUMBNAIL (fiel ao youtube.js) ----------
# Gemini "lê" a imagem (chamada leve) e depois analisa POR QUE gera clique.
GEMINI_READ_PROMPT = "\n".join([
    "Descreva esta thumbnail de YouTube em detalhes tecnicos:",
    "- Cores dominantes e contraste",
    "- Texto overlay (exatamente o que esta escrito)",
    "- Expressoes faciais e linguagem corporal (se houver pessoas)",
    "- Composicao e enquadramento",
    "- Icones, logos ou elementos graficos",
    "- Estilo geral (minimalista, colorido, clickbait, profissional, etc)",
    "",
    "Seja objetivo e detalhado. Max 200 palavras.",
])

THUMB_ANALYSIS_PROMPT = "\n".join([
    "**IDIOMA OBRIGATORIO: TODO O OUTPUT DEVE SER EM PORTUGUES BRASILEIRO (PT-BR).**",
    "",
    "# Overview",
    "Voce e um especialista em thumbnails de YouTube. Recebeu uma descricao detalhada de uma thumbnail.",
    "Voce tem 2 tarefas:",
    "",
    "## Tarefa 1: Extrair Power Words",
    "Identifique 1 a 3 power words/frases do TEXTO OVERLAY da thumbnail que contribuem para o alto desempenho.",
    "Se nao houver texto overlay, extraia power words do CONCEITO VISUAL (ex: \"antes/depois\", \"shock face\", \"numero grande\").",
    "",
    "## Tarefa 2: Analise da Thumbnail",
    "Analise POR QUE ela chama atencao e gera cliques cobrindo:",
    "- O que o viewer ve INSTANTANEAMENTE (primeiros 0.3 segundos)",
    "- A REACAO EMOCIONAL gerada (curiosidade, medo, desejo, surpresa, etc)",
    "- A PROMESSA IMPLICITA ou pergunta nao dita que a thumbnail cria",
    "- Como CORES, CONTRASTE e COMPOSICAO direcionam o olhar",
    "- Por que essa combinacao FAZ alguem CLICAR",
    "",
    "## Output Format (JSON):",
    '{ "power_words": ["word1", "word2"], "analysis": "paragrafo unico de 400-700 caracteres em PT-BR" }',
    "",
    "Retorne APENAS o JSON. Sem markdown, sem code fences.",
])


def analyze_thumbnail(gemini_key, thumbnail_url):
    """Baixa a thumb, Gemini descreve a imagem e depois analisa por que gera clique."""
    if not thumbnail_url:
        return {"analysis": "Thumbnail nao disponivel", "power_words": []}
    try:
        req = urllib.request.Request(thumbnail_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            img_bytes = resp.read()
            mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        if not img_bytes:
            return {"analysis": "Erro ao baixar thumbnail", "power_words": []}
        b64 = base64.b64encode(img_bytes).decode("ascii")
        # Step 1: Gemini LÊ a imagem (chamada com inlineData)
        parts = [
            {"text": GEMINI_READ_PROMPT},
            {"inlineData": {"mimeType": mime, "data": b64}},
        ]
        description = gemini_generate(gemini_key, parts, max_tokens=400)
        if not description:
            return {"analysis": "Gemini nao retornou descricao", "power_words": []}
        # Step 2: Gemini analisa a descricao (texto puro, JSON mode)
        raw = gemini_chat(gemini_key, THUMB_ANALYSIS_PROMPT,
                          "Descricao da thumbnail:\n\n" + description,
                          max_tokens=1024, json_mode=True)
        parsed = try_parse_json(raw)
        if isinstance(parsed, dict):
            return {"analysis": parsed.get("analysis", "") or "",
                    "power_words": parsed.get("power_words", []) or []}
        return {"analysis": (raw or "")[:700], "power_words": []}
    except Exception as e:
        return {"analysis": f"Erro na analise: {str(e)[:80]}", "power_words": []}


def analyze_thumbnails_batch(gemini_key, videos, log_fn, concurrency=3):
    """Analisa thumbnails em paralelo (fiel ao analyzeThumbnailsBatch do JS)."""
    if not videos:
        return []
    results = [{"analysis": "", "power_words": []} for _ in videos]
    log_fn(f"analisando {len(videos)} thumbnails (Gemini Vision)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(analyze_thumbnail, gemini_key, v.get("thumbnail_url", "")): i
                for i, v in enumerate(videos)}
        for fut in concurrent.futures.as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as e:
                results[i] = {"analysis": f"Erro: {str(e)[:60]}", "power_words": []}
    return results


def analyze_comments(gemini_key, comments, log_fn):
    empty = {"doing_well": [], "audience_dislikes": [], "audience_wants": []}
    if not comments:
        return empty
    comment_texts = "\n".join(
        f"Comentario {i + 1} ({c.get('likes') or c.get('voteCount') or 0} likes): "
        f"{(c.get('text') or c.get('comment') or c.get('content') or '')[:300]}"
        for i, c in enumerate(comments[:200])
    )
    try:
        raw = gemini_chat(gemini_key, COMMENT_ANALYZER_SYSTEM, comment_texts, max_tokens=4096)
    except Exception as e:
        log_fn(f"analise de comentarios falhou ({str(e)[:60]})")
        return empty
    parsed = try_parse_json(raw)
    if isinstance(parsed, dict):
        return {
            "doing_well": parsed.get("doing_well", []),
            "audience_dislikes": parsed.get("audience_dislikes", []),
            "audience_wants": parsed.get("audience_wants", []),
        }
    return empty


# ---------- Comentarios dos CONCORRENTES: pros x contras por canal ----------
COMPETITOR_COMMENT_SYSTEM = "\n".join([
    "# YouTube Competitor Comment Analyzer",
    "",
    "**IDIOMA OBRIGATORIO: PT-BR**",
    "",
    "Voce e um analista de audiencia expert. Analise os comentarios dos videos de UM CANAL",
    "CONCORRENTE e extraia PROS e CONTRAS do ponto de vista da audiencia desse canal.",
    "",
    "## Categorize em 2 grupos:",
    "1. **pros**: o que a audiencia ELOGIA/AMA nesse canal (minimo 3 items, cada um com",
    "   exemplo real de comentario que sustenta o ponto)",
    "2. **contras**: o que a audiencia RECLAMA ou CRITICA nesse canal (minimo 3 items, cada",
    "   um com exemplo real de comentario que sustenta o ponto)",
    "",
    "## Output Format (JSON):",
    "{",
    '  "pros": ["ponto positivo 1 com exemplo de comentario", ...],',
    '  "contras": ["ponto negativo 1 com exemplo de comentario", ...]',
    "}",
    "",
    "Se nao houver comentarios suficientes pra sustentar um ponto, NAO invente — retorne",
    "menos items em vez de fabricar.",
    "Retorne APENAS JSON valido. Sem markdown, sem code fences.",
])


def analyze_competitor_comments(gemini_key, channel_name, comments, log_fn):
    """Analisa comentarios dos videos de UM concorrente e extrai pros/contras
    (o que a audiencia dele elogia vs. reclama). Espelha analyze_comments(),
    mas com 2 categorias focadas em avaliar o canal concorrente, nao o proprio."""
    empty = {"pros": [], "contras": []}
    if not comments:
        return empty
    comment_texts = "\n".join(
        f"Comentario {i + 1} ({c.get('likes') or c.get('voteCount') or 0} likes): "
        f"{(c.get('text') or c.get('comment') or c.get('content') or '')[:300]}"
        for i, c in enumerate(comments[:150])
    )
    try:
        raw = gemini_chat(
            gemini_key, COMPETITOR_COMMENT_SYSTEM,
            f"Canal analisado: {channel_name}\n\n{comment_texts}", max_tokens=3072,
        )
    except Exception as e:
        log_fn(f"pros/contras de @{channel_name} falhou ({str(e)[:60]})")
        return empty
    parsed = try_parse_json(raw)
    if isinstance(parsed, dict):
        return {"pros": parsed.get("pros", []) or [], "contras": parsed.get("contras", []) or []}
    return empty


# ---------- FASE 1: Niche Outliers ----------
def run_phase1(competitor_channels, creds, log_fn):
    apify = creds["APIFY_TOKEN"]
    gemini = creds["GEMINI_API_KEY"]
    log_fn("Fase 1: coletando canais concorrentes...")

    channel_results = []
    all_comp_videos = []  # normalizados, pra stats
    for ci, ch_url in enumerate(competitor_channels):
        ch_id = extract_channel_id(ch_url)
        try:
            log_fn(f"scraping canal {ci + 1}/{len(competitor_channels)}: {ch_id}...")
            channel_videos = scrape_channel(apify, ch_url, 30)
        except Exception as e:
            log_fn(f"falha ao scrape canal {ch_id}: {str(e)[:80]}")
            continue
        if not channel_videos:
            log_fn(f"canal {ch_id}: nenhum video encontrado.")
            continue

        # top 10 por views (o filtro de 6 meses do JS depende de datas confiáveis;
        # mantemos o corte por views que é o sinal principal do detectOutliers)
        channel_videos.sort(key=_views_of, reverse=True)
        top10 = [normalize_video(v) for v in channel_videos[:10]]
        all_comp_videos.extend(top10)

        # Comentarios dos top videos DESTE concorrente -> pros/contras do canal
        # (visao da audiencia dele: o que amam vs. o que reclamam)
        pros_contras = {"pros": [], "contras": []}
        top_urls = [v["url"] for v in top10[:5] if v.get("url")]
        if top_urls:
            try:
                log_fn(f"coletando comentarios de @{ch_id} (pros/contras)...")
                comp_comments = scrape_comments(apify, top_urls, 100)
                log_fn(f"@{ch_id}: {len(comp_comments or [])} comentarios coletados")
                if comp_comments:
                    pros_contras = analyze_competitor_comments(gemini, ch_id, comp_comments, log_fn)
            except Exception as e:
                log_fn(f"comentarios de @{ch_id} falharam: {str(e)[:80]}")

        channel_results.append({
            "channel_name": ch_id, "channel_url": ch_url, "videos": top10,
            "pros": pros_contras.get("pros", []), "contras": pros_contras.get("contras", []),
        })
        log_fn(f"canal {ch_id}: {len(top10)} videos coletados")

    # Achata todos os vídeos e detecta outliers (>= 3x a média) do conjunto inteiro
    outliers = detect_outliers(all_comp_videos)
    if not outliers:
        # fallback: se ninguém bate 3x a média, usa os top por views
        outliers = sorted(all_comp_videos, key=lambda v: v.get("views", 0), reverse=True)[:10]

    # Analisa power words dos títulos dos outliers
    title_results = analyze_titles_batch(gemini, outliers, log_fn)
    for i, v in enumerate(outliers):
        tr = title_results[i] if i < len(title_results) else {}
        v["power_words"] = (tr or {}).get("power_words", []) or []
        v["hook_type"] = (tr or {}).get("hook_type", "") or ""

    # Analisa as THUMBNAILS dos outliers (Gemini Vision) — análise própria do YouTube
    # IMPORTANTE: analisamos os vídeos que VIRAM CARD (top por views do conjunto),
    # não só os outliers — senão só 1 card teria análise quando o filtro 3x pega 1.
    card_videos = sorted(all_comp_videos, key=_views_of, reverse=True)[:5]
    # garante que os outliers também entrem (dedup por url)
    seen = {id(v) for v in card_videos}
    to_analyze = card_videos + [v for v in outliers if id(v) not in seen]
    # analisa títulos dos cards também (outliers já feitos acima; reforça os demais)
    card_titles = analyze_titles_batch(gemini, card_videos, log_fn)
    for i, v in enumerate(card_videos):
        if not v.get("power_words"):
            tr = card_titles[i] if i < len(card_titles) else {}
            v["power_words"] = (tr or {}).get("power_words", []) or []
            v["hook_type"] = (tr or {}).get("hook_type", "") or ""
    thumb_results = analyze_thumbnails_batch(gemini, to_analyze, log_fn)
    for i, v in enumerate(to_analyze):
        tr = thumb_results[i] if i < len(thumb_results) else {}
        v["thumbnail_analysis"] = (tr or {}).get("analysis", "") or ""
        tpw = (tr or {}).get("power_words", []) or []
        if tpw:
            v["power_words"] = list(dict.fromkeys((v.get("power_words") or []) + tpw))

    return {"channels": channel_results, "outliers": outliers}, all_comp_videos


# ---------- FASE 2: Broad/Niche Search ----------
def run_phase2(niche, broad_niche, creds, log_fn):
    apify = creds["APIFY_TOKEN"]
    gemini = creds["GEMINI_API_KEY"]

    log_fn("Fase 2: buscando top 5 semanal do nicho amplo...")
    broad_trends = []
    try:
        broad_raw = scrape_search(apify, broad_niche or niche, 5, "week")
        broad_trends = sorted(
            [normalize_video(v) for v in (broad_raw or [])],
            key=lambda v: v["views"], reverse=True,
        )[:5]
        log_fn(f"nicho amplo semanal: {len(broad_trends)} videos")
    except Exception as e:
        log_fn(f"nicho amplo falhou: {str(e)[:80]}")

    log_fn("buscando top 5 diario do nicho especifico...")
    niche_trends = []
    try:
        niche_raw = scrape_search(apify, niche, 5, "today")
        niche_trends = sorted(
            [normalize_video(v) for v in (niche_raw or [])],
            key=lambda v: v["views"], reverse=True,
        )[:5]
        log_fn(f"nicho especifico diario: {len(niche_trends)} videos")
    except Exception as e:
        log_fn(f"nicho especifico falhou: {str(e)[:80]}")

    all_search = broad_trends + niche_trends
    if all_search:
        title_results = analyze_titles_batch(gemini, all_search, log_fn)
        for i, v in enumerate(all_search):
            tr = title_results[i] if i < len(title_results) else {}
            v["power_words"] = (tr or {}).get("power_words", []) or []
            v["hook_type"] = (tr or {}).get("hook_type", "") or ""

    return {"broad_niche_trends": broad_trends, "niche_daily": niche_trends}


# ---------- FASE 3: Comments + Creative Agent ----------
def run_phase3(me_channel, niche, broad_niche, phase1_result, phase2_result, creds, log_fn):
    apify = creds["APIFY_TOKEN"]
    gemini = creds["GEMINI_API_KEY"]

    log_fn("Fase 3: scraping seu canal...")
    my_videos = []
    try:
        my_raw = scrape_channel(apify, me_channel, 10)
        my_videos = [normalize_video(v) for v in (my_raw or [])]
        log_fn(f"seu canal: {len(my_videos)} videos")
    except Exception as e:
        log_fn(f"falha ao scrape seu canal: {str(e)[:80]}")

    # Comentários dos meus top 5 vídeos
    comment_insights = {"doing_well": [], "audience_dislikes": [], "audience_wants": []}
    if my_videos:
        top_urls = [
            v["url"] for v in sorted(my_videos, key=lambda v: v["views"], reverse=True)[:5]
            if v.get("url")
        ]
        if top_urls:
            try:
                log_fn("scraping comentarios dos seus top videos...")
                raw_comments = scrape_comments(apify, top_urls, 100)
                log_fn(f"comentarios: {len(raw_comments or [])} coletados")
                if raw_comments:
                    log_fn("analisando comentarios...")
                    comment_insights = analyze_comments(gemini, raw_comments, log_fn)
            except Exception as e:
                log_fn(f"comentarios falharam: {str(e)[:80]}")

    # ── Agente Criativo: sintetiza tudo no contrato do Content OS ──
    log_fn("gerando plano criativo (hooks + roteiros)...")
    creative_system = build_creative_agent_prompt({
        "niche": niche,
        "broad_niche": broad_niche,
        "channel_description": f"Canal de {niche} em portugues brasileiro.",
    })

    outliers = (phase1_result or {}).get("outliers", [])
    broad_trends = (phase2_result or {}).get("broad_niche_trends", [])
    niche_trends = (phase2_result or {}).get("niche_daily", [])

    creative_user = "\n".join([
        "# OUTLIER VIDEOS DOS CONCORRENTES:",
        json.dumps([{
            "title": v.get("title"), "channel": v.get("channel"), "views": v.get("views"),
            "power_words": v.get("power_words", []),
            "description": (v.get("description") or "")[:200],
        } for v in outliers], ensure_ascii=False, indent=2),
        "",
        "# TRENDS DO NICHO AMPLO:",
        json.dumps([{"title": v.get("title"), "views": v.get("views"), "power_words": v.get("power_words", [])}
                    for v in broad_trends], ensure_ascii=False, indent=2),
        "",
        "# TRENDS DO NICHO ESPECIFICO:",
        json.dumps([{"title": v.get("title"), "views": v.get("views"), "power_words": v.get("power_words", [])}
                    for v in niche_trends], ensure_ascii=False, indent=2),
        "",
        "# INSIGHTS DOS COMENTARIOS DA AUDIENCIA:",
        json.dumps(comment_insights, ensure_ascii=False, indent=2),
        "",
        "# VIDEOS DO MEU CANAL:",
        json.dumps([{"title": v.get("title"), "views": v.get("views"), "url": v.get("url")}
                    for v in my_videos[:10]], ensure_ascii=False, indent=2),
    ])

    creative_result = None
    for attempt in range(1, 3):
        raw = gemini_chat(gemini, creative_system, creative_user, max_tokens=16384)
        creative_result = try_parse_json(raw)
        if creative_result and creative_result.get("video_scripts"):
            log_fn(f"plano criativo OK (tentativa {attempt}): "
                   f"{len(creative_result.get('video_scripts', []))} roteiros")
            break
        creative_result = None
    if not creative_result:
        creative_result = {"winning_patterns": [], "hook_ideas": [], "video_scripts": [], "key_takeaway": ""}

    return comment_insights, my_videos, creative_result


# ---------- Orquestrador: contrato do Content OS ----------
def _build_top_competitor_videos(outliers):
    """Mapeia os outliers (Fase 1) -> top_competitor_videos do dashboard.
    rank, hook(=title), url, views, posted_date, creator, why_it_worked."""
    top = []
    for i, v in enumerate(sorted(outliers, key=lambda v: v.get("views", 0), reverse=True)):
        pw = v.get("power_words", [])
        why = ""
        if pw:
            why = "Power words: " + ", ".join(pw[:5]) + "."
        if v.get("hook_type"):
            why = (why + " ").strip() + f" Gatilho: {v['hook_type']}."
        top.append({
            "rank": i + 1,
            "hook": v.get("title", ""),
            "title": v.get("title", ""),
            "url": v.get("url", ""),
            "views": v.get("views", 0) or 0,
            "posted_date": v.get("date", ""),
            "creator": v.get("channel", ""),
            "why_it_worked": why or "Outlier: views bem acima da média do nicho.",
            "comments": v.get("comments", 0) or 0,
            "thumbnail_url": v.get("thumbnail_url", ""),
            "thumbnail_analysis": v.get("thumbnail_analysis", ""),
            "power_words": v.get("power_words", []) or [],
            "hook_type": v.get("hook_type", ""),
        })
    return top


def run_youtube(me_channel, competitor_channels, creds, log_fn=None):
    """Ponto de entrada do módulo YouTube.

    Args:
        me_channel: URL (ou handle) do canal do usuário.
        competitor_channels: lista de URLs de canais concorrentes.
        creds: dict com 'APIFY_TOKEN' e 'GEMINI_API_KEY'.
        log_fn: callback de log (msg:str). Default: print.

    Returns:
        (result_dict, my_videos, comp_videos)
          result_dict — contrato do dashboard:
            top_competitor_videos, winning_patterns(3), hook_ideas(10),
            video_scripts(10, A/V até 50s), key_takeaway(str),
            + extras: outliers, comment_insights, broad_niche_trends, niche_daily
          my_videos, comp_videos — listas normalizadas (pra stats).
    """
    log_fn = log_fn or (lambda m: print(f"   📍 {m}", flush=True))
    if not creds.get("APIFY_TOKEN") or not creds.get("GEMINI_API_KEY"):
        raise RuntimeError("Faltam APIFY_TOKEN e/ou GEMINI_API_KEY nas credenciais.")

    niche = DEFAULT_NICHE
    broad_niche = DEFAULT_BROAD_NICHE

    # Fase 1 — outliers dos concorrentes
    phase1, comp_videos = run_phase1(competitor_channels, creds, log_fn)

    # Fase 2 — buscas broad/niche
    phase2 = run_phase2(niche, broad_niche, creds, log_fn)

    # Fase 3 — comentários + agente criativo
    comment_insights, my_videos, creative = run_phase3(
        me_channel, niche, broad_niche, phase1, phase2, creds, log_fn
    )

    # Monta o contrato do dashboard
    result = {
        "top_competitor_videos": _build_top_competitor_videos(phase1.get("outliers", [])),
        "winning_patterns": creative.get("winning_patterns", [])[:3],
        "hook_ideas": creative.get("hook_ideas", [])[:10],
        "video_scripts": creative.get("video_scripts", [])[:10],
        "key_takeaway": creative.get("key_takeaway", "") or "",
        # extras específicos do YouTube
        "outliers": phase1.get("outliers", []),
        "comment_insights": comment_insights,
        "broad_niche_trends": phase2.get("broad_niche_trends", []),
        "niche_daily": phase2.get("niche_daily", []),
        # pros/contras por canal concorrente (visao da audiencia deles)
        "competitor_channels": phase1.get("channels", []),
    }
    return result, my_videos, comp_videos
