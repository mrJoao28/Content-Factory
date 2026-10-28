# Guia completo do .env

Music Studio não exige variável secreta nova. Configure o serviço de canto opcional
exclusivamente no vault pela interface, nunca neste arquivo. Importação e instrumental
local funcionam sem serviço pago: [guia musical](MUSIC_STUDIO.md).

## Motor 3D local opcional

`BLENDER_PATH` deve apontar para o executável oficial Blender 4.5 ou 5.2 LTS. Instale pelo
[site oficial](https://www.blender.org/download/), selecione o caminho local e
valide com `& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --version`.
Prefira barras `/` no `.env`, pois `\b` em aspas duplas pode virar backspace.
Sem esse executável, projetos 2D continuam funcionando e projetos 3D informam o requisito.
Não coloque scripts, tokens ou parâmetros de shell na variável.

| Nome | Padrão | Obrigatoriedade e validação | Finalidade / erro comum |
|---|---|---|---|
| `BLENDER_THREADS` | `2` | Opcional; inteiro 1–8 | Threads CPU. Valores altos podem travar a interface em notebooks. |
| `BLENDER_TIMEOUT_SECONDS` | `7200` | Opcional; inteiro 30–86400 | Prazo de um processo de render. Resume mantém frames válidos. |
| `BLENDER_DISK_BUDGET_MB` | `4096` | Opcional; inteiro 128–65536 | Teto conservador RGB de frames + folga; 1080p pode exigir ajuste explícito. |

São opções locais, sem credenciais ou cobrança. Consulte as opções de threads na
[documentação oficial](https://docs.blender.org/manual/en/4.5/advanced/command_line/arguments.html).
Copie os exemplos acima somente se desejar modificar os padrões e reinicie a API.
`doctor.ps1 -Smoke3D` verifica render real; detectar a versão não comprova renderização.
Mais instruções, limites e recuperação: [produção 3D](LOCAL_3D.md).

Copie `.env.example` para `.env` apenas se ele ainda nao existir. Reinicie a API depois de alterar configuracao. Caminhos relativos sao da raiz do projeto. Aspas duplas protegem caminhos Windows com espacos; prefira `/` nos caminhos. Nao existem OPENAI_API_KEY nem cookies nesta configuracao.

Segredos do cliente ficam apenas no .env ignorado pelo Git. Tokens de usuario ficam em DPAPI (Windows) ou keyring do SO. Nao coloque segredos em NEXT_PUBLIC_*: essas variaveis vao para o navegador.

Para cada variavel abaixo, o exemplo nao contem credenciais reais.

## APP_ENV

| Campo | Configuracao |
|---|---|
| Nome | `APP_ENV` |
| Servico | local |
| Finalidade | Modo informativo development/production/test. |
| Obrigatoriedade | Opcional |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Escolha development para desenvolvimento. |
| Exemplo sem segredo | `development` |
| Validacao | Settings aceita somente os modos declarados. |
| Erros comuns | Modo desconhecido causa validacao. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## APP_HOST

| Campo | Configuracao |
|---|---|
| Nome | `APP_HOST` |
| Servico | local |
| Finalidade | Interface local suportada. |
| Obrigatoriedade | Obrigatorio manter loopback |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Mantenha 127.0.0.1. |
| Exemplo sem segredo | `127.0.0.1` |
| Validacao | Settings rejeita qualquer outro host. |
| Erros comuns | Expor a rede nao e suportado. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## API_PORT

| Campo | Configuracao |
|---|---|
| Nome | `API_PORT` |
| Servico | local |
| Finalidade | Porta do backend e diagnostico. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Escolha porta livre; passe o mesmo valor a dev.ps1 -ApiPort. |
| Exemplo sem segredo | `8000` |
| Validacao | Abra /health na porta selecionada. |
| Erros comuns | Porta ocupada; redirect OAuth divergente. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## WEB_PORT

| Campo | Configuracao |
|---|---|
| Nome | `WEB_PORT` |
| Servico | local |
| Finalidade | Porta da web e allowlist CORS. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Use dev.ps1 -WebPort com o mesmo valor. |
| Exemplo sem segredo | `3000` |
| Validacao | A web deve abrir e acessar /channels. |
| Erros comuns | CORS falha se a porta divergir. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## DATABASE_URL

| Campo | Configuracao |
|---|---|
| Nome | `DATABASE_URL` |
| Servico | local |
| Finalidade | Banco SQLite persistente. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Escolha arquivo local; execute alembic upgrade head. |
| Exemplo sem segredo | `sqlite:///./data/content_factory.db` |
| Validacao | Doctor verifica conexao e WAL. |
| Erros comuns | Diretorio ausente, arquivo bloqueado ou database locked. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## STORAGE_ROOT

| Campo | Configuracao |
|---|---|
| Nome | `STORAGE_ROOT` |
| Servico | local |
| Finalidade | Audio, imports, temporarios e vault. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Escolha diretorio local gravavel. |
| Exemplo sem segredo | `./data` |
| Validacao | Doctor e importacao validam acesso. |
| Erros comuns | Permissao de escrita insuficiente. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## OUTPUT_DIR

| Campo | Configuracao |
|---|---|
| Nome | `OUTPUT_DIR` |
| Servico | local |
| Finalidade | MP4 e artefatos por projeto/revisao. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Reserve espaco em disco local. |
| Exemplo sem segredo | `./output` |
| Validacao | Render e dashboard verificam arquivos reais. |
| Erros comuns | Disco cheio ou antivirus bloqueando arquivo. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## ASSETS_DIR

| Campo | Configuracao |
|---|---|
| Nome | `ASSETS_DIR` |
| Servico | local |
| Finalidade | Biblioteca PNG local. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Escolha diretorio gravavel e importe PNG com direitos. |
| Exemplo sem segredo | `./assets` |
| Validacao | Importe PNG na Asset Library. |
| Erros comuns | Formato invalido ou dimensao maior que 4096. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## DEFAULT_TIMEZONE

| Campo | Configuracao |
|---|---|
| Nome | `DEFAULT_TIMEZONE` |
| Servico | local |
| Finalidade | Fuso IANA inicial do calendario. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Use nome IANA valido; preferencias da interface podem sobrescrever a exibicao. |
| Exemplo sem segredo | `America/Manaus` |
| Validacao | Planeje horario e verifique conversao para UTC. |
| Erros comuns | Fuso desconhecido ou hora inexistente por horario de verao. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## CODEX_AUTH_MODE

| Campo | Configuracao |
|---|---|
| Nome | `CODEX_AUTH_MODE` |
| Servico | codex |
| Finalidade | Metodo de autenticacao exclusivo. |
| Obrigatoriedade | Obrigatorio chatgpt |
| URL oficial | https://developers.openai.com/codex/auth |
| Como obter/configurar | Instale CLI e rode codex login; nao ha segredo a preencher. |
| Exemplo sem segredo | `chatgpt` |
| Validacao | codex login status deve confirmar ChatGPT. |
| Erros comuns | Login API key e rejeitado. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## CODEX_PROVIDER

| Campo | Configuracao |
|---|---|
| Nome | `CODEX_PROVIDER` |
| Servico | codex |
| Finalidade | Selecao auto/cli/sdk com verificacao de capacidades. |
| Obrigatoriedade | Opcional |
| URL oficial | https://developers.openai.com/codex/auth |
| Como obter/configurar | Use auto; CLI oficial e alternativa para SDK incompativel. |
| Exemplo sem segredo | `auto` |
| Validacao | Doctor e uma geracao confirmam acesso. |
| Erros comuns | SDK indisponivel ou sem isolamento; use cli. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## CODEX_PATH

| Campo | Configuracao |
|---|---|
| Nome | `CODEX_PATH` |
| Servico | codex |
| Finalidade | Executavel oficial Codex ou shim npm. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://developers.openai.com/codex/auth |
| Como obter/configurar | npm install -g @openai/codex; use caminho se nao estiver no PATH. |
| Exemplo sem segredo | `codex` |
| Validacao | codex --version e login status. |
| Erros comuns | Shim npm nao resolvido; atualize CLI. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## CODEX_TIMEOUT_SECONDS

| Campo | Configuracao |
|---|---|
| Nome | `CODEX_TIMEOUT_SECONDS` |
| Servico | codex |
| Finalidade | Prazo por papel de IA. |
| Obrigatoriedade | Opcional |
| URL oficial | https://developers.openai.com/codex/auth |
| Como obter/configurar | Ajuste tempo em segundos de acordo com roteiros longos. |
| Exemplo sem segredo | `300` |
| Validacao | Timeout aparece no JobEvent e segue retry limitado. |
| Erros comuns | Prazo curto interrompe geracao longa. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## CODEX_MAX_CONCURRENT_JOBS

| Campo | Configuracao |
|---|---|
| Nome | `CODEX_MAX_CONCURRENT_JOBS` |
| Servico | codex |
| Finalidade | Limite de memoria e uso. |
| Obrigatoriedade | Obrigatorio 1 nesta versao |
| URL oficial | https://developers.openai.com/codex/auth |
| Como obter/configurar | Mantenha 1; outros valores sao rejeitados. |
| Exemplo sem segredo | `1` |
| Validacao | Uma tarefa possui lease de cada vez. |
| Erros comuns | Valor maior que 1 falha em validacao. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## FFMPEG_PATH

| Campo | Configuracao |
|---|---|
| Nome | `FFMPEG_PATH` |
| Servico | ffmpeg |
| Finalidade | Encoder e filtros de audio/video. |
| Obrigatoriedade | Necessario para render |
| URL oficial | https://ffmpeg.org/download.html |
| Como obter/configurar | Instale build completo; coloque bin no PATH ou informe executavel. |
| Exemplo sem segredo | `C:/Tools/ffmpeg/bin/ffmpeg.exe` |
| Validacao | ffmpeg -version; teste real de render. |
| Erros comuns | Build Playwright reduzido nao possui H264/AAC/flite. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## FFPROBE_PATH

| Campo | Configuracao |
|---|---|
| Nome | `FFPROBE_PATH` |
| Servico | ffmpeg |
| Finalidade | Inspecao de streams e duracao. |
| Obrigatoriedade | Necessario para QC/audio |
| URL oficial | https://ffmpeg.org/download.html |
| Como obter/configurar | Use FFprobe do mesmo pacote FFmpeg. |
| Exemplo sem segredo | `C:/Tools/ffmpeg/bin/ffprobe.exe` |
| Validacao | ffprobe -version; Doctor READY apos executar. |
| Erros comuns | imageio-ffmpeg nao inclui necessariamente FFprobe. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## BLENDER_PATH

| Campo | Configuracao |
|---|---|
| Nome | `BLENDER_PATH` |
| Servico | blender |
| Finalidade | Renderizacao de templates Python confiaveis. |
| Obrigatoriedade | Opcional |
| URL oficial | https://www.blender.org/download/ |
| Como obter/configurar | Instale Blender e informe o executavel. |
| Exemplo sem segredo | `C:/Program Files/Blender Foundation/Blender 4.5/blender.exe` |
| Validacao | blender --version; execute apenas template confiavel. |
| Erros comuns | Template exige EEVEE Next; versoes antigas podem falhar. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## PIPER_PATH

| Campo | Configuracao |
|---|---|
| Nome | `PIPER_PATH` |
| Servico | piper |
| Finalidade | CLI TTS local por cena. |
| Obrigatoriedade | Ou audio importado |
| URL oficial | https://github.com/OHF-Voice/piper1-gpl |
| Como obter/configurar | pip install piper-tts no venv; localize piper.exe. |
| Exemplo sem segredo | `C:/AIContentFactory/.venv/Scripts/piper.exe` |
| Validacao | piper --help; gere uma frase inglesa. |
| Erros comuns | Runtime/modelo ausente ou arquitetura incompativel. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## PIPER_VOICE_PATH

| Campo | Configuracao |
|---|---|
| Nome | `PIPER_VOICE_PATH` |
| Servico | piper |
| Finalidade | Modelo ONNX de voz inglesa. |
| Obrigatoriedade | Para Piper |
| URL oficial | https://github.com/OHF-Voice/piper1-gpl |
| Como obter/configurar | Consulte catalogo do Piper, confira licenca e baixe .onnx e .onnx.json juntos. |
| Exemplo sem segredo | `./assets/voices/en_US-lessac-medium.onnx` |
| Validacao | Doctor verifica arquivos; geracao confirma compatibilidade. |
| Erros comuns | Falta .onnx.json, voz nao inglesa ou narracao maior que cena. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## GOOGLE_CLIENT_ID

| Campo | Configuracao |
|---|---|
| Nome | `GOOGLE_CLIENT_ID` |
| Servico | google |
| Finalidade | Identifica cliente Web da aplicacao. |
| Obrigatoriedade | Somente Google OAuth |
| URL oficial | https://console.cloud.google.com/apis/credentials |
| Como obter/configurar | Crie projeto, habilite Drive/YouTube, configure consentimento e cliente Web. |
| Exemplo sem segredo | `example.apps.googleusercontent.com` |
| Validacao | Connect e Verify account devem confirmar identidade. |
| Erros comuns | OAuth client errado ou usuario nao adicionado como tester. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## GOOGLE_CLIENT_SECRET

| Campo | Configuracao |
|---|---|
| Nome | `GOOGLE_CLIENT_SECRET` |
| Servico | google |
| Finalidade | Segredo do cliente Web para exchange/refresh. |
| Obrigatoriedade | Somente Google OAuth |
| URL oficial | https://console.cloud.google.com/apis/credentials |
| Como obter/configurar | Copie do cliente OAuth do proprio projeto para .env local. |
| Exemplo sem segredo | `<preencher-localmente>` |
| Validacao | Conexao conclui callback sem expor segredo. |
| Erros comuns | invalid_client; nunca registrar o valor em logs. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## GOOGLE_REDIRECT_URI

| Campo | Configuracao |
|---|---|
| Nome | `GOOGLE_REDIRECT_URI` |
| Servico | google |
| Finalidade | Callback local compartilhado por Drive e YouTube. |
| Obrigatoriedade | Somente Google OAuth |
| URL oficial | https://console.cloud.google.com/apis/credentials |
| Como obter/configurar | Cadastre a URI exata no cliente Web Google. |
| Exemplo sem segredo | `http://127.0.0.1:8000/auth/google/callback` |
| Validacao | Complete o login no navegador. |
| Erros comuns | redirect_uri_mismatch por porta/host/barra diferentes. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## GOOGLE_DRIVE_FOLDER_ID

| Campo | Configuracao |
|---|---|
| Nome | `GOOGLE_DRIVE_FOLDER_ID` |
| Servico | google |
| Finalidade | Pasta raiz de arquivo. |
| Obrigatoriedade | Opcional |
| URL oficial | https://console.cloud.google.com/apis/credentials |
| Como obter/configurar | Copie o ID entre /folders/ e os parametros da URL do Drive; ou escolha pasta acessivel na web. |
| Exemplo sem segredo | `folder_id_example` |
| Validacao | List folders/Create layout/Upload confirmam acesso. |
| Erros comuns | drive.file nao da acesso a todas as pastas existentes. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## YOUTUBE_CHANNEL_ID

| Campo | Configuracao |
|---|---|
| Nome | `YOUTUBE_CHANNEL_ID` |
| Servico | youtube |
| Finalidade | Canal esperado antes do upload. |
| Obrigatoriedade | Recomendado para evitar canal errado |
| URL oficial | https://developers.google.com/youtube/v3/docs/videos/insert |
| Como obter/configurar | Conecte YouTube, use Verify account e copie items[0].id; confira no Studio. |
| Exemplo sem segredo | `UC_example_channel_id` |
| Validacao | Upload compara canal autenticado com esse ID. |
| Erros comuns | Conta Google possui outro canal/Brand Account. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## TIKTOK_DIRECT_POST_ENABLED

| Campo | Configuracao |
|---|---|
| Nome | `TIKTOK_DIRECT_POST_ENABLED` |
| Servico | tiktok |
| Finalidade | Habilita escopo video.publish e formulario de Direct Post. |
| Obrigatoriedade | Opcional, false por padrao |
| URL oficial | https://developers.tiktok.com/apps/ |
| Como obter/configurar | Obtenha permissao/auditoria; defina true e reconecte OAuth; API ainda valida scopes/creator. |
| Exemplo sem segredo | `false` |
| Validacao | Query creator and permissions deve retornar opcoes reais. |
| Erros comuns | Flag local nao concede aprovacao externa. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## TIKTOK_CLIENT_KEY

| Campo | Configuracao |
|---|---|
| Nome | `TIKTOK_CLIENT_KEY` |
| Servico | tiktok |
| Finalidade | Identifica app registrada. |
| Obrigatoriedade | Somente TikTok OAuth |
| URL oficial | https://developers.tiktok.com/apps/ |
| Como obter/configurar | Crie app no portal e copie Client Key. |
| Exemplo sem segredo | `example_client_key` |
| Validacao | OAuth e Verify account confirmam identidade. |
| Erros comuns | App nao aprovada ou chave errada. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## TIKTOK_CLIENT_SECRET

| Campo | Configuracao |
|---|---|
| Nome | `TIKTOK_CLIENT_SECRET` |
| Servico | tiktok |
| Finalidade | Segredo para exchange/refresh/revogacao. |
| Obrigatoriedade | Somente TikTok OAuth |
| URL oficial | https://developers.tiktok.com/apps/ |
| Como obter/configurar | Copie Client Secret do portal para .env. |
| Exemplo sem segredo | `<preencher-localmente>` |
| Validacao | Callback troca codigo por token protegido no vault. |
| Erros comuns | invalid_client; manter fora de logs e Git. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## TIKTOK_REDIRECT_URI

| Campo | Configuracao |
|---|---|
| Nome | `TIKTOK_REDIRECT_URI` |
| Servico | tiktok |
| Finalidade | Callback Web registrado, obrigatoriamente HTTPS. |
| Obrigatoriedade | Somente TikTok OAuth |
| URL oficial | https://developers.tiktok.com/apps/ |
| Como obter/configurar | Registre URI HTTPS estatica; encaminhe somente o callback ao backend local com Host 127.0.0.1. Consulte TIKTOK_SETUP. |
| Exemplo sem segredo | `https://studio.example.com/auth/tiktok/callback` |
| Validacao | Portal aceita URI e callback conclui state. |
| Erros comuns | HTTP loopback nao e aceito pelo Login Kit Web; nao exponha toda a API. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## RENDER_MAX_CONCURRENT

| Campo | Configuracao |
|---|---|
| Nome | `RENDER_MAX_CONCURRENT` |
| Servico | local |
| Finalidade | Limite de render sequencial. |
| Obrigatoriedade | Obrigatorio 1 nesta versao |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Mantenha 1 para 8 GB de RAM. |
| Exemplo sem segredo | `1` |
| Validacao | Claims SQLite impedem dois renders concorrentes. |
| Erros comuns | Outros valores sao rejeitados. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## RENDER_DEFAULT_WIDTH

| Campo | Configuracao |
|---|---|
| Nome | `RENDER_DEFAULT_WIDTH` |
| Servico | local |
| Finalidade | Largura de novos projetos verticais. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Use dimensao par, normalmente 720. |
| Exemplo sem segredo | `720` |
| Validacao | FFprobe compara tamanho final. |
| Erros comuns | Valores impares ou fora de 64..1920 sao bloqueados. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## RENDER_DEFAULT_HEIGHT

| Campo | Configuracao |
|---|---|
| Nome | `RENDER_DEFAULT_HEIGHT` |
| Servico | local |
| Finalidade | Altura de novos projetos verticais. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Use dimensao par e proporcao 9:16 com a largura. |
| Exemplo sem segredo | `1280` |
| Validacao | FFprobe compara tamanho final. |
| Erros comuns | Plataforma pode recusar tamanho fora das regras. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## RENDER_DEFAULT_FPS

| Campo | Configuracao |
|---|---|
| Nome | `RENDER_DEFAULT_FPS` |
| Servico | local |
| Finalidade | Frames por segundo. |
| Obrigatoriedade | Padrao fornecido |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Use 24; renderer aceita ate 30. TikTok exige pelo menos 23. |
| Exemplo sem segredo | `24` |
| Validacao | FFprobe compara avg_frame_rate. |
| Erros comuns | Valores muito baixos nao servem para TikTok. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## AUTO_PUBLISH

| Campo | Configuracao |
|---|---|
| Nome | `AUTO_PUBLISH` |
| Servico | local |
| Finalidade | Nao existe publicacao automatica por timer. |
| Obrigatoriedade | Obrigatorio false nesta versao |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Mantenha false; calendario apenas planeja. |
| Exemplo sem segredo | `false` |
| Validacao | true causa erro explicito de configuracao. |
| Erros comuns | Plano editorial nao autoriza upload/publicacao. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## REQUIRE_HUMAN_APPROVAL

| Campo | Configuracao |
|---|---|
| Nome | `REQUIRE_HUMAN_APPROVAL` |
| Servico | local |
| Finalidade | Bloqueia entregas de artefato sem aprovacao por hash. |
| Obrigatoriedade | Recomendado true |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Mantenha true; false ainda exige acao explicita de upload. |
| Exemplo sem segredo | `true` |
| Validacao | Teste publication_guard bloqueia arquivos nao aprovados. |
| Erros comuns | Alterar roteiro/revisao ou arquivo invalida aprovacao. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |

## MAX_UPLOAD_MB

| Campo | Configuracao |
|---|---|
| Nome | `MAX_UPLOAD_MB` |
| Servico | local |
| Finalidade | Limite de importacao PNG/WAV/MP3. |
| Obrigatoriedade | Opcional |
| URL oficial | https://www.python.org/downloads/windows/ |
| Como obter/configurar | Escolha limite adequado ao disco, em MB. |
| Exemplo sem segredo | `100` |
| Validacao | Arquivo acima do limite retorna HTTP 413. |
| Erros comuns | Arquivos grandes demais sao removidos apos rejeicao. |
| Seguranca | Nao versionar .env, credenciais, dados nem logs sensiveis. Nao usar valores recebidos de roteiros como caminhos ou comandos. |


## Login ChatGPT proprio (provider direto)

| Nome | Servico e finalidade | Obrigatoria/padrao | Exemplo e obtencao | Validacao e erros | Seguranca |
|---|---|---|---|---|---|
| AI_PROVIDER | Content Factory: provider textual padrao | Opcional; chatgpt em instalacoes novas, compatibilidade legada preservada | AI_PROVIDER=chatgpt; escolha chatgpt ou codex, sem cadastro externo | Settings mostra a escolha; valores diferentes sao recusados. Preferencia salva na UI tem precedencia | Nao e segredo; nao muda conta nem cobranca automaticamente |
| CHATGPT_LOGIN_TIMEOUT_SECONDS | Content Factory: prazo da autorizacao | Opcional; 300 | CHATGPT_LOGIN_TIMEOUT_SECONDS=300; escolha local entre 1 e 600 | Timeout encerra listener; retry usa state/nonce/PKCE novos. Valores fora do intervalo sao recusados | Nao e segredo |

URL oficial e passo a passo: https://developers.openai.com/siwc/token-sharing-open-source/sign-in. Nao obtenha ou preencha client_id/secret/tokens manualmente: o navegador autoriza a identidade Content Factory e o backend guarda o registro emitido no vault. O guia [CHATGPT_DIRECT.md](CHATGPT_DIRECT.md) descreve permissao de plano, callback, modelos e reconexao.

CODEX_TIMEOUT_SECONDS e CODEX_MAX_CONCURRENT_JOBS tambem limitam o provider textual direto. O Codex CLI/SDK e opcional nesse modo. Mantenha as configuracoes Google/YouTube/TikTok existentes; a mudanca nao altera seus segredos ou permissoes.

## Orcamentos de inferencia ChatGPT

As quatro variaveis sao opcionais, locais e nao secretas. Nao exigem credenciais nem configuracao remota. Referencia: [CHATGPT_STREAM_LIMITS.md](CHATGPT_STREAM_LIMITS.md).

| Nome / finalidade | Exemplo e padrao | Validacao / erros comuns |
|---|---|---|
| CHATGPT_STREAM_MAX_BYTES: trafego total por papel, incluindo tentativas | 16777216 | Inteiro entre 16384 e 134217728; stream_limit indica soma excedida, nao login expirado |
| CHATGPT_EVENT_MAX_BYTES: evento e buffer SSE | 2097152 | Inteiro entre 1024 e 8388608; event_limit pode indicar uma linha/frame gigante mesmo com pouco trafego total |
| CHATGPT_TEXT_MAX_BYTES: texto final unico UTF-8 | 1048576 | Inteiro entre 1024 e 4194304; versoes delta/done nao devem ser somadas novamente |
| CHATGPT_TIMEOUT_SECONDS: duracao total da geracao do papel | 300 | Numero entre 1 e 1800; se ausente reutiliza CODEX_TIMEOUT_SECONDS por compatibilidade; runtime_limit exige revisar tempo/complexidade |

Configure os valores em .env e reinicie a API. Use inteiros em bytes, sem sufixo MB/MiB. Tetos excessivos aumentam risco de consumo local; mantenha os padroes medidos antes de ajustar. As validacoes rejeitam valores fora das faixas e nao aceitam ilimitado. Nenhum desses campos deve conter token, API key ou texto de projeto. Os testes nao precisam de conta externa para validar os limites.
