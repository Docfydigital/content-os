# Dashboard Content OS — schema de dados, design e deploy

Projeto local: `/root/projects/content-os-dashboard/` (HTML/CSS/JS puro, sem build).
Live: **https://content-os-dashboard-tau.vercel.app** — conta Vercel `docfydigital`.

## Deploy (Vercel via CLI)

O deploy de site novo/estático NÃO dá pra fazer só com as MCP tools da Vercel
(elas leem/gerenciam deploys, mas não sobem projeto novo). Use o CLI com o token
que já existe no ambiente (`$VERCEL_TOKEN`):

```bash
npm i -g vercel                 # se ainda não instalado
cd /root/projects/content-os-dashboard
vercel deploy --prod --yes --token "$VERCEL_TOKEN"
```

- Primeira vez: adicione `--name content-os-dashboard`.
- O alias fixo `content-os-dashboard-tau.vercel.app` é preservado a cada deploy.
- Sempre confirme no ar depois: `curl -s -o /dev/null -w "%{http_code}" <url>` e
  faça `grep` por um trecho de conteúdo novo pra provar que a versão subiu.
- VPS não tem Chrome/chromium → não dá pra tirar screenshot local. A prova visual
  é a URL publicada (peça à Reilla dar Ctrl+Shift+R pra furar cache).

## Preferências de DESIGN (firmes, ditadas pela Reilla)

- **Clean, claro, organizado** — "pra uma pessoa de 5 anos bater o olho e entender".
- **Seções em blocos separados e NUMERADOS** (1..7). Cada seção é um card branco com
  borda/cantos arredondados e número no canto. Nada "solto".
- **Botões de copiar** em tudo que a pessoa vai usar: cada hook copia o texto do gancho;
  cada roteiro tem "Copiar roteiro" que copia título + hook + A/V inteiro. Feedback
  visual "✓ Copiado!" em verde.
- Fontes: Space Grotesk (títulos/números) + Plus Jakarta Sans (corpo). Aurora suave no
  topo, hover com leve elevação. Paleta roxo/rosa (--brand #6d28d9, --hot #f43f5e).

## Ordem das 7 seções (o que o prompt-cérebro gera, nessa ordem)

1. ⚔️ Você vs. campeões — diagnóstico (card escuro) + tabela comparativa (status dot: critico/ajustar/ok)
2. 🔥 Top vídeos campeões — abas por rede (TikTok, Instagram)
3. 🪝 10 hooks — cada um com "por que funciona" + botão copiar
4. 🎬 Roteiros A/V até 50s — formato cena/VISUAL/ÁUDIO + "Copiar roteiro" + "📊 Baseado em:"
5. 🧬 Padrões — com barra de força e psicologia por trás
6. 💡 Takeaway (a grande sacada) — texto + lista de ações
7. 🗓️ Calendário da semana — dia/rede/ideia/hook sugerido

## Schema do data/latest.json (o que o app.js espera)

```json
{
  "generated_at": "YYYY-MM-DD",
  "nicho": "string",
  "resumo": { "posts_analisados": N, "redes": N, "melhor_rede": "", "melhor_formato": "" },
  "analise": {
    "titulo": "", "insight": "",
    "comparacao": [ { "criterio": "", "voce": "", "campeoes": "", "status": "critico|ajustar|ok" } ]
  },
  "networks": {
    "tiktok":    { "label": "TikTok", "emoji": "🎵", "posts": [ {rank, profile, views, likes, saves, score, hook, format, posted_days_ago, url} ] },
    "instagram": { "label": "Instagram", "emoji": "📸", "posts": [ ... ] }
  },
  "hooks":    [ { "hook": "", "why": "" } ],
  "roteiros": [ { "titulo": "", "rede": "", "duracao": "Até 50s", "hook_ref": "", "baseado_em": "", "av": "texto A/V com \n" } ],
  "patterns": [ { "titulo": "", "detalhe": "", "forca": 0-100 } ],
  "takeaway": { "texto": "", "acoes": [ "" ] },
  "calendar": [ { "dia": "", "rede": "", "formato": "", "ideia": "", "hook_sugerido": "" } ]
}
```

O campo `roteiros[].av` é renderizado em `<pre class="av">` preservando `\n` (não usar
o formato antigo `estrutura[]` — o app.js aceita ambos por retrocompat, mas o padrão é `av`).

## Histórico

Cada rodada arquiva o `latest.json` anterior em `data/history/YYYY-MM-DD.json`.
Snapshot completo ≈ 18KB → 52/ano (semanal) ≈ 0,9MB/ano. Praticamente eterno no git.
Dashboard mostra os ~5 últimos; os antigos ficam guardados (não apagados).

## Postpeer (camada de publicação — futuro)

Arquitetura de 3 camadas: **Content OS = cérebro** (o que postar) → Reilla grava →
**Postpeer = braço** (agenda/publica). Elo = o calendário. Site https://www.postpeer.dev/
tem `/docs`. Chave de API guardada em `/root/content-os/secrets.env` como
`POSTPEER_API_KEY` (chmod 600, no .gitignore). Confirmar endpoints na doc antes de
integrar — se tiver API, engine posta direto; senão, export CSV/JSON ou botão copiar.
```
