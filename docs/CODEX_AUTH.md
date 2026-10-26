# Autenticacao textual: ChatGPT direto e Codex opcional

O fluxo recomendado para novas instalacoes e o login proprio da Content Factory, sem CLI/SDK nem API key. Veja [CHATGPT_DIRECT.md](CHATGPT_DIRECT.md). O restante deste guia descreve somente o provider Codex de compatibilidade, selecionado explicitamente em Settings.

# Autenticacao ChatGPT / Codex

Instale `npm install -g @openai/codex`, execute `codex login` e depois `codex login status`. O botao Connect ChatGPT inicia o login pelo SDK oficial e mostra um link para abrir no navegador. O CLI verifica a sessao salva. Login por dispositivo (`codex login --device-auth`) depende da disponibilidade da conta/organizacao.

O backend verifica o status pelo CLI e aceita apenas autenticacao ChatGPT. Nao abre auth.json, nao le cookies e nao pede OPENAI_API_KEY. O SDK oficial reutiliza autenticacao gerenciada pelo Codex. O plano ChatGPT precisa dar acesso ao Codex e continua sujeito a limites; Plus nao significa geracao ilimitada.

Fontes oficiais verificadas: [SDK](https://developers.openai.com/codex/sdk), [autenticacao](https://developers.openai.com/codex/auth), [exec nao interativo](https://developers.openai.com/codex/noninteractive), [configuracao](https://developers.openai.com/codex/config-reference).

## Provider e compatibilidade

`CODEX_PROVIDER=auto` prefere o SDK quando instalado e quando o app-server local anuncia `--ignore-user-config`. Caso contrario usa o CLI oficial `codex exec --json --output-schema`. O runtime 0.164.0 deste ambiente suporta esse isolamento no comando exec, mas nao no app-server; por isso usa-se a alternativa oficial. Nenhuma biblioteca Python de terceiros se passa pelo SDK oficial.

O adapter SDK usa exclusivamente Codex, CodexConfig, thread_start, thread.turn, output_schema e stream/run documentados no repositorio oficial. Antes de iniciar verifica as capacidades necessarias. `CODEX_PROVIDER=sdk` falha explicitamente se a versao nao permitir o isolamento; nao reduz protecoes silenciosamente. `CODEX_PROVIDER=cli` forca a alternativa.

O CLI executa em diretorio temporario, sem config/rules do usuario; shell, plugins, apps, browser, computer-use e imagem ficam desabilitados. O perfil de permissoes permite apenas leitura do diretorio temporario e nega o restante do filesystem. O trafego do proprio provider para inferencia continua sendo gerenciado pelo Codex; nenhum comando de roteiro ganha acesso a rede.

Cada papel recebe contexto JSON completo. Resultados sao validados por Pydantic e salvos como checkpoints; nao se depende de memoria oculta do modelo para recuperar tarefas. Sessoes de geracao sao efemeras por isolamento. Historico de execucao fica em JobEvent e no checkpoint, sem tokens ou raciocinio interno.

Cancelamento/timeout encerram o processo do provider. Erros transitorios retornam para a fila com backoff limitado. Sessao expirada retorna WAITING_FOR_AUTH; execute login novamente e Resume. Limites de uso nao sao contornados.

Nao ha acesso programatico a geracao de imagens/videos do ChatGPT Plus. Importe PNGs criados manualmente ou use os templates geometricos locais.


## Login that stays pending after browser sign-in

The app uses the installed official Python SDK for the sign-in ceremony and the official CLI to confirm the saved ChatGPT session. No auth file is opened by the app. In Settings, Connect ChatGPT returns an official sign-in link; status refreshes while pending. Use device code when the localhost callback is blocked. Enable device-code authentication in ChatGPT security settings when required.

An existing confirmed ChatGPT login is reused. Startup has a 30-second limit; browser/device login has a five-minute limit. Cancel terminates only the app-owned login process and its children; it does not log out or revoke an existing session. API shutdown also cleans up pending login processes. Failures are displayed without raw SDK exception payloads.

If a PowerShell `codex login` appears stuck after signing in, open another PowerShell window under the same Windows user and run:

```powershell
codex login status
```

If it confirms ChatGPT, the login is already saved: cancel the old waiting command with Ctrl+C, then click Verify login. Otherwise cancel the old attempt and use:

```powershell
codex login --device-auth
codex login status
```

A different Windows user, CODEX_HOME or credential-store configuration can explain why two processes see different sessions. Run the backend from the same Windows account/environment where login succeeded. Do not copy tokens or credential files. If the Python SDK is missing, install it using `.venv\Scripts\python.exe -m pip install openai-codex`; terminal CLI login remains available.

Official OpenAI documentation: https://learn.chatgpt.com/docs/auth and https://learn.chatgpt.com/docs/codex-sdk


### SDK runtime compatibility

The login adapter uses the runtime bundled with `openai-codex`, rather than overriding it with a globally installed CLI version. In this environment, the SDK account check failed with TransportClosedError when forced to use the global CLI 0.164.0, and succeeded with its bundled 0.163.0 runtime. This check verified SDK transport and account-status retrieval, not successful account authentication. Inference still uses the capability-checked provider described above.
