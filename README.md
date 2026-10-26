# AI Content Factory

Estudio audiovisual local para WonderNest Kids (YouTube) e How It Actually Works (TikTok). Interface Next.js, API FastAPI, SQLite WAL, worker sequencial e compositor 2.5D Python/Pillow/FFmpeg. Nao utiliza n8n, Redis, GPU nem API paga de geracao de video.

## Instalar no Windows

Requisitos: Python 3.11+, Node.js 22+, FFmpeg com FFprobe, Codex CLI. Execute PowerShell na raiz deste repositorio:

```powershell
.\scripts\setup.ps1
codex login
.\scripts\doctor.ps1
.\scripts\dev.ps1
```

Web: http://127.0.0.1:3000. API/OpenAPI: http://127.0.0.1:8000/docs.
[Instalacao detalhada](docs/SETUP_WINDOWS.md) ? [Guia completo do .env](docs/ENV_GUIDE.md) ? [Login Codex](docs/CODEX_AUTH.md).

## O que funciona

- Dois workspaces independentes, cinco series infantis iniciais, personagens e expressoes referenciando assets.
- Criacao de ideias com prevencao de duplicacao, roteiros/versionamento, storyboard validado, fila SQLite com lease, heartbeat, checkpoints, retry e cancelamento.
- Sete papeis de IA sequenciais por um provider compartilhado; CLI oficial com JSONL e schema. Adapter SDK Python oficial com verificacao de capacidades e fallback documentado.
- Importacao PNG, declaracao de direitos, deduplicacao SHA-256, importacao WAV/MP3, Piper por cena com cache e controle de duracao; musica, efeitos temporizados, volumes e preview de audio.
- Compositor real com alpha, easing, keyframes, rotacao, camera, parallax, texto, setas, engrenagens, particulas e transicoes. Templates originais em `factory/templates.py`.
- MP4 H.264/AAC, thumbnail, SRT por cena, metadados, verificacao FFprobe, decodificacao integral e medicao de volume.
- Player, aprovacao/rejeicao vinculada ao hash e revisao especifica de fontes cientificas.
- Calendario diario/semanal/mensal, arrastar planos, fuso IANA, conflitos e metas editoriais persistidas.
- OAuth com state, PKCE Google, refresh/revogacao; tokens DPAPI no Windows.
- Drive com diretorios e uploads resumiveis de video/thumbnail/roteiro/SRT/metadados; YouTube com upload resumivel, Made for Kids, privacidade, publishAt e consulta de status.
- TikTok OAuth, identidade, envio oficial para inbox, Direct Post condicionado a aprovacao/consentimento e consulta de status. Alternativa manual ZIP, legenda, hashtags e registro da URL.
- Dashboard com contagens locais reais, armazenamento e tempo de render; snapshots de estatisticas YouTube sob demanda e eventos via SSE.

## Fluxo de uso

1. Conecte ChatGPT em Settings ou execute `codex login` no mesmo usuario Windows que executa a API.
2. Configure Piper e uma voz inglesa, ou importe narracao depois de revisar as cenas.
3. Escolha um workspace e envie uma ideia em Prompt Workspace.
4. Acompanhe a fila. Se houver dependencia ausente, configure-a e pressione Resume.
5. Pause antes de editar roteiro/storyboard. Salvar cria revisao e invalida aprovacao. Retome para produzir a nova revisao.
6. Assista ao MP4 em Review Studio e registre a revisao humana.
7. Conecte Drive/YouTube/TikTok. Planejar no calendario nao faz upload. Cada upload exige confirmacao explicita.
8. Consulte o status remoto. Um upload nunca e apresentado como publicacao confirmada automaticamente.

## Testar e demonstrar

```powershell
.\scripts\test.ps1 -Browser
# Demonstracoes autorais independentes de login/API externa:
.\.venv\Scripts\python.exe scripts/demo.py
```

Demos: `output/demo/wondernest/video.mp4` (35s) e `output/demo/how-it-works/video.mp4` (65s). Incluem narracao local Flite apenas para demonstracao, storyboard e `validation.json`. Nao sao videos gerados pelo Codex nem foram publicados. Producao usa Piper ou narracao importada. Flite precisa estar habilitado no build do FFmpeg para este comando de demo.

[Resultados e limitacoes verificadas](docs/VALIDATION.md). Os testes HTTP externos usam mocks somente em `tests/`; producao usa APIs reais. Login, contas, permissoes, quotas e auditorias precisam ser validados pelo proprietario.

## Arquitetura e limites

[Arquitetura](docs/ARCHITECTURE.md) ? [Pipeline](docs/PRODUCTION_PIPELINE.md) ? [Seguranca](docs/SECURITY.md) ? [Troubleshooting](docs/TROUBLESHOOTING.md).

A arte inicial e geometrica em 2.5D; nao e animacao 3D fisica. Importar assets melhores aumenta a qualidade, sem alterar o motor. Blender e opcional. A verificacao cientifica assistida por IA nao substitui leitura humana das fontes. Retencao, watch time e crescimento nao sao inventados. Estatisticas de canal YouTube podem ser sincronizadas sob demanda; retencao/watch time exigem integracao YouTube Analytics adicional.

O SDK Python nao pode ser instalado neste sandbox sem acesso ao registry. O CLI 0.164.0 instalado suporta a alternativa oficial usada aqui. O adapter SDK so e escolhido automaticamente se o runtime suportar isolamento de configuracao equivalente; consulte CODEX_AUTH.md.

Nao ha publicacao automatica por timer: `AUTO_PUBLISH` permanece desabilitado. YouTube agenda no servidor da plataforma ao aceitar `publishAt`; TikTok inbox exige finalizar no aplicativo. Direct Post possui endpoint e formulario de consentimento, desabilitados por padrao; habilite apenas com escopo aprovado pela plataforma.

Git foi inicializado, mas o sandbox bloqueia escrita em `.git`, impedindo branches/commits. Nenhum commit e alegado. O script `scripts/commit-validated.ps1` permite ao proprietario validar e criar um commit de feature fora dessa restricao.
