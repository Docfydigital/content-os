#!/usr/bin/env python3
"""
Content OS — Módulo TikTok (porte do pipeline TikTok OS do Creator AI).

Espelha o net do Instagram (pipeline.py), trocando:
  - Actor Apify: GdWCkxBtKWOsKjdch (TikTok scraper)
  - Body do scrape (campos específicos do TikTok)
  - normalizeTikTok (mapeamento de campos)
  - Prompts próprios de TikTok (análise + roteiros), PT-BR

Reusa (mesmo estilo urllib puro, sem dependências externas):
  from pipeline import http_post_json, gemini_chat, transcribe_video,
                       try_parse_json, sort_by_views, filter_by_days

Contrato de saída (pra integrar ao pipeline.py):
  run_tiktok(me, competitors, creds, max_transcribe, log_fn)
      -> (result_dict, my_reels, comp_reels)

  creds       = dict com 'APIFY_TOKEN' e 'GEMINI_API_KEY'
  log_fn      = função de log(msg)  (pode ser print)
  result_dict = top_competitor_videos(5), winning_patterns(3),
                hook_ideas(10), video_scripts(10), key_takeaway(str),
                competitor_gaps, quick_wins
  my_reels / comp_reels = reels normalizados (pra stats de comparação)

Roteiros do Content OS = ATÉ 50 SEGUNDOS (original era 30-60s).
Modelo: gemini-3.5-flash-lite (mesmo do pipeline.py).
"""
import json
import time
import urllib.error

# Reusa helpers do pipeline Instagram (mesmo diretório, urllib puro)
from pipeline import (
    http_post_json,
    gemini_chat,
    transcribe_video,
    try_parse_json,
    sort_by_views,
    sort_by_engagement,
    filter_by_days,
)

# ---------- Config TikTok (igual ao tiktok.js) ----------
TIKTOK_ACTOR_ID = "GdWCkxBtKWOsKjdch"
APIFY_BASE = "https://api.apify.com/v2"
TIKTOK_TIMEOUT = 300  # scrape do TikTok é mais lento (AbortSignal.timeout(300000) no JS)
DAYS_WINDOW = 90      # janela de recência (meu e concorrentes)
MY_TOP = 10
COMP_TOP = 10


# ---------- STEP 1: Apify (scrape + normalização) ----------
def normalize_tiktok(video):
    """Mapeia o objeto cru do Apify (TikTok) pro formato interno (== normalizeTikTok)."""
    author = video.get("authorMeta") or {}
    vmeta = video.get("videoMeta") or {}
    media = video.get("mediaUrls") or []
    return {
        "url": video.get("webVideoUrl") or "",
        "videoUrl": media[0] if media else "",
        "displayUrl": vmeta.get("coverUrl") or "",
        "caption": (video.get("text") or "")[:2000],
        "ownerUsername": author.get("name") or "",
        "videoPlayCount": video.get("playCount") or 0,
        "likesCount": video.get("diggCount") or 0,
        "commentsCount": video.get("commentCount") or 0,
        "timestamp": video.get("createTimeISO") or "",
    }


def scrape_tiktoks(apify_token, username, results_per_page=20, oldest_post_date="180 days"):
    """POST run-sync-get-dataset-items com o body exato do TikTok scraper."""
    username = normalize_username(username)
    url = f"{APIFY_BASE}/acts/{TIKTOK_ACTOR_ID}/run-sync-get-dataset-items?token={apify_token}"
    body = {
        "excludePinnedPosts": False,
        "oldestPostDateUnified": oldest_post_date,
        "profiles": [username],
        "proxyCountryCode": "None",
        "resultsPerPage": results_per_page,
        "scrapeRelatedVideos": False,
        "shouldDownloadAvatars": False,
        "shouldDownloadCovers": True,
        "shouldDownloadMusicCovers": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadVideos": True,
    }
    try:
        status, data = http_post_json(url, body, timeout=TIKTOK_TIMEOUT)
        if isinstance(data, list):
            return data
        return []
    except urllib.error.HTTPError as e:
        text = e.read().decode()[:200]
        if e.code == 402:
            raise RuntimeError("Apify: saldo esgotado. Recarregue os creditos em apify.com.")
        if e.code == 401:
            raise RuntimeError("Apify: key invalida ou expirada.")
        raise RuntimeError(f"Apify TikTok error ({e.code}): {text}")


