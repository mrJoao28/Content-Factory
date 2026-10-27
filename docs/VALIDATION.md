# Validacao e pendencias

## Limites de streaming e storyboard: validacao final

- Base 73a7764. Consulta de producao somente leitura confirmou o job c01a3bd3-0030-40ea-b5f2-68cc6f72e4d2 parado em STORYBOARDING com alvo 35s e creative_director/script_writer preservados. O corpo da resposta nao foi retido e sua complexidade exata nao foi presumida. Detalhes em [CHATGPT_STREAM_LIMITS.md](CHATGPT_STREAM_LIMITS.md).
- Reproducao autoral: 7 cenas, 35s, 56 camadas, 336 keyframes; JSON compacto 18.968 bytes, SSE 2.691.684 bytes com 18.968 deltas. O parser novo contabiliza 18.968 bytes de texto unico, sem somar as versoes finais. Pico tracemalloc de parse 191.000 bytes, excluindo a fixture previamente alocada e sem equivaler a RSS total.
- O teste real do pipeline reproduz a falha com teto de 2 MB, verifica os checkpoints, aplica Resume ao mesmo job/revisao e produz MP4 real de 35s. Confirma uma ScriptVersion, um artefato, duration/checks via FFprobe e HUMAN_REVIEW sem aprovacao automatica. Apenas HTTP externo e controlado; audio de teste conhecido e renderer/SQLite/schemas/rotas reais.
- Execucao final: **173 testes Python passaram em 154.14s**, sem skips (`python -m pytest -q --durations=5 -o faulthandler_timeout=60 --basetemp=data/storyboard-budget-verified`). A prova de retomada/render de 35s levou 10.70s na suite final. Cobertura inclui muitos eventos, limites de frame/buffer/texto/trafego, configuracao finita, tentativas compartilhando trafego, complexidade/duracao, EOF, timeout e cancelamento.
- **Ruff passou**, TypeScript strict passou, Vitest **6 passaram**, Next.js build passou e Playwright **7 passaram** com API/frontend reais em portas isoladas.
- Uma execucao anterior foi interrompida por travamento na finalizacao do monitor de desconexao do teste de conexao. O monitor agora observa tambem o evento de encerramento, evitando depender somente do cancelamento de task. Somente os processos identificados daquela execucao pytest foram encerrados; servidores do proprietario foram preservados. A suite final acima passou apos a correcao.
- O banco, modelo, conta e checkpoints do proprietario nao foram modificados. Nenhuma geracao real de storyboard pela conta foi iniciada pelo agente nesta entrega; a retomada pelo proprietario permanece pendente. Nenhuma publicacao foi realizada.
- Branch fix/storyboard-stream-budgets tentada e bloqueada por .git somente leitura; nenhum commit, push ou PR foi criado. Alteracoes permanecem locais.

## SSE e formato ChatGPT: validacao final

- Base f1b770d; detalhes em [CHATGPT_RESPONSE_FORMAT.md](CHATGPT_RESPONSE_FORMAT.md). O proprietario reproduziu HTTP 200 sem Content-Type, primeiro rejeitado como SSE-like; apos correcao do cabecalho, o terminal nao fornecia texto no campo esperado. O parser agora reconhece o stream por conteudo apenas quando o cabecalho falta e reune texto dos eventos antes da confirmacao terminal.
- O proprietario confirmou inferencia real no probe corrigido: HTTP 200, content_type=missing, format=sse, error_code=null. O script so retorna esse resultado depois de completar inferencia e validar AgentResult. Nao houve geracao/publicacao de video da conta real por este agente.
- Pytest final: **152 passaram**, sem skips, em **269.75s** (`python -m pytest -q --basetemp=data/chatgpt-response-complete-final`). Inclui os formatos SSE/JSON erro/JSON completed/HTML/vazio, MIME ausente, UTF-8 e chunks fragmentados, coleta de texto por eventos, recusa, erro tardio, EOF, schema invalido, preservacao de selecao/checkpoints e MP4 local real dos dois canais com respostas externas controladas.
- **Ruff passou**, TypeScript strict passou, Vitest **6 passaram**, build Next.js passou e Playwright **7 passaram** com API/frontend reais em portas isoladas. O teste de navegador cobre a apresentacao do diagnostico seguro na revisao, sem simular as rotas verificadas.
- Um timeout do teste de startup em /doctor foi ajustado de 2s para 35s nessa chamada, pois o endpoint executa probes locais reais com limites proprios; a execucao final passou. Os servicos de producao nao tiveram seus timeouts alterados por isso.
- Logs e respostas incluem somente metadados permitidos e mensagens locais; nenhum prompt, output, HTML, mensagem bruta do servidor, token ou Authorization e registrado pelo diagnostico. Login, conta/modelo, checkpoints e banco do proprietario foram preservados.
- Criacao de branch tentada e bloqueada pela permissao de somente leitura de .git. Nenhum commit, push ou PR desta correcao foi criado; alteracoes permanecem locais.

