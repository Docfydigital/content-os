# Pipelines por rede (TikTok + YouTube) — spec fiel ao Creator AI

Fonte: código real do Creator AI (`~/creatorai-v2/worker/pipelines/{tiktok,youtube}.js`),
lido via bridge do Mac. O Content OS replica esses fluxos em Python (`net_tiktok.py`,
`net_youtube.py`) integrados ao `pipeline.py` por `--network`.

## Actor IDs REAIS (corrigem a tabela genérica da SKILL.md)

| Rede | Actor(s) Apify (valor exato usado no Creator AI) | Endpoint |
|---|---|---|
| Instagram | `xMc5Ga1oCONPmWJIa` | `run-sync-get-dataset-items` |
| TikTok | `GdWCkxBtKWOsKjdch` | `run-sync-get-dataset-items` |
| YouTube | `streamers~youtube-scraper` + `streamers~youtube-comments-scraper` | `run-sync-get-dataset-items` |

Sempre confira o saldo/acesso da conta antes de rodar. `run-sync-get-dataset-items` volta **HTTP 201** no sucesso.

## TikTok — mesmo fluxo do Instagram, muda scraper + mapeamento

- **Input do scrape** (body): `{excludePinnedPosts:false, oldestPostDateUnified:'180 days'(meu)|'90 days'(concorrente), profiles:[username], proxyCountryCode:'None', resultsPerPage:N, scrapeRelatedVideos:false, shouldDownloadAvatars:false, shouldDownloadCovers:true, shouldDownloadMusicCovers:false, shouldDownloadSlideshowImages:false, shouldDownloadSubtitles:false, shouldDownloadVideos:true}`
- **normalizeTikTok** (campos → interno): `url=webVideoUrl`, `videoUrl=mediaUrls[0]`, `displayUrl=videoMeta.coverUrl`, `caption=text[:2000]`, `ownerUsername=authorMeta.name`, `videoPlayCount=playCount`, `likesCount=diggCount`, `commentsCount=commentCount`, `timestamp=createTimeISO`
- **Seleção**: meu = top 10 por views, últimos 90 dias (fallback all-time se <5); concorrente = top 10, 90 dias (fallback all-time).
- Resto idêntico ao Instagram: transcreve vídeo (Gemini) → hook batch → análise (call 1) → roteiros+calendário (call 2). Mesmo modelo `gemini-3.5-flash-lite`.

## YouTube — 3 FASES, NÃO transcreve vídeo

YouTube é o complexo. Trabalha com **títulos + descrições + comentários**, não com transcrição de vídeo.
- **Fase 1 — Niche Outliers**: `scrapeChannel` (input `{startUrls:[{url}], maxResults:30, sortBy:'date'}`), depois `detectOutliers` = vídeos com views ≥ **3× a média** do conjunto, top 10 desc.
- **Fase 2 — Broad/Niche Search**: `scrapeSearch` (input `{searchKeywords, maxResults:5, sortBy:'relevance', dateFilter?}`).
- **Fase 3 — Comments + Creative Agent**: `scrapeComments` (input `{startUrls:[{url}], maxComments:100, sortBy:'top'}`) + `TITLE_ANALYZER_SYSTEM` (extrai power words dos títulos) + agente criativo que gera roteiros.
- **normalizeVideo**: `title`, `url(=url||videoUrl)`, `views(=viewCount||views)`, `likes`, `comments(=commentsCount||numberOfComments)`, `thumbnail_url`, `channel(=channelName||channelTitle)`, `date(=date||uploadDate)`, `description[:500]`.
- **Mapeamento pro contrato da dashboard**: outliers → `top_competitor_videos`; roteiros criativos → `video_scripts`; mais `winning_patterns`(3), `hook_ideas`(10), `key_takeaway`. Campos extras do YouTube (outliers, comment_insights) podem virar chaves adicionais.

## Modelo por etapa (preferência da Reilla)

- **Transcrição** → `gemini-3.5-flash-lite` (é 80%+ das chamadas por causa do vídeo; barato, não precisa de raciocínio). Fica.
- **Roteiros** → subir pra modelo mais forte. Ela pediu isso explicitamente. Opções que a key dela acessa: `gemini-3-pro-preview` (topo, mas `-preview` pode mudar/descontinuar), `gemini-2.5-pro` (Pro estável de produção — melhor pra entregar ao aluno), ou `gemini-3.5-flash` (equilíbrio).
- **Split inteligente**: etapa cara (vídeo) no barato; a etapa criativa (1 call de roteiros) no forte — custo extra mínimo, salto de qualidade grande. Deixar configurável (`SCRIPT_MODEL`) pro aluno escolher.

## Duração dos roteiros

Creator AI usa 30-60s; o Content OS usa **até 50 segundos** (preferência da Reilla). Ao portar prompts, troque o texto de duração pra "ate 50 segundos".

## Pitfalls operacionais (descobertos rodando de verdade)

- **O perfil precisa POSTAR na rede analisada.** O motor de TikTok/YouTube funciona ponta-a-ponta,
  mas se o perfil quase não posta naquela rede, a análise fica rasa. Ex: um perfil pode ser
  forte no Instagram (18 vídeos) mas só ter **1 TikTok** — o pipeline roda e gera 10 hooks/10
  roteiros, porém o Gemini "preencheu" em cima de 2 vídeos só. O mínimo do Creator AI é **5 vídeos
  recentes** por perfil pra análise assertiva. Antes de testar uma rede, confira que o perfil (e o
  concorrente) tem volume ali; senão escolha outro perfil/concorrente ou avise que o resultado será fraco.
- **YouTube usa URL de CANAL, não @handle.** Diferente de IG/TikTok (que recebem `username`/@), o
  `net_youtube.run_youtube` espera URLs de canal (`youtube.com/@Canal` ou `/channel/ID`). `extractChannelId`
  aceita `channel/`, `c/` e `@`. Peça o link do canal, não o @.
- **Roteamento por rede** no `pipeline.py`: `--network {instagram|tiktok|youtube}`. Instagram usa
  `run_instagram()` inline; TikTok/YouTube importam `net_tiktok.run_tiktok(...)` / `net_youtube.run_youtube(...)`.
  Todos retornam `(result_dict, my_items, comp_items)` e passam pelo mesmo `build_dashboard_snapshot()`.
  Os módulos reusam `gemini_chat`/`transcribe_video`/`try_parse_json` do `pipeline.py` (urllib puro, sem pip).
- **YouTube ainda não foi testado com dados reais** (só compila/importa). TikTok foi testado (rodou,
  mas com o dado raso acima). Instagram é o único validado com volume real.

## Medição de custo real (pendência de melhoria)

O `pipeline.py` NÃO loga o `usageMetadata` que o Gemini devolve; o Creator AI loga (calcula custo em BRL: ~R$0,30/1M input, R$2,50/1M output, ×5,70 câmbio). Para dar custo exato por rodada (útil pro aluno ver quanto gasta), adicionar esse log lendo `usageMetadata.promptTokenCount`/`candidatesTokenCount`/`thoughtsTokenCount` de cada resposta. Custo típico de uma análise completa: centavos (Gemini flash-lite + poucos créditos Apify). O trabalho pesado/caro é a CONSTRUÇÃO da ferramenta (Opus), não rodar — rodar depois é só Gemini/Apify, sem acionar o agente.