def normalize_username(input_str):
    """Aceita @user ou URL tiktok.com/@user (== normalizeUsername do JS)."""
    import re
    s = str(input_str or "")
    m = re.search(r"tiktok\.com/@?([^/?]+)", s)
    if m:
        return m.group(1)
    return s.lstrip("@")


def build_reel_summary_tiktok(reels):
    """Compacta reels pro prompt (== formatForPrompt do tiktok.js, inclui hook/powerWords)."""
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
            "hook": r.get("hook", ""),
            "powerWords": r.get("powerWords", []),
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


# ---------- Prompts TikTok (fiéis ao tiktok.js, PT-BR) ----------
def build_tiktok_analysis_prompt(username):
    return f"""**IDIOMA OBRIGATORIO: TODO O OUTPUT DEVE SER EM PORTUGUES BRASILEIRO (PT-BR).**

<role>
Voce e um estrategista de conteudo ELITE especializado em TikTok.
</role>

<mission>
Criar a PARTE 1 do relatorio estrategico: analise de performance, padroes vencedores, hooks e gaps.
</mission>

<analysis_framework>
## ETAPA 1: SELECIONAR TOP 5 TIKTOKS DOS CONCORRENTES
## ETAPA 2: ANALISE PROFUNDA (4-5 SENTENCAS POR VIDEO)
**CRITICO: Use DADOS NUMERICOS REAIS do JSON (views, likes, engagement rate, datas). Compare SEMPRE com {username}.**
- Qual o gatilho psicologico primario?
- Qual a mecanica de execucao que faz funcionar?
- O que 99% das pessoas nao percebem sobre por que isso viralizou?
- Compare: quantas views vs media de {username} (ex: "3.5x mais views que {username}")
## ETAPA 3: IDENTIFICAR 3 WINNING PATTERNS
**FOCO: Identifique padroes de FORMATO, ESTRUTURA e MECANICA de conteudo (ex: formato lista, storytelling, antes/depois, tutorial rapido). NAO identifique padroes de TEMA ou ASSUNTO especifico dos videos.**
Analise AMBOS os datasets. Por que funciona pra {username}.
## ETAPA 4: CRIAR 10 HOOK IDEAS (primeiros 1-2 segundos criticos no TikTok)
- Use emojis estrategicos quando apropriado (🚨, ✅, ❌, 🔥)
- Inclua NUMEROS ESPECIFICOS e LOCALIZACAO quando relevante pro nicho
## ETAPA 5: COMPETITOR GAPS (3 categorias: inexplorado, moderado, saturado)

## ETAPA 6: QUICK WINS (top 3)
**CRITICO: Cada quick win DEVE incluir:**
- Tempo de implementacao (ex: "30 minutos", "1 video")
- ROI esperado com numeros (ex: "CTR +40%", "3-5x mais views", "+60% alcance")
- Referencia ao dado real que sustenta a recomendacao

## ETAPA 7: KEY TAKEAWAY
</analysis_framework>

<output_structure>
Retorne APENAS JSON valido:
{{
  "performance_overview": {{ "avg_views": 0, "top_pattern": "(padrao de FORMATO/ESTRUTURA, nao de tema)", "hook_rate_insight": "(compare engagement rate de {username} vs concorrentes com numeros reais)", "best_format": "" }},
  "top_competitor_videos": [{{ "rank": 1, "hook": "", "url": "", "views": 0, "posted_date": "YYYY-MM-DD", "creator": "", "why_it_worked": "" }}],
  "winning_patterns": [{{ "pattern_name": "", "explanation": "" }}],
  "hook_ideas": [{{ "hook": "", "why_it_works": "" }}],
  "competitor_gaps": {{ "unexplored": [], "moderate": [], "saturated": [] }},
  "quick_wins": [{{ "rank": 1, "why_quick_win": "(inclua: tempo de implementacao + ROI esperado com numeros + dado real que sustenta)" }}],
  "key_takeaway": ""
}}
REQUISITOS CRITICOS:
- top_competitor_videos: exatamente 5 objetos
- winning_patterns: exatamente 3 objetos
- hook_ideas: exatamente 10 objetos
- competitor_gaps: 3 categorias com 2-3 items cada
- quick_wins: exatamente 3 objetos
- rank, views = numeros
- NAO use aspas duplas dentro de strings — use aspas simples
- NAO invente dados — use APENAS valores exatos do JSON de input
- NUNCA invente perfis, @usernames, URLs ou videos que nao existam nos dados fornecidos
- Se um dado nao existe no JSON, NAO crie um valor ficticio — use apenas o que foi fornecido
- Resposta = JSON valido puro (sem markdown, sem code fences, sem texto extra)
</output_structure>

<language_rules>
OBRIGATORIO PT-BR. MANTER ORIGINAL: transcricoes, hooks citados, @usernames, URLs.
</language_rules>"""


