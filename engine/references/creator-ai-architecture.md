# Creator AI (IACSS) — arquitetura do SaaS (camada de infra)

Complementa `references/creator-ai-reference-pipeline.md` (que cobre o PIPELINE em detalhe).
Este arquivo cobre a ARQUITETURA/infra do app vivo — útil pra explicar por que o Content OS
entrega o mesmo resultado com ~10% da complexidade. Lido do código em `~/creatorai-v2` no Mac
(repo `Docfydigital/creatorai-v2`, branch `main`; pastas `iacss-*` são legado de abril).

## 3 camadas — e o truque do enqueue

```
[Next.js/Vercel]  →  [Supabase: banco+auth+fila]  →  [Worker Hetzner/PM2]
 site ENFILEIRA job    guarda tudo, fila job_queue    roda o pipeline pesado
```

- **A análise NÃO roda no site.** `/api/run` (POST) valida ownership por `user_id`, checa as keys
  em `workspace.env_vars`, e só INSERE um job em `job_queue` (status `pending`), respondendo na
  hora. Motivo: Vercel tem timeout curto, não aguenta os 30s–2min do pipeline.
- **Worker separado** (`worker/index.js`, Hetzner+PM2) faz `setInterval(pollQueue, 1000)`: pega o
  próximo `pending` de forma atômica (update→select), roda o pipeline, salva em `analyses`, marca
  o job `done`/`error`. O site fica fazendo `GET /api/run` perguntando "já ficou pronto?".
- Guard-rails do worker: `MAX_CONCURRENT=50`, `JOB_TIMEOUT_MS=40min` (limpa jobs travados),
  1 job pending/running por workspace por vez (409 se já houver), mantém só as **5** análises mais
  recentes por workspace+type (deleta as antigas).

## Tabelas Supabase
- `workspaces` — 1 por rede do cliente (`type` ∈ instagram/tiktok/youtube/carousel), `config`
  (username, canais...), `env_vars` (APIFY_TOKEN + GEMINI_API_KEY do cliente), `last_run/last_error`.
- `job_queue` — fila: `status` (pending→running→done/error), `payload` (competitors, phase p/ YT).
- `analyses` — resultado final `{strategy, my_reels, competitor_reels, warnings}` (ou por fase no YT).

## Acesso / negócio
- **Middleware** (`src/middleware.ts`): sem sessão Supabase → redirect `/login`. Rotas públicas:
  login/signup/activate/forgot-password/verify-otp/update-password/auth-callback.
- **Entrada de clientes**: webhooks Hotmart + AbacatePay criam conta+assinatura; migração via
  `migration_invites` (campanha 1 convite/min, máx 80/dia — ver skill supabase-access-provisioning).
- **Segredo**: `HERMES_MIGRATION_SECRET` fica no Keychain do Mac. NUNCA ler/expor.

## Por que o Content OS é a versão certa pro aluno
| Creator AI (produto SaaS) | Content OS (entrega ao aluno) |
|---|---|
| Worker Hetzner varrendo fila 24/7 | skill do Hermes roda sob demanda |
| Supabase (banco+auth+fila+RLS) | JSON no GitHub, sem banco |
| Next.js + auth + OTP + webhooks pagamento | dashboard read-only (vitrine) |
| 4 sistemas integrados, manutenção contínua | 1 skill + 1 dashboard, zero servidor |

Mesmo pipeline (ver o outro ref), mesmo resultado, sem infra. Aluno pega 2 keys (Apify+Gemini),
roda a skill, vê o relatório na dashboard.
