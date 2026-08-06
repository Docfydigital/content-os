# Content OS

Sistema de conteúdo viral pra criadores. Analisa **seu perfil + concorrentes** no
**Instagram, TikTok e YouTube**, descobre os posts que mais engajam e te devolve
**10 hooks, 10 roteiros (até 50s), padrões de conteúdo e um calendário** — tudo numa
dashboard limpa. No YouTube ele ainda analisa **título e thumbnail** dos vídeos campeões.

Você roda tudo pela sua própria IA (Hermes, Codex, Claude, etc.) dando o guia pra ela.
Não precisa saber programar.

```
content-os/
├── engine/       → o motor (Python). Roda a análise e gera a dashboard.
│   ├── run_all.py              # comando único: roda as 3 redes e funde tudo
│   ├── pipeline.py             # motor por rede (Instagram)
│   ├── net_tiktok.py           # rede TikTok
│   ├── net_youtube.py          # rede YouTube (título + thumbnail)
│   ├── publish_postpeer.py     # publica o calendário via Postpeer (opcional)
│   ├── config.example.json     # seus perfis (copiar → preencher)
│   ├── secrets.example.env     # suas chaves (copiar → preencher)
│   ├── GUIA-DO-ALUNO.md        # passo a passo sem código
│   └── references/             # como o sistema funciona por dentro
└── dashboard/    → a vitrine (HTML/CSS/JS). Mostra o resultado. Deploy grátis na Vercel.
```

## Começe aqui
Leia **[engine/GUIA-DO-ALUNO.md](engine/GUIA-DO-ALUNO.md)** — é o passo a passo completo.

Resumo em 3 passos:
1. Pegue 3 chaves grátis: **Apify** (coleta), **Gemini** (análise), **Postpeer** (publicar, opcional)
2. Preencha `secrets.env` e `config.json` (a partir dos `.example`)
3. `python3 engine/run_all.py` → abra a dashboard

## Custo
Centavos por análise (Gemini flash-lite + Apify). Você usa suas próprias chaves — nada
passa por servidor de terceiros.

## Privacidade
Suas chaves ficam só no seu `secrets.env` (que **nunca** vai pro git — já está no `.gitignore`).
A dashboard é read-only e roda estática.
