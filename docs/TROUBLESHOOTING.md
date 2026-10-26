# Diagnostico

Execute `scripts/doctor.ps1` ou abra Settings > Run checks. READY de uma ferramenta significa que sua verificacao local passou, nao que todo o pipeline/conta tem permissao.

| Sintoma | Acao |
|---|---|
| AUTH_REQUIRED / WAITING_FOR_AUTH | Execute codex login no mesmo usuario/processo, depois Verify login e Resume. A sessao do app Codex de outro usuario sandbox nao e automaticamente compartilhada. |
| WinError 10013 no pip/npm | Ambiente bloqueou acesso de rede. Execute setup em terminal autorizado com conectividade; nao invente credenciais nem desabilite protecoes. |
| Python Store acesso negado | Instale Python x64 convencional; confira Get-Command python e python --version. |
| FFmpeg nao encontrado | Configure caminho absoluto em .env ou PATH. O build do Playwright so suporta codecs reduzidos. |
| FFprobe ausente | Instale o pacote completo; imageio-ffmpeg pode fornecer apenas encoder. |
| WAITING_FOR_ASSETS | Consulte checkpoint/erro. Importe recursos essenciais ou narracao; configure Piper/voz e retome. |
| Narracao maior que cena | Ajuste roteiro, duracao das cenas ou velocidade de TTS; nao reduza audio cegamente. |
| FAILED em technical validation | Abra relatorio. Verifique duracao, codecs, volume e render. Audio silencioso e bloqueado. |
| OAuth redirect_uri_mismatch | Compare host, porta e caminho com o cliente registrado. TikTok Web exige HTTPS. |
| Google pasta nao listada | drive.file ve arquivos criados/autorizados ao app. Use raiz criada pelo app; Picker ainda nao foi integrado. |
| YouTube 403/429 | Confira API habilitada, escopo, quota e auditoria no projeto. Nao afirme publicacao sem status remoto. |
| TikTok video.publish recusado | Aprovacao/escopo/conta precisam permitir Direct Post. Inbox/manual sao alternativas. |
| NEEDS_RECONCILIATION | Upload teve resposta ambigua. Consulte status remoto antes de outra tentativa. Nao apague o registro para forcar duplicacao. |
| Nao consigo editar | Pause e aguarde o worker liberar o lease. Renovacao ocorre a cada 10s; lease expira em 45s. |
| Banco bloqueado | Use disco local e um processo API; WAL/busy_timeout ja estao ativos. Evite sync de nuvem no arquivo SQLite aberto. |
| Browser nao inicia nos testes | Execute npx playwright install chromium no diretorio apps/web e confira politicas locais. |
| .git/index.lock: Permission denied | Sandbox atual protege .git. Execute commits como proprietario fora dessa restricao; nenhum commit foi fabricado. |
| Ruff/Alembic indisponivel | Instale .[dev] com conectividade. Check de sintaxe Python nao substitui lint nem migracao Alembic. |

Testes usam bancos e diretorios exclusivos. Nao altere DATABASE_URL para seu banco real ao executar testes destrutivos. Os exemplos de .env nao sao segredos reais.


## npm ci / missing optional platform packages

The committed frontend lockfile contains the platform-specific optional dependencies (Next SWC, Tailwind Oxide, lightningcss, Sharp and Rolldown). Rerun `scripts/setup.ps1` with the corrected lockfile. Do not remove optional dependencies or regenerate a partial lockfile from the installed Windows-only node_modules tree.

If npm reports EPERM unlinking next-swc.win32-x64-msvc.node, stop the running frontend with Ctrl+C before running setup again. A running Next.js process can hold native modules open on Windows. The Python dependency installation does not need to be undone.

The Reflex/Starlette warning describes a package outside this project's virtual environment when system-site-packages is enabled. Reflex is not an application dependency. For a new installation, setup creates an isolated virtual environment; an existing environment is preserved.


## EPERM on SWC, port 8000 occupied, or next command missing

A previous development process may still hold the SWC binary and port 8000. An interrupted npm ci can also remove the Next command shim. Recover with `scripts/setup.ps1 -StopRunning`, then `scripts/dev.ps1`. The stop helper verifies the repository path and process role before targeting a process. If Windows denies inspection or stopping, use Ctrl+C in the original terminal. The backend's original startup error is now printed before cleanup; taskkill stderr is captured rather than raised as a PowerShell NativeCommandError.