## Recuperacao de provider/job: 2026-10-26

- Base 4730771; causa e dados sanitizados documentados em [PROVIDER_RECOVERY.md](PROVIDER_RECOVERY.md). Banco do proprietario consultado somente em leitura; nenhuma producao real foi retomada ou recriada pelo agente.
- `python -m pytest -q --basetemp=data/provider-recovery-final`: **114 passaram**, sem skips, em 115.21s. Apos limitar a busca de etapa ao intervalo temporal do job, os testes de historico e pipeline foram repetidos: **3 passaram**, incluindo os dois renders reais e recuperacao apos persistir o artefato.
- Ruff passou; TypeScript strict passou; Vitest **6 passaram**; build de producao Next.js passou.
- Playwright inclui recuperacao de FAILED com Codex para ChatGPT usando as rotas reais, consentimento explicito, vault DPAPI de teste e checkpoint preservado. API Uvicorn e frontend Next.js sao iniciados em portas isoladas; worker desabilitado para o teste de interface. As provas de pipeline Python executam worker, SSE externo controlado, schemas reais, audio conhecido e MP4 local nos dois canais, sem chamadas Codex.
- Execucao final Playwright: **6 passaram em 43.6s**, incluindo recuperacao pela interface sem simular as rotas verificadas. Os timestamps da fixture respeitam o intervalo de vida do job.
- Login/inferencia reais continuam pendentes do proprietario. O vault da conta real respondeu STORAGE_UNAVAILABLE no ambiente do agente; isso nao comprova erro de login no processo do usuario. FFmpeg e FFprobe disponiveis; Piper/voz nao configurados; assets essenciais dependem do storyboard ainda ausente.
- A criacao de fix/provider-selection-and-job-recovery foi tentada e bloqueada por somente leitura de .git. Nenhum commit, push ou PR desta correcao foi criado. As alteracoes preexistentes em egg-info foram preservadas.

## Login ChatGPT direto: validacao de 2026-10-26

- Pytest: **104 passaram** (`python -m pytest --basetemp=data/test-chatgpt-final -q`). Inclui registro OAuth, JWT/JWKS, PKCE, callback/replay/cancelamento, scopes efetivos, vault DPAPI, refresh coordenado entre processos, SSE fragmentado, erros HTTP, checkpoints e retomada dos dois canais com MP4 real. Somente servicos externos foram substituidos nos testes.
- Ruff passou; TypeScript strict passou; Vitest **6 passaram**; Playwright **5 passaram**; build de producao Next.js passou. Sintaxe PowerShell validada.
- Instalacao limpa do frontend em pasta isolada com o lockfile atual: **npm ci instalou 94 pacotes**, executando scripts normalmente.
- API Uvicorn iniciou com HTTP real, sem chave de API, CLI Codex indisponivel e importacao do SDK desabilitada no processo de teste. Dashboard/diagnostico responderam e a fila sem autorizacao entrou em WAITING_FOR_AUTH. Os testes de navegador iniciaram API e frontend reais em portas isoladas.
- Login com conta humana, elegibilidade do plano, catalogo real e inferencia OpenAI real **nao foram executados**. Para validar: iniciar a aplicacao, selecionar ChatGPT direto em Settings, autorizar, escolher um modelo e confirmar o teste que consome o limite do plano.
- Referencia comportamental My-Code-Agent: commit `9f2212aebff6baecc7edd54be81d04e4d41459a4`. Implementacao Python independente baseada na documentacao oficial; nenhum codigo TypeScript foi copiado. Guia: [CHATGPT_DIRECT.md](CHATGPT_DIRECT.md).
- Base Content Factory: `1e455b8d57b7d1738de10281d769e9235e070233`. Alteracoes locais preservadas. A criacao da branch foi bloqueada pela permissao de somente leitura de `.git`; nenhum commit, push ou PR foi criado nesta entrega.

