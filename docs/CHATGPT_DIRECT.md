# ChatGPT direto na Content Factory

## Conectar e produzir

Execute `scripts/setup.ps1` e `scripts/dev.ps1`; abra http://127.0.0.1:3000/settings.

1. Em Text provider, escolha ChatGPT plan - direct connection. Instalacoes novas usam esse provider; instalacoes anteriores preservam sua escolha Codex ate uma troca explicita.
2. Clique Continue with ChatGPT. O backend abre o navegador local quando possivel; Open official authorization manually oferece o mesmo fluxo caso a abertura falhe.
3. Autorize a Content Factory e o uso do plano. Volte a Settings: CONNECTED indica identidade e permissoes validadas, nao inferencia testada.
4. Clique Refresh model catalog e escolha um modelo retornado pela conta. Nenhum modelo e inventado ou escolhido automaticamente.
5. Opcionalmente marque o consentimento de consumo e clique Test text generation. Esse teste realiza uma geracao textual minima e consome o limite do plano. Apenas resposta concluida e JSON validado habilitam o indicador de inferencia verificada. Cancel text test interrompe o pedido.
6. Crie uma producao. O indicador do workspace mostra provider, conta e modelo. A fila salva somente esses identificadores no checkpoint `_ai_selection`, sem tokens.

Roteiro, storyboard, revisoes e metadados usam o mesmo provider. O compositor 2.5D, Piper/audio importado, arquivos, revisao por hash e publicacao continuam independentes. Esse login nao e acesso programatico a geracao de imagens ou videos.

Se o botao exibir **Unsupported platform**, atualize a aplicacao e reinicie o backend: esse erro vinha de um conflito de ordem entre rotas locais, antes de qualquer pedido de autorizacao a OpenAI. A rota especifica ChatGPT agora e registrada antes da rota generica das outras plataformas, com teste pelo aplicativo FastAPI montado e pelo callback loopback real. As chamadas externas nesses testes usam somente fixtures, sem consumir o plano.

O System doctor agora acompanha a prontidao do provider escolhido: DISCONNECTED exige login, WAITING_FOR_MODEL exige escolher modelo, STORAGE_UNAVAILABLE exige configurar o vault. READY confirma conexao/modelo configurados; o teste de inferencia continua separado. Se um modelo selecionado desaparecer do catalogo, sua verificacao anterior e invalidada.

## Contas, reconexao e retomada

Contas salvas possuem rotulos distintos mesmo com email igual. Use account troca explicitamente a conexao; Reconnect reutiliza seu registro e verifica novamente sua identidade. Uma tentativa incompleta nao substitui a conta ativa. Cancel authorization encerra o listener e preserva a conexao anterior.

Producao sem autorizacao para em WAITING_FOR_AUTH. Reautorize a mesma conta e use Resume na fila; checkpoints concluidos sao preservados. WAITING_FOR_MODEL exige modelo valido; WAITING_FOR_PLATFORM_APPROVAL indica permissao insuficiente; WAITING_FOR_LIMIT exige verificar o uso e retomar mais tarde, sem loop automatico de retries nem troca de conta para contornar limites. Falhas transitorias possuem tentativas limitadas e backoff; Retry-After e respeitado. Edicoes que alteram a renderizacao continuam invalidando aprovacao.

Uma producao ja vinculada nao acompanha silenciosamente a escolha global de provider/modelo. Para alterar uma tarefa parada, abra Script/Storyboard e clique Use current text selection for this waiting job. Isso e explicito e preserva checkpoints e o historico da escolha anterior. Conteudo concluido pode ter sido produzido pelo modelo anterior.

Disconnect invalida a geracao daquela conexao e limpa os tokens locais. A interface diferencia revogacao remota confirmada de desconexao apenas local; no segundo caso, use tambem as configuracoes do ChatGPT. Nao ha fallback para API key, cobranca por API ou conta alternativa.

## Seguranca e protocolo

A Content Factory usa o registro dinamico documentado com sua propria identidade, `agent_name_hint=Content Factory` e um `ext_agent_host_id` estavel. O `client_id` emitido fica associado a identidade validada. Nao utiliza o client_id do My-Code-Agent nem le cookies ou credenciais Codex.

Cada tentativa tem state, nonce e PKCE S256 novos e um listener temporario em 127.0.0.1, porta disponivel e caminho /auth/callback. A mesma URI exata e enviada na autorizacao e na troca. Apenas GET, host/caminho/state corretos e parametros sem duplicacoes sao aceitos. A tentativa e consumida uma unica vez. O prazo padrao e cinco minutos e o listener e encerrado no cancelamento, timeout ou shutdown.