def build_tiktok_scripts_prompt(username):
    return f"""**IDIOMA OBRIGATORIO: TODO O OUTPUT DEVE SER EM PORTUGUES BRASILEIRO (PT-BR).**

<role>
Voce e um roteirista de conteudo ELITE especializado em TikTok.
</role>

<mission>
Criar a PARTE 2 do relatorio estrategico: 10 roteiros completos prontos pra gravar.
Voce recebera a analise da PARTE 1 (hooks, patterns, gaps) como contexto.
</mission>

<script_framework>
## CRIAR 10 ROTEIROS COMPLETOS (ate 50 segundos, formato vertical, ritmo rapido)
- Adaptado ao estilo de {username}
- Cada roteiro deve usar um dos hooks fornecidos na analise
- Formato A/V otimizado para TikTok
## FIRST FRAME BLUEPRINT (POR ROTEIRO)
## EDITING RECIPE (trends de edicao do TikTok)
## PERFORMANCE SCORE (POR ROTEIRO)
</script_framework>

<output_structure>
Retorne APENAS JSON valido:
{{
  "video_scripts": [{{ "script_number": 1, "hook_reference": "", "estimated_duration": "ate 50 segundos", "script": "", "first_frame_blueprint": "", "editing_recipe": "", "performance_score": 8.5, "score_justification": "" }}]
}}
REQUISITOS CRITICOS:
- video_scripts: EXATAMENTE 10 objetos — nem mais, nem menos (TODOS EM PORTUGUES BR)
- script_number e performance_score = numeros
- Scripts com \\n (escaped) pra quebras de linha — NAO use quebras de linha reais dentro de strings
- NAO use aspas duplas dentro de strings — use aspas simples
- Resposta = JSON valido puro (sem markdown, sem code fences, sem texto extra)
</output_structure>

<language_rules>
OBRIGATORIO PT-BR. MANTER ORIGINAL: hooks citados, @usernames.
</language_rules>"""


# ---------- Pipeline TikTok ----------
def _select_top(reels_norm, days, top):
    """Top N pela JUNÇÃO views+likes+comentarios nos últimos `days`;
    fallback all-time se <5 recentes."""
    recent = sort_by_engagement(filter_by_days(reels_norm, days))[:top]
    if len(recent) < 5:
        recent = sort_by_engagement(reels_norm)[:top]
    return recent