Os registros abaixo descrevem validacoes anteriores e limitacoes das demais integracoes; as contagens atuais sao as desta secao.

## Resultados anteriores executados neste workspace

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

1. A conexao ChatGPT direta requer autorizacao humana em Settings e teste explicito de inferencia. O provider Codex continua opcional e usa sua autenticacao oficial propria; nao e requisito do fluxo direto.
2. SDK Python oficial 0.163.0 instalado. A consulta real de conta funcionou com o runtime incluido no SDK; nao havia sessao autenticada disponivel neste processo. Login usa o runtime correspondente do SDK; inferencia usa o CLI oficial quando o gate de isolamento exige. Sessoes sao efemeras; checkpoints persistem todos os resultados. Reuso de threads persistentes e uma extensao pendente.
3. Piper e voz inglesa nao estao configurados. O caminho de narracao importada foi testado com arquivos reais; Piper real requer instalar modelo e validar licenca/qualidade da voz.
4. Google/YouTube/TikTok estao sem credenciais/consentimento. Integracoes foram testadas com HTTP mocks, incluindo scopes, estados e payloads. Nao foram validadas em contas de producao.
5. TikTok Web exige callback HTTPS registrado. Direct Post exige escopo/aprovacao externos e permanece desligado por padrao. Upload a inbox/manual continuam alternativos.
6. Blender e Compose nao foram executados. Blender e opcional; vault Linux de containers requer configuracao adicional.
7. Estatisticas YouTube de canal podem ser sincronizadas por acao explicita. Retencao/watch time, analytics TikTok e refresh remoto periodico ainda nao estao implementados.
8. Calendario planeja e entrega publishAt no upload YouTube confirmado. Nao ha daemon de autopublicacao; AUTO_PUBLISH=true e rejeitado.
9. A arte geometrica nao entrega automaticamente aparencia de filme 3D. Assets originais importados e revisao artistica sao necessarios para elevar o acabamento.

## Git

A revisao base desta entrega e 1e455b8d57b7d1738de10281d769e9235e070233, criada fora desta sessao. As correcoes desta sessao permanecem no working tree. A politica do ambiente permite somente leitura de .git; nenhum novo commit, branch, merge ou push foi realizado.

O projeto nao e declarado tecnicamente concluido conforme todos os criterios do prompt: autenticacao de conta, voz e validacao externa continuam pendentes. O codigo local, UI, banco, fila e producao de midia possuem evidencias executadas acima.


## Correcoes de instalacao e login (2026-10-26)

- Lockfile reparado com os registros oficiais das dependencias opcionais por plataforma, preservando as versoes principais. `npm ci --dry-run --offline` passou. Instalacao real em pasta vazia passou: 94 pacotes instalados com npm ci, sem ignorar scripts. Um npm ci no diretorio de desenvolvimento encontrou EPERM porque outro Next.js mantinha o binario SWC aberto; npm install restaurou as dependencias locais. Pare o frontend com Ctrl+C antes de executar setup novamente.
- Login reutiliza sessao ChatGPT existente, mostra link oficial/codigo de dispositivo, atualiza status automaticamente, limita startup a 30s e login a 5min, e permite cancelar. O SDK usa seu runtime correspondente; forcar o CLI global provocou TransportClosedError na consulta de conta, enquanto o runtime incluido respondeu corretamente.
- Os testes de login incluem subprocesso real de teste e fixtures somente para o servico externo de autenticacao. Nenhuma sessao de usuario, upload ou publicacao foi simulada como real.
- O frontend de testes usa diretorio de build proprio, evitando o lock do servidor de desenvolvimento que pode estar aberto pelo usuario.


## Scripts Windows: recuperacao de servidores antigos

63 testes Python passaram, incluindo tres regressoes executadas em PowerShell: selecao de processos restrita ao caminho e papel do projeto, deteccao de porta TCP ocupada e preservacao do erro original durante limpeza. O comando dev foi executado com a porta 8000 ocupada e interrompeu antes de iniciar processos, exibindo a causa correta. A instalacao local do Next foi restaurada e seu entrypoint confirmou a versao 16.4.1. A parada de processos do usuario pelo novo stop.ps1 ainda precisa ser executada no terminal do proprietario; o sandbox nao tem acesso a esses processos.
