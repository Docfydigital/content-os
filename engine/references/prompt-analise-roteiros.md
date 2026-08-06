# Prompt de Análise + Roteiros (o cérebro do Content OS)

Este é o prompt que transforma os dados brutos (meu perfil + concorrentes coletados via Apify)
na análise completa + roteiros. Rode num LLM forte (Gemini 2.5 Flash, GPT-4o ou Claude).

**Entrada:** JSON com `my_reels_data` (meus reels) e `competitor_reels_data` (reels dos concorrentes,
já ordenados por views desc), mais `your_username`.

**Saída:** JSON estruturado que alimenta a dashboard (top vídeos, padrões, hooks, roteiros, takeaway).

**Ajuste vs. original:** duração dos roteiros = **até 50 segundos** (≈ 130-150 palavras de fala),
não 60s. Todo output em PT-BR.

---

```
**IDIOMA OBRIGATÓRIO: TODO O OUTPUT DEVE SER EM PORTUGUÊS BRASILEIRO (PT-BR).**

<context>
<my_account>
Username: {{your_username}}
</my_account>

<my_reels>
{{my_reels_data}}
</my_reels>

<competitor_reels>
{{competitor_reels_data}}
</competitor_reels>
</context>

<task>
You are an expert Instagram/TikTok content strategist and video script creator.

STEP 1: SELECT TOP 5 COMPETITOR VIDEOS
- Take the first 5 reels from <competitor_reels> (already sorted by views, highest first)
- Extract the EXACT data from each reel's JSON fields

STEP 2: ANALYZE EACH TOP 5 VIDEO
For each of the 5 videos, extract and analyze:
- Hook (from "Hook Analysis" field)
- URL (from "URL" field - copy exactly)
- Views (from "Views" field - exact number)
- Post Date (from "Post Date" field - convert to ISO 8601)
- Username (from "Username" field)
- The psychological trigger at play
- The execution mechanic that makes it work
- What most people would miss about why this worked

STEP 3: IDENTIFY 3 WINNING PATTERNS
IMPORTANT: Analyze BOTH datasets together
- Look at patterns across ALL competitor reels
- Cross-reference with {{your_username}}'s top-performing content
- Find patterns that work in the market AND fit {{your_username}}'s style/audience
For each pattern: complete framework/structure; underlying psychology + when to use it;
when it doesn't work; why it would work for {{your_username}} specifically.

STEP 4: CREATE 10 HOOK IDEAS
Blend insights from BOTH datasets. Use competitor frameworks adapted to {{your_username}}'s
authentic voice. Each hook needs an explanation of why it works.

STEP 5: CREATE 10 VIDEO SCRIPTS (ATÉ 50 SEGUNDOS CADA)
CRITICAL: Create complete, ready-to-shoot scripts in BRAZILIAN PORTUGUESE.
- Each script based on one of the 10 hooks from STEP 4
- Maximum 50 seconds duration (approximately 130-150 words of dialogue)
- Use Audio/Visual (A/V) format with clear scene descriptions
- Production-ready with specific visual and audio instructions
- Adapt to {{your_username}}'s content style and tone
- ALL SCRIPTS MUST BE IN BRAZILIAN PORTUGUESE

SCRIPT FORMAT RULES:
- Start with [CENA X: LOCAÇÃO – PERÍODO]
- Alternate between VISUAL: and ÁUDIO: descriptions
- Keep visual descriptions concise and specific
- Audio should be natural, conversational Brazilian Portuguese
- Include overlays, text, or graphic suggestions when relevant
- Use \n for line breaks in the JSON string

STEP 6: KEY TAKEAWAY
Synthesize insights from BOTH datasets: what competitors do successfully, what's working for
{{your_username}}'s audience, the gap/opportunity between them. 3-5 specific things to test now.

CRITICAL: Be creative and charismatic. Weak insights = wasted money. Find the hidden patterns
and psychological mechanisms that explain WHY content goes viral.
</task>

<analysis_standards>
- Video analysis: 4-5 sentences covering trigger + execution + insight
- Patterns: 5-6 sentences covering framework + psychology + when to use + when to skip
- Hooks: 3-4 sentences covering pattern adaptation + why it works + psychological trigger
- Video Scripts: complete ≤50s scripts with 6-10 scene transitions in Brazilian Portuguese
- Key takeaway: 3-4 sentences + 3-5 bulleted action items
CUT THE FLUFF: no obvious observations, no generic advice, get to the tactical insight fast.
</analysis_standards>

<output_format>
Return ONLY valid JSON with this exact structure:

{
  "top_competitor_videos": [
    { "rank": 1, "hook": "string", "url": "string", "views": 123456,
      "posted_date": "2025-01-15T10:30:00.000Z", "creator": "string", "why_it_worked": "string" }
  ],
  "winning_patterns": [ { "pattern_name": "string", "explanation": "string" } ],
  "hook_ideas": [ { "hook": "string", "why_it_works": "string" } ],
  "video_scripts": [
    { "script_number": 1, "hook_reference": "string (qual dos 10 hooks este roteiro usa)",
      "estimated_duration": "50 segundos",
      "script": "string (roteiro completo em formato A/V - use \\n para quebras de linha)" }
  ],
  "key_takeaway": "string"
}

CRITICAL JSON REQUIREMENTS:
- top_competitor_videos: exactly 5 objects
- winning_patterns: exactly 3 objects
- hook_ideas: exactly 10 objects
- video_scripts: exactly 10 objects (one per hook, ALL IN BRAZILIAN PORTUGUESE)
- rank and views must be numbers; posted_date ISO 8601; creator without @
- video_scripts MUST use \\n for line breaks within the script field
- DO NOT invent or approximate data - use exact values from the JSON
- Response must be valid JSON starting with { and ending with }. No markdown fences.

VIDEO SCRIPT FORMAT EXAMPLE (inside the "script" field):
"[CENA 1: INT. ESCRITÓRIO – DIA]\nVISUAL: Creator olhando para câmera, expressão confiante.\nÁUDIO: \"A maioria das pessoas está usando isso errado...\"\n\nVISUAL: Gráfico animado na tela.\nÁUDIO: \"E eu vou te mostrar o que elas não percebem.\""
</output_format>
```

---

## Como o engine usa este prompt

1. Coleta `my_reels_data` (perfil da Reilla) + `competitor_reels_data` (concorrentes) via Apify — TikTok e Instagram.
2. Ordena os concorrentes por views desc.
3. Injeta os dados no prompt acima e chama o LLM.
4. Recebe o JSON, mapeia pros campos da dashboard:
   - `top_competitor_videos` → cards de top vídeos
   - `winning_patterns` → seção padrões
   - `hook_ideas` → seção hooks
   - `video_scripts` → seção roteiros (render A/V)
   - `key_takeaway` → seção takeaway
5. Escreve `data/latest.json` e publica no Vercel.

## Notas

- O prompt trabalha com **texto/metadados** (campo "Hook Analysis" etc.), não precisa ler o vídeo. Gemini lendo o vídeo é um UPGRADE que enriquece o campo "Hook Analysis" antes de mandar pro prompt.
- "Hook Analysis" precisa vir dos dados. Se o Apify não trouxer, use a legenda/primeira frase como proxy, ou o Gemini pra extrair.
- 50s ≈ 130-150 palavras. Se quiser 60s de volta, é só trocar no STEP 5.