def run_tiktok(me, competitors, creds, max_transcribe, log_fn=None):
    """
    Executa o pipeline TikTok e devolve (result_dict, my_reels, comp_reels).

    me            : @ do usuario (com ou sem @)
    competitors   : lista de @s concorrentes
    creds         : {'APIFY_TOKEN': ..., 'GEMINI_API_KEY': ...}
    max_transcribe: limite de videos a transcrever (custo/tempo)
    log_fn        : callable(msg) para log (default: print)
    """
    log = log_fn or (lambda m: print(m, flush=True))
    apify = creds.get("APIFY_TOKEN")
    gemini = creds.get("GEMINI_API_KEY")
    if not apify or not gemini:
        raise RuntimeError("faltam APIFY_TOKEN e/ou GEMINI_API_KEY nas creds")

    me = normalize_username(me)
    competitors = [normalize_username(c) for c in competitors if str(c).strip()]

    # STEP 1: meu perfil — top 10 (90 dias, fallback all-time)
    log(f"Coletando TikToks de @{me}...")
    my_raw = scrape_tiktoks(apify, me, results_per_page=30, oldest_post_date="180 days")
    my_norm = [normalize_tiktok(v) for v in my_raw]
    my_reels = _select_top(my_norm, DAYS_WINDOW, MY_TOP)
    log(f"@{me}: {len(my_reels)} TikToks selecionados")

    # STEP 1b: concorrentes — top 10 (90 dias, fallback all-time) por perfil
    comp_reels = []
    for c in competitors:
        log(f"Coletando TikToks de @{c}...")
        try:
            raw = scrape_tiktoks(apify, c, results_per_page=15, oldest_post_date="90 days")
        except RuntimeError as e:
            log(f"@{c} falhou: {str(e)[:80]}")
            continue
        comp_norm = [normalize_tiktok(v) for v in raw]
        filt = _select_top(comp_norm, DAYS_WINDOW, COMP_TOP)
        comp_reels.extend(filt)
        log(f"@{c}: {len(filt)} TikToks")

    # STEP 3: transcricao (limitada por max_transcribe)
    my_quota = (max_transcribe + 1) // 2
    comp_quota = max_transcribe // 2

    def transcribe_pool(pool, quota, label):
        successes = 0
        attempts = 0
        for r in pool:
            if successes >= quota:
                break
            vurl = r.get("videoUrl")
            if not vurl:
                continue
            if attempts > 0:
                time.sleep(5)
            attempts += 1
            transcript = transcribe_video(gemini, vurl)
            r["transcript"] = transcript
            if transcript:
                successes += 1
                log(f"  {label}: {successes}/{quota} transcritos ({len(transcript)} chars)")
            else:
                log(f"  {label}: vídeo incompatível/indisponível; tentando o próximo campeão")
        return successes

    log(f"Transcrevendo amostra equilibrada: {my_quota} seus + {comp_quota} do concorrente...")
    my_ok = transcribe_pool(my_reels, my_quota, "meu perfil")
    comp_ok = transcribe_pool(comp_reels, comp_quota, "concorrente")
    log(f"Amostra transcrita: {my_ok} seus + {comp_ok} do concorrente")

    # Contexto compartilhado pros dois prompts
    videos_context = (
        f"# MY TIKTOKS:\n{build_reel_summary_tiktok(my_reels)}\n\n"
        f"# COMPETITOR TIKTOKS:\n{build_reel_summary_tiktok(sort_by_views(comp_reels))}"
    )

    # STEP 5a: analise (patterns, hooks, gaps, quick wins) — 2 tentativas
    log("Gerando analise TikTok (Gemini)...")
    analysis_system = build_tiktok_analysis_prompt(me)
    analysis = None
    for attempt in range(1, 3):
        raw = gemini_chat(gemini, analysis_system, videos_context, max_tokens=8192, json_mode=True)
        analysis = try_parse_json(raw)
        if analysis and analysis.get("hook_ideas"):
            log(f"Analise parseada OK (tentativa {attempt})")
            break
        analysis = None
    if not analysis:
        raise RuntimeError("Falha ao gerar analise TikTok: Gemini nao retornou JSON valido apos 2 tentativas.")

    # STEP 5b: somente roteiros; calendario e montado deterministicamente no pipeline.py
    log("Gerando 10 roteiros TikTok (Gemini)...")
    scripts_system = build_tiktok_scripts_prompt(me)
    scripts_user = f"# ANALYSIS CONTEXT (from part 1):\n{json.dumps(analysis, ensure_ascii=False, indent=2)}\n\n{videos_context}"
    scripts = None
    for attempt in range(1, 3):
        raw = gemini_chat(gemini, scripts_system, scripts_user, max_tokens=16384, json_mode=True)
        scripts = try_parse_json(raw)
        if scripts and scripts.get("video_scripts"):
            log(f"Roteiros parseados OK (tentativa {attempt}): {len(scripts.get('video_scripts', []))} roteiros")
            break
        scripts = None
    if not scripts:
        raise RuntimeError("Falha ao gerar roteiros TikTok: Gemini nao retornou JSON valido apos 2 tentativas.")

    # Merge (== strategy = {...analysis, ...scripts} do JS)
    result = {**analysis, **scripts}
    return result, my_reels, comp_reels
