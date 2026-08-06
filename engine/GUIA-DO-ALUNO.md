# Content OS — Guia rápido (rodar na sua IA)

O Content OS analisa seu perfil + concorrentes nas 3 redes (Instagram, TikTok, YouTube),
descobre os posts que mais engajam, e te devolve **10 hooks, 10 roteiros (até 50s),
padrões de conteúdo e um calendário** — tudo numa dashboard. No YouTube ele ainda analisa
**título e thumbnail** dos vídeos campeões.

Você roda tudo dando este guia pra sua IA (Hermes, Codex, Claude, etc.) e pedindo pra
ela seguir os passos. Não precisa saber programar.

---

## 1. Pegue suas 3 chaves (grátis pra começar)

| Chave | Onde pegar | Pra quê |
|---|---|---|
| **Apify** | apify.com → Settings → API tokens | coletar os posts das redes |
| **Gemini** | ai.google.dev → "Get API key" | análise, roteiros e leitura da thumbnail |
| **Postpeer** *(opcional)* | postpeer.dev | publicar o calendário (só se quiser publicar) |

> Você paga suas próprias chaves. O custo por análise é de centavos (Gemini flash-lite + Apify).

## 2. Configure os segredos

Copie `secrets.example.env` para `secrets.env`, cole suas chaves no lugar de `SUA_KEY_AQUI`
e proteja o arquivo:

```bash
cp secrets.example.env secrets.env
# edite secrets.env e cole suas chaves
chmod 600 secrets.env
```

Nunca suba o `secrets.env` no GitHub. Ele já entra no `.gitignore`.

## 3. Configure seus perfis

Copie `config.example.json` para `config.json` e preencha com o **seu** perfil e os
**concorrentes** que você quer analisar em cada rede:

- Instagram e TikTok: use o `@` sem o arroba (ex: `"joaosilva"`)
- YouTube: use a URL do canal (ex: `"https://www.youtube.com/@joaosilva"`)
- Deixe uma rede de fora? É só apagar o bloco dela ou deixar o `me` em branco — ela é pulada.

## 4. Rode o Content OS (um comando)

```bash
python3 run_all.py
```

Ele roda as 3 redes e junta tudo numa dashboard só (`data/latest.json`). Leva de 3 a 10 min
por rede. Quer rodar só algumas? `python3 run_all.py --only instagram,tiktok`

## 5. Veja o resultado

Abra a dashboard. Se for publicar online (grátis na Vercel):

```bash
cd content-os-dashboard
vercel deploy --prod
```

## 6. (Opcional) Publicar o calendário no Postpeer

Primeiro **veja** o que seria publicado, sem publicar (dry-run):

```bash
python3 publish_postpeer.py
```

Quando estiver tudo certo, conecte suas contas no Postpeer, pegue o `accountId` de cada
rede, coloque no `config.json` em `"postpeer_accounts"` e publique de verdade:

```bash
python3 publish_postpeer.py --confirm
```

---

### Resumo do que a IA precisa fazer por você
1. `cp secrets.example.env secrets.env` e preencher as chaves → `chmod 600 secrets.env`
2. `cp config.example.json config.json` e preencher seus perfis
3. `python3 run_all.py`
4. `vercel deploy --prod` (se for publicar a dashboard)
5. `python3 publish_postpeer.py` (dry-run) e depois `--confirm` (se for publicar posts)