PyJWT/cryptography verificam assinatura com JWKS, issuer, audience, exp/iat, nonce, azp quando aplicavel e at_hash quando presente. Os scopes efetivamente concedidos sao validados. ID tokens retidos ficam apenas no vault; a aplicacao usa login_hint de email e omite id_token_hint nas URLs expostas a JavaScript.

Tokens ficam no slot chatgpt do vault existente: DPAPI vinculado ao usuario no Windows, ou backend seguro do sistema em outros sistemas. Nao ha fallback em texto puro. O registro e atomico, e FileLock coordena refresh entre threads e processos. Credenciais nao entram em .env, SQLite de projetos, respostas HTTP, logs ou armazenamento do navegador. Sem vault seguro, a API e as demais funcoes continuam disponiveis e a conexao informa STORAGE_UNAVAILABLE.

Inferencia usa somente POST https://api.openai.com/v1/responses, com Bearer OAuth no backend, store=false, stream=true e contexto completo em input. O catalogo vem de GET https://api.openai.com/v1/models. Nao ha ferramentas nem parametros incompativeis com o preview. SSE possui decodificacao UTF-8 incremental estrita e limites de tamanho; EOF sem conclusao, erros, recusa e respostas incompletas nunca sao sucesso. A conclusao exige response.completed com status completed e conteudo textual valido. JSON e solicitado no prompt, validado pelos schemas Pydantic reais e corrigido no maximo uma vez; nao se presume suporte de JSON Schema estrito nessa rota.

## Configuracao e limites

- AI_PROVIDER=chatgpt: recomendado para instalacoes novas. AI_PROVIDER=codex: compatibilidade explicita. A preferencia salva em Settings tem precedencia. Sem AI_PROVIDER, uma configuracao legada explicita CODEX_PROVIDER preserva Codex; jobs legados sem marcador tambem continuam Codex.
- CHATGPT_LOGIN_TIMEOUT_SECONDS=300: inteiro de 1 a 600 segundos.
- CODEX_TIMEOUT_SECONDS=300: prazo total de geracao textual, compartilhado com o provider direto. Operacoes OAuth/catalogo possuem timeout HTTP de 15 segundos.
- CODEX_MAX_CONCURRENT_JOBS=1: processamento textual sequencial; fila possui lease SQLite e o teste explicito usa o mesmo limite do provider direto.
- Nenhuma OPENAI_API_KEY, client secret ou token manual e necessario. Google/YouTube/TikTok mantem seus proprios parametros e slots.

O catalogo nao garante acesso efetivo ou geracao ilimitada. Elegibilidade, modelos e limites pertencem a conta/organizacao e podem variar durante o preview. Uma inferencia concluida confirma apenas aquele pedido/modelo. Consulte o uso no ChatGPT.

## Callback bloqueado, containers e sessoes remotas

O navegador precisa alcancar o loopback da maquina que executa o backend. Use primeiro Windows local, no mesmo usuario do vault. Feche uma tentativa antiga e clique novamente para obter uma porta livre. Nao substitua 127.0.0.1 por localhost, nao altere o caminho e nao copie tokens. Em container ou sessao remota, loopback e vault podem pertencer a outro ambiente: esse fluxo exige que o navegador alcance o callback e que haja armazenamento seguro naquele runtime. Nao existe fallback para scraping, cookies ou credenciais do host.

## Codex opcional

Para a compatibilidade existente, selecione Codex em Settings; mantenha os comandos `codex login` e `codex login status`. `scripts/setup.ps1 -InstallCodexSdk` instala opcionalmente o SDK. `-SkipCodexSdk` continua aceito. O provider direto nao inicia subprocessos Codex e nao depende desses pacotes. Detalhes em CODEX_AUTH.md.

## Referencias e proveniencia

Documentacao oficial consultada em 2026-10-26:
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
- https://developers.openai.com/siwc/website (validacao OIDC, nao o registro de cliente comercial)

Base Content Factory: 1e455b8d57b7d1738de10281d769e9235e070233. Referencia de comportamento My-Code-Agent: 9f2212aebff6baecc7edd54be81d04e4d41459a4 (chatgpt.ts, chatgpt-store.ts, providers/chatgpt.ts, providers/chatgpt-stream.ts, routes/chatgpt.ts, testes e docs/CHATGPT_E_MODELOS_LOCAIS.md).

Nao foi encontrada uma licenca de reutilizacao na arvore da referencia inspecionada. Nenhum codigo TypeScript foi copiado ou traduzido; esta implementacao Python foi escrita a partir do contrato oficial. Diferencas deliberadas: vault DPAPI/backend seguro em vez de arquivo JSON de tokens; nenhuma ferramenta de programacao; somente texto estruturado; o compositor audiovisual existente permanece independente.
