# Limites SSE e retomada do storyboard

## Investigacao e causa

Base 73a7764. A consulta somente leitura encontrou o job c01a3bd3-0030-40ea-b5f2-68cc6f72e4d2, projeto afa026ef-90ac-4d07-a43d-3aad21447051, FAILED em STORYBOARDING, atualizado em 2026-10-27 01:47:20 UTC, alvo 35 segundos. creative_director e script_writer estao presentes; storyboard_planner nao foi salvo. Nenhum desses resultados ou selecoes foi apagado/reescrito pelo agente.

O erro antigo ocorre quando a soma de TODOS os chunks SSE ultrapassa MAX_BODY=2.000.000, independentemente do tamanho do JSON final. Os envelopes, comentarios, reasoning e repeticoes de output tambem usam trafego. StreamText somava separadamente deltas, output_text.done e output_item.done da mesma parte. Alem disso, o schema geral permitia 32 camadas x 64 keyframes por cena: sete cenas podiam descrever 14.336 keyframes. Nao havia um orcamento menor para geracao nem validacao de complexidade antes do checkpoint.

A resposta que falhou nao foi retida. Portanto nao e possivel afirmar o numero real de camadas, keyframes, bytes de reasoning ou a proporcao de overhead daquela tentativa. A reproducao abaixo demonstra a falha mesmo com um storyboard valido e compacto, sem copiar conteudo privado.

## Medidas da reproducao autoral

| Medida | Resultado |
|---|---:|
| Cenas / duracao | 7 / 35 segundos |
| Camadas / keyframes | 56 / 336 |
| JSON compacto sem defaults | 18.968 bytes |
| Mesmo Board expandido | 47.983 bytes |
| Eventos de delta, um caractere por evento | 18.968 |
| Trafego SSE incluindo versoes finais | 2.691.684 bytes |
| Texto unico contabilizado | 18.968 bytes |
| Pico tracemalloc durante parse | 191.000 bytes |

A fixture foi alocada antes do tracemalloc; o pico mede alocacoes Python durante o parse, nao RSS, rede, frontend ou memoria total do processo. O arquivo local ignorado data/diagnostics/storyboard-budget-metrics.json registra essas medidas. A fixture reproduzivel esta em tests/test_chatgpt_limits.py. O limite antigo rejeita esse fluxo apesar de seu conteudo final pequeno; nao e necessario gerar cenas absurdamente complexas para atingir 2 MB.

## Limites independentes

| Variavel | Padrao | Faixa aceita | Escopo |
|---|---:|---:|---|
| CHATGPT_STREAM_MAX_BYTES | 16.777.216 (16 MiB) | 16 KiB a 128 MiB | Soma dos corpos recebidos por geracao/papel, incluindo retry e correcao JSON |
| CHATGPT_EVENT_MAX_BYTES | 2.097.152 (2 MiB) | 1 KiB a 8 MiB | Um evento SSE e seu buffer de linha, inclusive sem delimitador |
| CHATGPT_TEXT_MAX_BYTES | 1.048.576 (1 MiB) | 1 KiB a 4 MiB | Texto UTF-8 unico, por indice de output/conteudo |
| CHATGPT_TIMEOUT_SECONDS | 300 recomendado | 1 a 1800 segundos | Tempo total do papel, incluindo espera de concorrencia, tentativas e correcao |

Se CHATGPT_TIMEOUT_SECONDS nao estiver definido, CODEX_TIMEOUT_SECONDS continua sendo o valor de compatibilidade das instalacoes existentes; isso nao seleciona nem executa Codex. Novas instalacoes possuem a variavel direta em .env.example. Nao e preciso mudar .env para obter os novos padroes de bytes. Nao ha fallback para limites ilimitados nem aumento automatico apos uma falha.

