# Pipeline

`DRAFT -> SCRIPTING -> STORYBOARDING -> ASSET_CHECK -> AUDIO_GENERATION -> RENDERING -> TECHNICAL_VALIDATION -> HUMAN_REVIEW -> APPROVED`.

Upload/planejamento remotos possuem registros proprios; o projeto pode avancar para PUBLICATION_PREPARATION, SCHEDULED ou PUBLISHED quando ha evidencia. DRIVE_UPLOAD e estados de espera fazem parte do contrato; a entrega externa e uma acao explicita, independente da fila de render.

Os papeis sequenciais sao Creative Director, Script Writer, Storyboard Planner, Visual Director, Animation Planner, Quality Reviewer e Publishing Assistant. Compartilham provider, contexto, biblioteca e resultados anteriores. Cada resultado e validado e checkpointado. Os diretores visuais/de animacao revisam comandos; nao executam codigo gerado.

O roteirista deve dividir a historia em beats adequados a duracao. O storyboard usa cenas de no maximo 60s; episodios longos contem varias cenas. A soma precisa corresponder ao alvo. A velocidade de TTS pode ser configurada pela classe Piper; a UI usa a velocidade padrao. Se audio exceder a cena, a tarefa aguarda ajuste, sem cortar narracao silenciosamente.

Assets essenciais ausentes geram WAITING_FOR_ASSETS e lista de solicitacoes no checkpoint. Importe PNG ou substitua no storyboard por geometria adequada. Expressoes podem apontar para PNGs diferentes; quatro estados sao suportados pelo schema: happy, surprised, curious, sad. Series e personagens so sao reutilizados quando selecionados/contextualizados.

Piper gera WAV por cena, cacheado por texto/voz/mtime/velocidade. Pausas e preenchimento mantem limites de cena. Audio externo precisa coincidir com a duracao total dentro de um segundo. O compositor produz frames RGB via Pillow e envia ao FFmpeg sem carregar o video inteiro na RAM. FFmpeg normaliza e exporta AAC/H264. Importe musica/efeitos licenciados na Asset Library e configure o mix em Review Studio: volume de narracao, musica em loop e cues de efeitos com tempo/volume. Alterar mix ou importar narracao cria nova revisao.

A qualidade tecnica verifica codecs, tamanho, fps, duracao, audio audivel, pico e decodificacao completa. Essa verificacao nao avalia expressividade artistica. Engineering registra sempre uma necessidade de verificacao humana das fontes; os links do modelo nao sao tratados como evidencias automaticamente verificadas.

Pause/cancel sao persistidos e observados entre etapas e por frame. Um trabalho parado pode retomar checkpoints. Falhas transitorias tem ate tres retries com backoff; erro deterministico nao entra em loop infinito. Restart espera expirar o lease do processo antigo. Arquivos temporarios do Codex e renders parciais sao limpos; cache de voz e artefatos finais sao preservados.

Rejeicao humana mantem HUMAN_REVIEW. Editar cria revisao, descarta aprovacao e exige novo render. Antes de qualquer entrega o hash do arquivo real e comparado com o aprovado. Planejar nao publica; confirmar upload e uma acao separada.

Templates infantis: walk, jump, observe, expression, floating, parallax, magic, sparkle. Templates de engenharia: exploded, layers, arrows, fluid, gears, highlight, rotation, comparison, sequence. Sao diagramas/animacao 2.5D. O template Blender opcional e um script confiavel do repositorio; scripts arbitrarios nao sao aceitos.

## Conexao textual e retomada

Cada nova producao registra provider, conexao e modelo selecionados, sem tokens. A interface exibe essa selecao; alterar o padrao em Settings nao troca silenciosamente a conta de um job existente. Jobs antigos continuam usando Codex por compatibilidade. O usuario pode aplicar explicitamente a selecao atual a uma tarefa aguardando, mantendo checkpoints concluidos.

Falta ou expiracao de autorizacao usa WAITING_FOR_AUTH; permissao insuficiente usa WAITING_FOR_PLATFORM_APPROVAL; limite do plano usa WAITING_FOR_LIMIT; modelo indisponivel usa WAITING_FOR_MODEL. Esses estados aguardam intervencao e Resume, sem repeticao infinita. Erros transitorios respeitam tentativas limitadas e Retry-After. Reconectar permite retomar a etapa pendente sem repetir os resultados ja persistidos. Cancelar ou trocar a conexao interrompe geracoes daquela sessao. A revisao humana e o hash aprovado continuam obrigatorios para entrega.
