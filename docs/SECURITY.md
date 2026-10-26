# Seguranca local

- API nativa em 127.0.0.1, host allowlist, CORS restrito a web local e cabecalho X-Factory-Client nas mutacoes reduzem CSRF/DNS rebinding. Nao e um servico multiusuario autenticado; nao publique na rede.
- Prompts e roteiros sao dados JSON, nunca shell, Python, expressoes eval ou filtros FFmpeg arbitrarios. O motor aceita apenas comandos tipados e limites de tempo/tamanho/keyframes/camadas.
- Codex opera em workspace temporario com permissoes restritas, ferramentas desabilitadas e sem configuracao/plugins do usuario. Auth continua sendo do proprio CLI. SDK sem isolamento equivalente nao e ativado automaticamente.
- Subprocessos usam listas de argumentos e shell=False. Cancelamento termina processos pertencentes a esta aplicacao. Blender so recebe templates confiaveis explicitamente permitidos.
- Arquivos sao resolvidos contra roots e rejeitam traversal/caminhos absolutos. Importacao usa nome UUID, limite por stream, PNG decodificavel ate 4096px e audio inspecionado pelo FFprobe. SVG nao e servido nem executado.
- OAuth usa state aleatorio e expiravel, PKCE Google, validacao do provider e refresh/revogacao oficiais. O vault DPAPI e vinculado ao usuario Windows. Nao transfira os arquivos cifrados esperando que outro usuario consiga usa-los.
- .env, data/, output/, auth.json e modelos de voz estao ignorados no Git. O segredo OAuth do cliente ainda e texto no .env: proteja a pasta com permissoes do SO e backups apropriados. Nao ha OpenAI API key.
- Nunca habilite logs HTTP com query strings nos callbacks OAuth. Os comandos recomendados usam --no-access-log. Erros de plataforma nao incluem corpos com tokens. SSE publica eventos de estagio, sem raciocinio interno nem saida bruta de ferramentas.
- Aprovacao esta vinculada a revisao e SHA-256 do artefato. Alterar arquivo ou conteudo invalida publicacao. YouTube audience vem do canal persistido. Cada acao remota exige confirmacao.
- URLs de upload sao verificadas contra hosts oficiais. Links cientificos nao sao buscados automaticamente, evitando SSRF. Sem evidencias, ha flag e revisao humana obrigatoria.

Limites: um processo local malicioso executando como o mesmo usuario pode ler .env ou solicitar operacoes; este projeto nao e uma fronteira contra malware local. Sem autenticacao multiusuario/TLS propria, o callback TikTok publico deve expor apenas a rota exata e nao toda a API. O Compose nao configura keyring Linux nem valida producao.
