# Autenticacao ChatGPT / Codex

Instale `npm install -g @openai/codex`, execute `codex login` e depois `codex login status`. O botao Connect ChatGPT inicia o mesmo login oficial. Complete a janela do navegador. Se ela nao abrir, execute o comando no PowerShell. Login por dispositivo (`codex login --device-auth`) depende da disponibilidade da conta/organizacao.

O backend verifica o status pelo CLI e aceita apenas autenticacao ChatGPT. Nao abre auth.json, nao le cookies e nao pede OPENAI_API_KEY. O SDK oficial reutiliza autenticacao gerenciada pelo Codex. O plano ChatGPT precisa dar acesso ao Codex e continua sujeito a limites; Plus nao significa geracao ilimitada.

Fontes oficiais verificadas: [SDK](https://developers.openai.com/codex/sdk), [autenticacao](https://developers.openai.com/codex/auth), [exec nao interativo](https://developers.openai.com/codex/noninteractive), [configuracao](https://developers.openai.com/codex/config-reference).

## Provider e compatibilidade

`CODEX_PROVIDER=auto` prefere o SDK quando instalado e quando o app-server local anuncia `--ignore-user-config`. Caso contrario usa o CLI oficial `codex exec --json --output-schema`. O runtime 0.164.0 deste ambiente suporta esse isolamento no comando exec, mas nao no app-server; por isso usa-se a alternativa oficial. Nenhuma biblioteca Python de terceiros se passa pelo SDK oficial.

O adapter SDK usa exclusivamente Codex, CodexConfig, thread_start, thread.turn, output_schema e stream/run documentados no repositorio oficial. Antes de iniciar verifica as capacidades necessarias. `CODEX_PROVIDER=sdk` falha explicitamente se a versao nao permitir o isolamento; nao reduz protecoes silenciosamente. `CODEX_PROVIDER=cli` forca a alternativa.

O CLI executa em diretorio temporario, sem config/rules do usuario; shell, plugins, apps, browser, computer-use e imagem ficam desabilitados. O perfil de permissoes permite apenas leitura do diretorio temporario e nega o restante do filesystem. O trafego do proprio provider para inferencia continua sendo gerenciado pelo Codex; nenhum comando de roteiro ganha acesso a rede.

Cada papel recebe contexto JSON completo. Resultados sao validados por Pydantic e salvos como checkpoints; nao se depende de memoria oculta do modelo para recuperar tarefas. Sessoes de geracao sao efemeras por isolamento. Historico de execucao fica em JobEvent e no checkpoint, sem tokens ou raciocinio interno.

Cancelamento/timeout encerram o processo do provider. Erros transitorios retornam para a fila com backoff limitado. Sessao expirada retorna WAITING_FOR_AUTH; execute login novamente e Resume. Limites de uso nao sao contornados.

Nao ha acesso programatico a geracao de imagens/videos do ChatGPT Plus. Importe PNGs criados manualmente ou use os templates geometricos locais.