Os bytes de trafego correspondem ao corpo SSE depois da decodificacao HTTP, nao a headers/TLS ou bytes comprimidos. O leitor entrega blocos de ate 16 KiB ao parser; o stream nao e acumulado inteiro. O limite de evento e reiniciado por frame, nao por chunk de rede. Varias mensagens pequenas no mesmo chunk nao viram um evento gigante. O texto usa bytearrays por parte e no maximo 128 partes; versoes finais identicas sao verificadas e nao somadas novamente. O evento terminal continua limitado separadamente e seu texto final e validado pelo teto de texto.

O padrao de 16 MiB oferece margem para mais eventos/metadata que a reproducao de 2,69 MB, sem reservar essa memoria toda. Os tetos de evento e texto continuam bem menores. MAX_BODY=2.000.000 permanece somente como limite de JSON nao streaming (OAuth/catalogo/erros), sem aumento indiscriminado.

## Complexidade e validade

A geracao de Board recebe schema e instrucoes com maximo de ceil(duracao/5) cenas, limitado a 60; para 35 segundos sao no maximo sete cenas. Cada cena tem ate oito camadas, cada camada ate seis keyframes esparsos e narracao de ate 400 caracteres. Sao solicitados JSON compacto, omissao de defaults e nenhuma repeticao de descricoes de assets/personagens. O schema geral de importacao/edicao manual nao foi reduzido.

Depois de Pydantic, antes de salvar o checkpoint, a geracao valida novamente os orcamentos, keyframes relativos dentro da cena e soma de duracoes igual ao alvo, com tolerancia numerica de 0,01 segundo. Um resultado de 34 ou 36 segundos nao substitui os 35 pedidos. Erros de schema/complexidade permitem uma unica correcao com as mesmas restricoes; respostas excessivas nao provocam loop de aumentos/retries.

Sucesso ainda exige response.completed, status completed, texto valido e schema Pydantic. Refusal, erro tardio, interrupcao/EOF ou cancelamento nao salvam texto parcial. Timeout e cancelamento sao observados tambem durante processamento intenso de muitos eventos, sem esperar apenas uma pausa da rede.

## Retomar a producao existente

1. Pare o dev antigo com Ctrl+C e execute .\scripts\dev.ps1 para carregar os novos limites e prompts.
2. Abra a producao existente afa026ef-90ac-4d07-a43d-3aad21447051 na fila/revisao. Confira a selecao ja vinculada, sem trocar conta/modelo.
3. Clique Resume. A retomada existente remove o erro e mantem o mesmo job/revisao; creative_director e script_writer sao reutilizados. A proxima chamada e Storyboard Planner.
4. Se houver erro de limite, o diagnostico agora distingue stream_limit, event_limit, text_limit e runtime_limit. Reduza complexidade/verifique a configuracao indicada. Nao refaca login para resolver tamanho.

Nao recrie o projeto nem apague o banco. A prova de integracao reproduz falha com 2 MB, faz Resume e gera MP4 real de 35 segundos com sete cenas, respostas externas controladas e audio de teste conhecido. Ela verifica job unico, ScriptVersion unica, artefato unico e aprovacao humana ainda pendente. Isso nao e uma geracao real pela conta do proprietario. O compositor continua 2.5D, e audio/assets reais podem exigir configuracao independente.

## Resultados executados

173 testes Python passaram, sem skips, em 154.14s. A prova de recuperacao e MP4 real de 35s levou 10.70s nessa suite. Ruff, TypeScript, seis testes Vitest, sete Playwright e build de producao passaram. A suite tambem confirmou inicializacao real da API sem Codex/API key e o navegador iniciou API/frontend isolados. Houve ajuste do monitor de desconexao para encerrar quando a geracao termina, cobrindo a limpeza de cancelamento observada durante os checks.

A retomada pela conta do proprietario nao foi executada pelo agente e nenhum video foi publicado. Git bloqueou a criacao de branch por permissao de somente leitura; nao ha commits/push/PR desta entrega.
