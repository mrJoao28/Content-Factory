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
