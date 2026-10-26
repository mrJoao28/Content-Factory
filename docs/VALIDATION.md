# Validacao e pendencias

## Resultados executados neste workspace

- Python 3.14.2; Node.js 26.8.1; Next.js 16.4.1; Codex CLI 0.164.0.
- Pytest: **63 passaram, nenhum ignorado**. Inclui SQLite WAL/foreign keys, CRUD, duplicacao, series/personagens/assets, fila/lease/recovery/retry/cancelamento, schemas, seguranca local, provider JSONL, vault DPAPI, OAuth/refresh, Drive, YouTube, TikTok Direct Post, calendario, mixer e render real.
- **Alembic upgrade/downgrade passou** em banco SQLite isolado. O SQLAlchemy global estava incompleto; a versao 2.0.50 foi reinstalada dentro da .venv a partir de um wheel oficial em cache.
- Vitest: **6 passaram** (fuso Manaus/UTC, horario de verao, datas SQLite e estados/armazenamento).
- TypeScript strict: passou. Build de producao Next.js: passou.
- Playwright: **4 passaram** com API e frontend reais em portas isoladas, sem mocks de banco/CRUD. Inclui criacao em ambos os workspaces, pause da fila, biblioteca, bloqueio de revisao sem render e tela de login Codex com alternativa por dispositivo.
- Sintaxe dos scripts PowerShell: validada pelo parser. Setup com downloads nao foi concluido porque o sandbox bloqueia conexoes externas.
- Ruff: **ruff check . passou**. Imports e formatacao foram corrigidos.
- `.env`, credenciais e saidas foram confirmados como ignorados pelo Git. Nenhuma credencial real foi introduzida no codigo.

## Videos reais

| Demo autoral | Arquivo | Duracao | Formato | Resultado |
|---|---|---|---|---|
| WonderNest Kids | output/demo/wondernest/video.mp4 | 35s | 360x640, 24fps, H264/AAC | 8 verificacoes tecnicas aprovadas |
| How It Actually Works | output/demo/how-it-works/video.mp4 | 65s | 360x640, 24fps, H264/AAC | 8 verificacoes tecnicas aprovadas |

Cada pasta inclui thumbnail, storyboard e validation.json com hash, codecs, volume e duracao. As demos usam narracao local Flite para provar o motor sem instalar voz Piper. Sao animacoes geometricas 2.5D autorais, nao geracao por Codex e nao 3D fisico. Nenhum video foi publicado. Os testes de pipeline tambem geraram MP4s reais para ambos os canais, substituindo somente a resposta do servico externo de IA por fixtures de teste.

## Contas e ferramentas ainda pendentes

1. O CLI informa AUTH_REQUIRED. Execute codex login no seu usuario. Geracao real de roteiro pelo seu ChatGPT ainda nao foi validada.
2. SDK Python oficial 0.163.0 instalado. A consulta real de conta funcionou com o runtime incluido no SDK; nao havia sessao autenticada disponivel neste processo. Login usa o runtime correspondente do SDK; inferencia usa o CLI oficial quando o gate de isolamento exige. Sessoes sao efemeras; checkpoints persistem todos os resultados. Reuso de threads persistentes e uma extensao pendente.
3. Piper e voz inglesa nao estao configurados. O caminho de narracao importada foi testado com arquivos reais; Piper real requer instalar modelo e validar licenca/qualidade da voz.
4. Google/YouTube/TikTok estao sem credenciais/consentimento. Integracoes foram testadas com HTTP mocks, incluindo scopes, estados e payloads. Nao foram validadas em contas de producao.
5. TikTok Web exige callback HTTPS registrado. Direct Post exige escopo/aprovacao externos e permanece desligado por padrao. Upload a inbox/manual continuam alternativos.
6. Blender e Compose nao foram executados. Blender e opcional; vault Linux de containers requer configuracao adicional.
7. Estatisticas YouTube de canal podem ser sincronizadas por acao explicita. Retencao/watch time, analytics TikTok e refresh remoto periodico ainda nao estao implementados.
8. Calendario planeja e entrega publishAt no upload YouTube confirmado. Nao ha daemon de autopublicacao; AUTO_PUBLISH=true e rejeitado.
9. A arte geometrica nao entrega automaticamente aparencia de filme 3D. Assets originais importados e revisao artistica sao necessarios para elevar o acabamento.

## Git

A main ja possui o commit inicial fb23d33, criado fora desta sessao. As correcoes desta sessao permanecem no working tree. A politica do ambiente permite somente leitura de .git; nenhum novo commit, branch, merge ou push foi realizado.

O projeto nao e declarado tecnicamente concluido conforme todos os criterios do prompt: autenticacao de conta, voz e validacao externa continuam pendentes. O codigo local, UI, banco, fila e producao de midia possuem evidencias executadas acima.


## Correcoes de instalacao e login (2026-10-26)

- Lockfile reparado com os registros oficiais das dependencias opcionais por plataforma, preservando as versoes principais. `npm ci --dry-run --offline` passou. Instalacao real em pasta vazia passou: 94 pacotes instalados com npm ci, sem ignorar scripts. Um npm ci no diretorio de desenvolvimento encontrou EPERM porque outro Next.js mantinha o binario SWC aberto; npm install restaurou as dependencias locais. Pare o frontend com Ctrl+C antes de executar setup novamente.
- Login reutiliza sessao ChatGPT existente, mostra link oficial/codigo de dispositivo, atualiza status automaticamente, limita startup a 30s e login a 5min, e permite cancelar. O SDK usa seu runtime correspondente; forcar o CLI global provocou TransportClosedError na consulta de conta, enquanto o runtime incluido respondeu corretamente.
- Os testes de login incluem subprocesso real de teste e fixtures somente para o servico externo de autenticacao. Nenhuma sessao de usuario, upload ou publicacao foi simulada como real.
- O frontend de testes usa diretorio de build proprio, evitando o lock do servidor de desenvolvimento que pode estar aberto pelo usuario.


## Scripts Windows: recuperacao de servidores antigos

63 testes Python passaram, incluindo tres regressoes executadas em PowerShell: selecao de processos restrita ao caminho e papel do projeto, deteccao de porta TCP ocupada e preservacao do erro original durante limpeza. O comando dev foi executado com a porta 8000 ocupada e interrompeu antes de iniciar processos, exibindo a causa correta. A instalacao local do Next foi restaurada e seu entrypoint confirmou a versao 16.4.1. A parada de processos do usuario pelo novo stop.ps1 ainda precisa ser executada no terminal do proprietario; o sandbox nao tem acesso a esses processos.
