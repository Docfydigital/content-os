# Creator AI — pipeline de referência (engenharia reversa)

O **Creator AI** (`creatorai-v2`, app em produção da Reilla em `app.iacreatorsociety.com.br`)
é a implementação de referência que o Content OS replica — "o mesmo resultado, mais simples".
Este arquivo documenta como ele gera os relatórios, extraído lendo o código no Mac dela
(`/Users/reillalinya/creatorai-v2/worker/pipelines/`). Use como fonte da verdade ao codar
o `engine.py`.

## Stack real do Creator AI (o "app grande")
Next.js + Supabase (auth/banco/storage) + worker Node em Hetzner + PM2 + webhook Hotmart.
Tabela `analyses` guarda o resultado (`{...analysis, ...scripts}`). O aluno NÃO monta isso —
ele usa as skills do Hermes + a dashboard como vitrine (muito mais simples, mesmo relatório).

## Fluxo do Instagram OS (padrão pras 3 redes)
Input do usuário: **seu @ + @s dos concorrentes**.

1. **Coleta (Apify)** — actor `xMc5Ga1oCONPmWJIa`, `run-sync-get-dataset-items`, 15 reels por perfil.
2. **Filtra** — seus reels: `sortByViews(filterByDays(60)).slice(0,8)`; concorrentes: top 10 últimos 60d
   por views. Fallback: se <5 nos últimos 60d, completa com all-time. **Exige mínimo 5 reels**
   (seus e dos concorrentes) senão aborta com erro explicativo (perfil novo → sugerir adicionar concorrente).
3. **Transcreve (Gemini)** — modelo `gemini-3.5-flash-lite`, endpoint `generativelanguage.googleapis.com/v1beta`,
   `key=` na query. Manda `fileData:{mimeType:'video/mp4', fileUri: videoUrl}` — o Gemini lê o vídeo pela URL.
   Máx 2000 chars de transcript. Concurrency 2. Retry 3x em 429/503 com backoff 20s*attempt.
4. **Extrai hooks (Gemini chat)** — batch: 1 call analisa TODOS os reels de uma vez, devolve array
   `[{hook, power_words[]}]`. Prompt = `HOOK_ANALYZER_SYSTEM`.
5. **Análise PARTE 1 (Gemini chat)** — `buildAnalysisSystemPrompt(username)` → JSON com
   `performance_overview`, `top_competitor_videos` (5), `winning_patterns` (3), `hook_ideas` (10),
   `competitor_gaps` (unexplored/moderate/saturated), `quick_wins` (3), `key_takeaway`.
6. **Roteiros PARTE 2 (Gemini chat)** — `buildScriptsSystemPrompt(username)`, recebe a análise da parte 1
   como contexto → JSON com `video_scripts` (10, formato A/V + first_frame_blueprint + editing_recipe +
   performance_score) e `content_calendar` (**30 dias**, roteiros distribuídos + 20 temas originais).
7. **Merge** — `strategy = {...analysis, ...scripts}`.

## Técnica-chave: 2 chamadas separadas + JSON safety
Análise e roteiros são **chamadas LLM SEPARADAS** (não um JSON gigante único) — isso evita
o JSON quebrar por tamanho/truncamento. Cada uma roda em **loop de 2 tentativas**; se o parse
falhar na 1ª, tenta de novo. O parser (`tryParseJSON`) é defensivo:
- remove code fences ```json ... ```
- extrai só do primeiro `{` ao último `}`
- 2º fallback: remove trailing commas `,(\s*[}\]])` → `$1`
- valida presença de campo esperado (`hook_ideas`, `video_scripts`) antes de aceitar

Regra anti-JSON-inválido embutida nos prompts: **"NÃO use aspas duplas dentro de strings —
use aspas simples"** e **"scripts com \n escaped, não quebras de linha reais"**.

## Fatos que corrigem/afinam o engine do Content OS
| Item | Valor real no Creator AI |
|---|---|
| Modelo Gemini | `gemini-3.5-flash-lite` (NÃO 2.5-flash) |
| Keys necessárias | **só 2**: Apify + Gemini (sem OpenRouter) |
| Custo (código real) | input R$0,30/1M, output R$2,50/1M, câmbio ~5,70; ~60 vídeos 30s ≈ centavos |
| Roteiros deles | 10 de **60s** + calendário **30 dias** |
| Roteiros nossos (Reilla) | **até 50s** — preferência dela ganha sobre o padrão de 60s |
| Erros de key | mensagens PT-BR amigáveis por status (403/400/402/401/429/503) apontando pro tutorial |

## Como acessei (bridge do Mac)
Chrome com JavaScript-via-Apple-Events DESATIVADO → não deu pra inspecionar o app pela tela.
Fui direto no **código-fonte** via bridge (`reilla-mac-bridge-access`), que é mais confiável pra
entender "como funciona" do que dirigir a UI. Refs salvas em `/root/creator-ai-refs/*.txt`.
