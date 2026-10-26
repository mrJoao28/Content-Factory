# Revisão do login e da execução — 26/10/2026

Base analisada: `acb36ed0f90eb124b8ac74f37d3a82dfe8a5a45e`.

## Erro observado e correções

| Problema | Evidência | Correção |
|---|---|---|
| `Unsupported platform` em Continue with ChatGPT | POST real a `/auth/chatgpt/connect` retornava 422 antes de iniciar OAuth. O router genérico `/auth/{platform}/connect` era registrado primeiro e enviava `chatgpt` à integração Google/TikTok. | Registrar o router específico antes do router genérico. O teste usa o aplicativo FastAPI montado, inicia o listener e conclui o callback local; somente HTTP externo e credenciais de teste são simulados. |
| System doctor mostrava provider READY mesmo desconectado ou sem modelo | A prontidão textual era preenchida com READY incondicionalmente. | Derivar o estado da conexão e do modelo selecionados. READY continua distinto de inferência verificada. |
| Verificação de inferência ficava válida depois da remoção do modelo | Ao atualizar um catálogo vazio, o modelo selecionado era removido mas `inference_verified` permanecia true. | Invalidar a verificação quando o modelo selecionado desaparece. |
| Calendário dependia da base IANA do sistema | `zoneinfo` precisa de uma base externa; instalações Windows normalmente não a incluem. | Declarar `tzdata` e testar America/Manaus sem acesso à base do sistema operacional. |
| Caminhos Windows eram aceitos como relativos no Linux | A suíte demonstrou que `C:/Windows/win.ini` não era rejeitado pelo validador de caminhos em Linux. | Rejeitar drives e UNC Windows antes de resolver caminhos de armazenamento. |
| Runner de navegador ignorava a venv no Linux | O runner procurava somente `.venv/Scripts/python.exe` e caía no Python global. | Procurar também `.venv/bin/python` conforme a plataforma. |

O erro da imagem é um bug de roteamento local. Não depende da senha, do plano ChatGPT, de API key ou de permissões na OpenAI.

## Verificações executadas

- Instalação limpa das dependências Python e `npm ci`: concluídas. O bloqueio anterior do lockfile não foi reproduzido na revisão atual.
- Pytest: **102 passaram; 6 ignorados** por dependerem de Windows/DPAPI/PowerShell.
- Ruff: aprovado.
- Testes web Vitest: **6 passaram**.
- TypeScript e build de produção Next.js: aprovados.
- Inicialização real dos processos Uvicorn e Next.js em portas locais isoladas: `/health` e `/settings` responderam HTTP 200. A página de Settings contém o login ChatGPT; a rota de status da API respondeu sem depender do Codex ou de API key.
- OIDC discovery público da OpenAI: issuer, endpoints de autorização/token/JWKS/revogação e algoritmo anunciados correspondem aos usados pela implementação. Nenhuma autorização de conta foi iniciada nessa consulta.
- A suíte foi isolada das variáveis de proxy da máquina: os pedidos externos usam transportes de teste explícitos e os callbacks são locais. Proxies de produção não foram alterados.

## Limites desta validação

Não houve login real na conta do proprietário, inferência com o plano, consumo de créditos ou publicação. Os testes usam respostas externas controladas, assinatura JWT verificada e callback HTTP local real. A autorização no navegador e uma inferência real continuam necessárias para confirmar elegibilidade/acesso da conta.

Os testes nativos de Windows e DPAPI não foram executados neste ambiente Linux. O teste de fuso cobre a ausência da base IANA, mas não substitui esses testes nativos.

Não foi possível executar Playwright: o download do Chromium retornou arquivos inválidos/truncados. Isso não é uma falha observada da interface; o build, a tipagem, os testes web e a resposta HTTP foram verificados separadamente. Os testes de interface anteriores que simulam a rota de login não substituem o novo teste de integração pelo aplicativo real.

## Após atualizar

1. Pare o processo antigo com Ctrl+C no terminal que executa `scripts/dev.ps1`.
2. Atualize para a revisão corrigida e rode `scripts/setup.ps1`. Se houver processo antigo mantendo SWC/portas ocupados, use `scripts/setup.ps1 -StopRunning`.
3. Execute `scripts/dev.ps1` e abra Settings em `http://127.0.0.1:3000/settings`.
4. Selecione **ChatGPT plan - direct connection**, autorize, atualize o catálogo e escolha um modelo. Instalações antigas podem preservar a seleção Codex.
5. Para verificar acesso efetivo, faça o teste textual com consentimento de uso do plano. Depois retome a produção pendente.

O pipeline de vídeo continua exigindo recursos visuais e Piper/voz ou narração importada. A autenticação não substitui essas configurações nem adiciona geração 3D.
