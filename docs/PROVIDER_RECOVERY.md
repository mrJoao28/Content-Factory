# Provider e recuperacao da producao

## Causa confirmada nesta instalacao

Base: 4730771a34f14593f07d3b9cc83441a3100c66ab. A consulta SQLite foi somente leitura: projeto d2454c2b-bf28-43f2-96bc-514a26c9c432, job 797c09e6-75d7-4823-a2a1-628fd1aef150, revisao 1, FAILED, checkpoint vazio.

Timestamps UTC em 26/10/2026: criacao 11:15:02; linha de preferencias (atualmente ai_provider=chatgpt) atualizada 12:27:43; ultima falha Codex 20:35:06. Ha falhas Codex anteriores no mesmo projeto. O ambiente nao define AI_PROVIDER e possui CODEX_PROVIDER legado explicito, mas a preferencia salva ChatGPT prevalece para novas producoes. A tarefa anterior nao tinha selecao; pipeline.py e enqueue() assumiam Codex implicitamente. Portanto a escolha global atual nao corrigia essa tarefa. O timestamp das preferencias e da linha inteira, nao uma auditoria por campo; nao comprova isoladamente o instante da troca de provider. Nao foi comprovada execucao de um processo antigo; o codigo da revisao atual ja explica o comportamento. O erro observado nao comprova limite do plano ou falha do login direto.

A sessao/modelo reais nao puderam ser consultados neste ambiente: o vault respondeu STORAGE_UNAVAILABLE. Isso nao demonstra desconexao no processo executado pelo proprietario. Nenhuma credencial Codex foi lida e o banco do usuario nao foi alterado para recuperar a tarefa.

## Recuperar sem recriar o projeto

1. Pare o dev antigo com Ctrl+C e execute `.\scripts\dev.ps1` na pasta do projeto para carregar o codigo atualizado. Se houver processos antigos, execute `.\scripts\stop.ps1` primeiro. Dependencias existentes nao mudaram nesta correcao; use setup -StopRunning se a instalacao estiver incompleta.
2. Em Settings, selecione ChatGPT plan - direct connection. A preferencia salva prevalece sobre .env. Confira conta e modelo; atualize o catalogo se necessario. Login nao confirma acesso de inferencia. O teste textual e opcional, explicito e consome limite do plano.
3. Abra a producao existente na Review studio ou Production queue. Confira Production text connection, origem/historico, erro e etapa interrompida. Confira New selection antes de continuar.
4. Marque a confirmacao de uso do plano e clique Use selected ChatGPT and resume. A troca e a retomada sao atomicas, usam o mesmo job/revisao e preservam checkpoints. O erro anterior so e limpo quando a retomada e efetivada.
5. Se a conta apenas foi reconectada e o job ja guarda aquela conta/modelo, Resume mantem a selecao. Modelo removido exige escolha explicita e reaplicacao; nenhum fallback de modelo, conta, provider ou cobranca ocorre.

Worker com lease valido ou upload em andamento bloqueiam a alteracao. Aguarde a liberacao; nao apague banco, artefatos ou checkpoints. Repetir a confirmacao antes do claim nao duplica job/historico. Tarefas de outras producoes nao sao alteradas.

## Regras para tarefas antigas

Selecao valida em _ai_selection e preservada. Sem selecao, so existe inferencia historica Codex quando ha exatamente um job no projeto e uma falha Codex registrada entre sua criacao e ultima atualizacao; o diagnostico identifica historical_codex_failure. Sem evidencia suficiente, a tarefa aguarda escolha explicita (WAITING_FOR_MODEL, codigo selection_required). Nao ha default implicito Codex para tarefas antigas nem troca silenciosa para o provider global.

Resultados concluidos permanecem e podem ter sido produzidos por outro modelo. Novos resultados guardam _ai_step_sources. A mudanca explicita preserva _ai_selection_history. O diagnostico distingue inicio de conclusao; somente eventos : completed usam o icone de conclusao. Eventos repetidos identicos do provider sao suprimidos por etapa.

## Pendencias audiovisuais separadas

Nesta instalacao FFmpeg e FFprobe foram encontrados. PIPER_PATH esta vazio e PIPER_VOICE_PATH nao aponta para uma voz instalada. Configure ambos e o arquivo de configuracao da voz ou importe narracao WAV/MP3 com duracao correspondente ao storyboard. Assets essenciais ausentes aguardam importacao/substituicao. Nao se sabe quais assets serao necessarios ate existir storyboard valido. Essas falhas mostram a etapa de audio/assets e sua mensagem propria; nao sao falhas Codex.

O compositor continua 2.5D, com revisao humana e aprovacao vinculada ao hash. Autenticacao nao gera imagens/videos por si so. Nenhum video da conta real foi gerado ou publicado nesta investigacao.

## Validacao

As rotas sao exercitadas no aplicativo FastAPI montado. As provas de pipeline usam os schemas reais, HTTP externo controlado, audio de teste e MP4 local com validacao tecnica nos dois canais; proibem uso de Codex no caminho direto. Isso nao equivale a inferencia real com a conta do usuario. Consulte VALIDATION.md para resultados desta entrega.

Resultados finais: 114 testes Python passaram, mais 3 repetidos apos o ajuste de intervalo de timestamps; Ruff, TypeScript, Vitest (6), Playwright (6) e build Next.js passaram. A API e o frontend foram iniciados pelos testes de navegador em portas isoladas. Nenhuma inferencia com conta real nem publicacao foi executada.
