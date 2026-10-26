# Validacao e pendencias

## Resultados executados neste workspace

- Python 3.14.2; Node.js 26.8.1; Next.js 16.4.1; Codex CLI 0.164.0.
- Pytest: **48 passaram, 1 ignorado**. Inclui SQLite WAL/foreign keys, CRUD, duplicacao, series/personagens/assets, fila/lease/recovery/retry/cancelamento, schemas, seguranca local, provider JSONL, vault DPAPI, OAuth/refresh, Drive, YouTube, TikTok Direct Post, calendario, mixer e render real.
- O teste ignorado e **Alembic upgrade/downgrade**: pacote indisponivel no ambiente sem acesso de rede. O bootstrap SQLAlchemy e o DDL congelado da migracao foram executados em SQLite real; isso nao e apresentado como teste do comando Alembic.
- Vitest: **6 passaram** (fuso Manaus/UTC, horario de verao, datas SQLite e estados/armazenamento).
- TypeScript strict: passou. Build de producao Next.js: passou.
- Playwright: **3 passaram** com API e frontend reais em portas isoladas, sem mocks de banco/CRUD. Inclui criacao em ambos os workspaces, pause da fila, biblioteca e bloqueio de revisao sem render.
- Sintaxe dos scripts PowerShell: validada pelo parser. Setup com downloads nao foi concluido porque o sandbox bloqueia conexoes externas.
- Ruff: **nao executado com sucesso**. O pacote nao esta instalado; o executavel encontrado no cache uv tem acesso negado. `scripts/check_syntax.py` passou, mas nao substitui Ruff.
- `.env`, credenciais e saidas foram confirmados como ignorados pelo Git. Nenhuma credencial real foi introduzida no codigo.

## Videos reais

| Demo autoral | Arquivo | Duracao | Formato | Resultado |
|---|---|---|---|---|
| WonderNest Kids | output/demo/wondernest/video.mp4 | 35s | 360x640, 24fps, H264/AAC | 8 verificacoes tecnicas aprovadas |
| How It Actually Works | output/demo/how-it-works/video.mp4 | 65s | 360x640, 24fps, H264/AAC | 8 verificacoes tecnicas aprovadas |

Cada pasta inclui thumbnail, storyboard e validation.json com hash, codecs, volume e duracao. As demos usam narracao local Flite para provar o motor sem instalar voz Piper. Sao animacoes geometricas 2.5D autorais, nao geracao por Codex e nao 3D fisico. Nenhum video foi publicado. Os testes de pipeline tambem geraram MP4s reais para ambos os canais, substituindo somente a resposta do servico externo de IA por fixtures de teste.

## Contas e ferramentas ainda pendentes

1. O CLI informa AUTH_REQUIRED. Execute codex login no seu usuario. Geracao real de roteiro pelo seu ChatGPT ainda nao foi validada.
2. SDK Python oficial nao foi instalado; adapter e gate de capacidades existem, e o CLI oficial e a alternativa implementada. Sessoes sao efemeras; checkpoints persistem todos os resultados. Reuso de threads persistentes e uma extensao pendente.
3. Piper e voz inglesa nao estao configurados. O caminho de narracao importada foi testado com arquivos reais; Piper real requer instalar modelo e validar licenca/qualidade da voz.
4. Google/YouTube/TikTok estao sem credenciais/consentimento. Integracoes foram testadas com HTTP mocks, incluindo scopes, estados e payloads. Nao foram validadas em contas de producao.
5. TikTok Web exige callback HTTPS registrado. Direct Post exige escopo/aprovacao externos e permanece desligado por padrao. Upload a inbox/manual continuam alternativos.
6. Blender e Compose nao foram executados. Blender e opcional; vault Linux de containers requer configuracao adicional.
7. Estatisticas YouTube de canal podem ser sincronizadas por acao explicita. Retencao/watch time, analytics TikTok e refresh remoto periodico ainda nao estao implementados.
8. Calendario planeja e entrega publishAt no upload YouTube confirmado. Nao ha daemon de autopublicacao; AUTO_PUBLISH=true e rejeitado.
9. A arte geometrica nao entrega automaticamente aparencia de filme 3D. Assets originais importados e revisao artistica sao necessarios para elevar o acabamento.

## Git

O repositorio foi inicializado com main. Escrita em .git/index.lock e HEAD.lock foi bloqueada pelo sandbox. Estado real: **nenhum commit, nenhuma branch de feature confirmada**. Nao houve push nem force push. O proprietario pode usar scripts/commit-validated.ps1 depois de instalar as dependencias pendentes e revisar os arquivos.

O projeto nao e declarado tecnicamente concluido conforme todos os criterios do prompt: autenticacao, voz, migracao/lint e validacao externa continuam pendentes. O codigo local, UI, banco, fila e producao de midia possuem evidencias executadas acima.
