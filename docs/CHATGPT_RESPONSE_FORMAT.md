# Diagnostico de respostas ChatGPT e SSE

## Causa observada

Na revisao f1b770d, sse_events comparava Content-Type com text/event-stream e encerrava antes de examinar o corpo. O pedido ja enviava stream:true, store:false e Accept:text/event-stream ao endpoint publico documentado https://api.openai.com/v1/responses. Nao se trata de habilitar streaming no pedido.

O proprietario executou o probe autenticado e forneceu somente estes metadados: HTTP 200, Content-Type ausente, request ID ausente, corpo identificado pelo prefixo como SSE (sse_wrong_content_type). Isso confirma a causa imediata da rejeicao local: ausencia do cabecalho exigido pelo parser. Nao identifica quem omitiu o cabecalho (servico ou intermediario) e nao prova, sozinho, que o stream terminou corretamente.

A tentativa original confirmada no banco esta em chatgpt / gpt-6.1-sol; erro registrado em 2026-10-27 00:47:57 UTC. O banco foi consultado em modo somente leitura. O processo do agente nao consegue acessar o vault da conta do proprietario; sua tentativa de probe terminou antes do HTTP (probe_unavailable), sem extrair credenciais. A evidencia HTTP acima veio do probe executado pelo proprietario.

Uma segunda execucao do proprietario confirmou SSE sem Content-Type e evento terminal sem texto no campo output esperado (ChatGPT completed without valid text). O provider foi corrigido para reunir response.output_text.delta, response.output_text.done e response.output_item.done, mantendo os dados apenas em memoria ate response.completed confirmar status completed. Na terceira execucao, o proprietario confirmou o probe real com HTTP 200, Content-Type ausente, format=sse e error_code=null: Missing Content-Type; SSE content and completed event validated. O script so imprime esse resultado apos a resposta passar no schema AgentResult. Isso confirma a inferencia textual real do probe; nao confirma renderizacao/publicacao da producao.

## Correcao

- Content-Type e comparado sem diferenciar maiusculas/minusculas e parametros de charset.
- Quando Content-Type esta ausente, somente um prefixo SSE reconhecido habilita o parser. O prefixo e limitado e reproduzido no parser sem perder chunks; BOM UTF-8, comentarios e fragmentacao sao tratados. Essa compatibilidade permanece identificada como content_type=missing no diagnostico.
- O texto de eventos delta/done e reunido em memoria; nao se exige que o terminal repita o texto. Recusas, itens de ferramenta, partes inconsistentes e texto apos conclusao sao rejeitados. Deltas so podem ser utilizados depois de response.completed confirmar a resposta completa e o JSON passar no schema.
- O prefixo nunca significa sucesso. E necessario validar os frames, UTF-8, evento response.completed, status completed, ausencia de erro e texto aceito pelo schema Pydantic. EOF, resposta incompleta, erro tardio, JSON invalido ou recusa nao persistem resultado.
- Content-Type explicitamente incompat?vel continua sendo rejeitado mesmo com dados parecidos com SSE. HTML, resposta vazia, JSON de erro e JSON marcado completed possuem classificacoes e mensagens distintas. JSON completed isolado nao substitui o contrato streaming deste fluxo.
- JSON de erro, inclusive com HTTP 200, passa pelo tratamento de autorizacao/modelo/limite quando ha um codigo conhecido. Erros de parametros explicam o contrato rejeitado sem sugerir que uma nova senha resolve o problema.
- Nao ha troca de conta/modelo/provider, API key, endpoint privado ou alteracao do login. A aprovacao por hash e os checkpoints existentes permanecem.

## Diagnostico seguro

O backend registra exclusivamente http_status, content_type normalizado, request_id validado, format, error_code permitido e mensagem construida localmente. Parametros de cabecalhos, mensagens brutas do servico, corpos de resposta, HTML, prompts, output, tokens e Authorization nao sao copiados. Codigos desconhecidos aparecem como unrecognized_error. Campos ausentes permanecem missing/null; nao sao inventados.

Na Review studio, uma falha nova exibe Safe ChatGPT response diagnostic. O endpoint de teste de conexao tambem retorna os mesmos metadados seguros em falhas controladas. Logs antigos nao possuem esses metadados retroativamente.

Para testar a conexao real com um conteudo fixo, sem enviar o projeto nem alterar o banco:

```powershell
.\.venv\Scripts\python.exe scripts/diagnose_chatgpt.py --confirm-plan-usage
```

Execute pelo mesmo usuario Windows do login. O comando faz uma geracao curta de Creative Director, usa o modelo ja selecionado e consome limite do plano. Imprime somente o diagnostico, nunca o texto gerado. Codigo de saida 0 indica inferencia e schema concluidos; 1 indica falha. Sem --confirm-plan-usage nenhuma chamada e feita. Reinicie scripts/dev.ps1 antes de retomar a producao para carregar a correcao na API. Resume na producao vinculada mantem os resultados existentes; nao e preciso recriar o projeto ou conectar outra conta.

## Fontes oficiais consultadas

- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations

A documentacao exige stream:true/store:false e conclusao por response.completed. A compatibilidade com cabecalho ausente e uma decisao local motivada pela evidencia acima, sem aceitar conclusoes ou formatos nao documentados.

Referencia adicional dos eventos oficiais: https://developers.openai.com/api/reference/resources/responses/streaming-events .

## Confirmacao do proprietario

Diagnostico final fornecido pelo proprietario, sem conteudo gerado ou credenciais:

```json
{"http_status":200,"content_type":"missing","request_id":null,"format":"sse","error_code":null,"message":"Missing Content-Type; SSE content and completed event validated."}
```

O request ID continua ausente; nao ha evidencia para atribuir a remocao do cabecalho a um intermediario especifico.

Validacao final: 152 testes Python passaram; Ruff, TypeScript, 6 testes Vitest, 7 testes Playwright e build Next.js passaram. Veja VALIDATION.md. A tentativa de criar branch foi bloqueada por .git somente leitura; a correcao permanece no working tree, sem commits/push/PR.

Para falhas de tamanho durante STORYBOARDING, veja [CHATGPT_STREAM_LIMITS.md](CHATGPT_STREAM_LIMITS.md): trafego, evento/buffer, texto unico e tempo possuem orcamentos separados; uma mensagem de tamanho nao indica falha de autenticacao.
