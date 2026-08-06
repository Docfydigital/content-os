# Postpeer API — camada de publicação do Content OS

Pesquisado em ago/2026 na doc oficial (postpeer.dev/docs). Postpeer é uma **API
unificada de publicação em redes sociais (developer-first)**, NÃO um painel visual
pro usuário final. No Content OS ele é o **motor de publicação por trás**; a tela de
organização que o aluno vê é a **dashboard do Content OS**, não o Postpeer.

## Fatos técnicos confirmados
- **Base URL:** `https://api.postpeer.dev/v1`
- **Auth:** header `x-access-key: SUA_API_KEY` (não é Bearer). Guardar em secrets.env
  como `POSTPEER_API_KEY`, fora do chat, `chmod 600`, no `.gitignore`.
- **Redes:** Twitter/X, Instagram (Feed/Reels/carrossel), YouTube+Shorts, TikTok
  (vídeo/foto/carrossel), Facebook, Threads, Pinterest, LinkedIn, Bluesky. Todas "Live".
- **SDKs:** Node `@postpeer/node`, Python `pip install postpeer`. Tem OpenAPI spec.
- **MCP server hospedado:** `https://mcp.postpeer.dev/mcp` (auth Bearer); skill oficial
  `npx skills add PostPeer-API/skills --all`. Function-calling p/ OpenAI/LangChain/CrewAI.
- **Webhooks:** sim (conexões de conta + mudança de status de post).
- **No-code:** Zapier e Make.
- **Preço:** freemium por créditos. Free $0 (20 créditos, sem cartão), Starter $25/mo
  (2000 cr), Standard $43/mo (6000 cr), Pro $120/mo (20000 cr). Todos incluem todas as redes.
- **Hospedagem:** SaaS. NÃO é self-hosted / open source (o GitHub org "PostPeer-API" é só
  as skills de agente, não o produto).

## Fluxo de publicação (4 passos, tudo via API)
1. **Conectar conta:** `GET /v1/connect/{platform}` (OAuth gerido pelo Postpeer; opcional
   agrupar em Profiles via `POST /v1/profiles`).
2. **Upload de mídia:** `POST /v1/media/upload` com `filename`+`mimeType` → devolve
   `uploadUrl` (presigned S3) + `publicUrl`; depois PUT do arquivo no `uploadUrl`.
   Formatos: img JPEG/PNG/GIF/WebP; vídeo MP4/MOV. TikTok ate 10min/4GB, IG Reel 3s-15min/300MB.
3. **Publicar/agendar:** `POST /v1/posts` com `content`, `platforms[]` (platform+accountId),
   `mediaItems[]`, e `publishNow:true` OU `scheduledFor`+`timezone`.
4. Também há endpoints de AI (captions/imagens) e Analytics (likes/reach/etc).

## Ponte Content OS → Postpeer
- **NÃO há import de calendário/CSV nativo.** A orquestração fica no engine do Content OS:
  iterar o calendário e fazer **um `POST /v1/posts` por item** (dia→rede→legenda→scheduledFor).
- Mídia (vídeo gravado) sobe antes via presigned upload; usa o `publicUrl` no `mediaItems[]`.
- Webhooks confirmam status pós-publicação.

## Cuidado de rede
O gate de segurança do Hermes bloqueia curl a domínios `.dev` (regra lookalike TLD) —
subagentes não conseguem buscar postpeer.dev sozinhos. Fetch da doc precisa do agente
principal ou colar o HTML. Os endpoints acima já estão validados, não precisa re-buscar.
