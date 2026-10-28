# Produção 3D local — estado verificável

Esta implementação adiciona um caminho Blender ao pipeline existente. O adaptador
suporta **Blender 4.5 e 5.2 LTS** em CPU. O usuário instalou 5.2.3 LTS depois do
bloqueio inicial de instalação; os resultados atuais estão em [BLENDER_52.md](BLENDER_52.md).
Os JSONs de demonstração, isoladamente, não são evidência de renderização. Não escolha
Final antes de renderizar e inspecionar a fatia Preview.

## Instalar e iniciar no Windows

1. Feche a execução de desenvolvimento com Ctrl+C. Preserve `.env`, `data`, `output`
   e os arquivos de voz existentes.
2. Instale **Blender 4.5 ou 5.2 LTS** pelo [site oficial](https://www.blender.org/download/).
   O adaptador rejeita outras séries explicitamente. Em hardware ARM/emulação,
   confirme que o binário oficial realmente executa antes de produzir.
3. Acrescente ao `.env` (não substitua o arquivo):

   ```dotenv
   BLENDER_PATH=C:/Program Files/Blender Foundation/Blender 5.2/blender.exe
   BLENDER_THREADS=2
   BLENDER_TIMEOUT_SECONDS=7200
   BLENDER_DISK_BUDGET_MB=4096
   ```

4. Execute na raiz:

   ```powershell
   .\scripts\setup.ps1 -StopRunning
   .\scripts\doctor.ps1
   .\scripts\doctor.ps1 -Smoke3D
   .\scripts\dev.ps1
   ```

`setup` aplica Alembic; `dev` também aplica as migrações antes de abrir os serviços.
`0002_visual_config` acrescenta somente uma coluna JSON. Projetos existentes recebem
`engine=compositor_2d`, preservando o comportamento anterior. Não apague o banco.
API e interface continuam em `127.0.0.1:8000` e `127.0.0.1:3000`.

## Fluxo pela interface

No Prompt workspace escolha **3D local · Blender CPU**, personagem, cenário,
qualidade, resolução, FPS e duração. O servidor exige o executável correto antes de
enfileirar uma produção 3D. A duração configurada prevalece; uma duração diferente
na ideia causa erro recuperável antes da geração textual. 8, 15 e 35 segundos são
aceitos em 3D; os contratos antigos de Shorts/episódios 2D permanecem disponíveis.

ChatGPT gera somente conceito, roteiro, dados de cena, revisão e metadados, usando
a conexão/modelo já selecionados. Não gera as imagens, o áudio ou o vídeo neste
fluxo. Não há API key, troca de provider nem cobrança externa automática.

O worker usa o schema 3D do catálogo, valida-o antes de salvar o checkpoint,
produz/mensura áudio, executa Blender e FFmpeg e aplica a validação técnica anterior.
A revisão humana e a aprovação por SHA-256 do MP4 permanecem obrigatórias.
Review studio oferece reprodução, download, diagnóstico e configurações visuais.
Não há prévia estática fictícia: a thumbnail vem do primeiro frame realmente renderizado.

Para corrigir um planejamento inválido, pause a produção e use **Regenerate planning**.
A interface enumera as invalidações e exige confirmação. O endpoint guarda uma nova
revisão, preserva `creative_director`, `script_writer` e a seleção textual, cancela o
job anterior e invalida storyboard, revisões dependentes, composição, render e aprovação.
A mudança é bloqueada com lease/upload ativo e por revisão desatualizada. O script
é preservado mesmo se tiver sido editado manualmente. Os arquivos antigos não são apagados.
Não altera outras produções. Resume do mesmo job mantém cache da mesma revisão.

## Contrato e segurança

- `visual_schema.py`: metros, Z para cima, personagens voltados para -Y na pose
  inicial; rotação de heading em graus. Tempos relativos a cada cena. Frame 1=t=0;
  N frames cobrem `[0,duração)`. Cenas precisam durar um número inteiro de frames.
- `VisualBoard.duration` precisa coincidir exatamente com o projeto. Sem alongar
  cenas automaticamente. O provider direto faz no máximo uma correção JSON com
  feedback de validação; OAuth, SSE e limites finitos existentes são preservados.
- Catálogo `factory-3d-v1`: Dino `dino-v1`, Milo `milo-v1`; floresta, jardim e estúdio;
  ovo mágico, estrela e par de engrenagens. A IA não escolhe materiais arbitrários,
  anatomia, arquivos, scripts, drivers, bibliotecas ou caminhos.
- Máximos: 60 cenas, 2 atores/cena, 3 props, 24 ações, 6 chaves de câmera e 24
  partículas. Caminhada no chão, até 0,8 m/s; ações ordenadas sem sobreposição por
  ator; referências e versões precisam existir. Essa validação básica não prova
  ausência de todas as colisões ou adequação artística.
- `factory_scene.py` é código confiável do repositório. Usa geometria volumétrica
  procedural compartilhada, pivôs, poses determinísticas, três luzes, AgX, Cycles CPU
  e materiais nodais. Sem importação de `.blend` externo ou Python da IA.
  `--factory-startup --disable-autoexec --python-exit-code 1` são obrigatórios.
- Catálogo, duração, resolução, qualidade e FPS são persistidos em `visual_config`
  e storyboard por revisão. O manifest do render inclui o hash do template, versão
  Blender, áudio, timeline, threads e revisão. O hash define um diretório de frames
  exclusivo; PNGs corrompidos/incompatíveis são descartados individualmente.
- Frames são gravados primeiro em `.partial.png` e renomeados após render. O
  Blender avalia cada frame a partir dos dados originais, permitindo retomada.
  Um lock de arquivo e a fila SQLite impedem renders pesados simultâneos.
- Cancelamento/timeout terminam a árvore de processo no Windows; a fila libera o
  lease. Eventos registram contagem real de frames, tempo e ETA somente após oito
  frames novos. A saída completa de Blender não é guardada em logs.

## Qualidade e recursos

| Ajuste | Padrão | Intervalo/efeito |
|---|---|---|
| Preview | 8 samples, CPU | 360×640 sugerido; qualidade visual a avaliar |
| Final | 32 samples, CPU | 720×1280 ou 1080×1920, 24/30 FPS |
| `BLENDER_THREADS` | 2 | 1–8 threads; reserva CPU para interface |
| `BLENDER_TIMEOUT_SECONDS` | 7200 | 30–86400; render preserva frames ao expirar |
| `BLENDER_DISK_BUDGET_MB` | 4096 | 128–65536; estimativa conservadora RGB + 64 MiB |

O limite de disco usa estimativa sem compressão. 1080p/35s pode exceder o padrão;
escolha menor resolução ou aumente o orçamento explicitamente após conferir espaço.
PNG por frame evita carregar um vídeo inteiro em RAM, mas não impõe teto de RSS ao
Blender. Sem benchmark, não há garantia de viabilidade em 8 GB. EEVEE/GPU não são
selecionados nem usados como fallback. Não há denoiser ou GPU pagos.

## Voz, música e diálogo

Preserve `PIPER_PATH` e `PIPER_VOICE_PATH`. A configuração 3D verifica executável,
modelo `.onnx` e JSON adjacente (`.onnx.json`), idioma inglês e sample rate.
Settings oferece **Test configured voice**, síntese local sem uso do plano.
Não há download automático nem alteração das vozes configuradas. Instale pelo
[Piper oficial](https://github.com/OHF-Voice/piper1-gpl) e consulte o model card/licença
de cada voz em [piper-voices](https://huggingface.co/rhasspy/piper-voices).

Narração e diálogo por personagem são separados no storyboard. A configuração atual
usa a mesma voz inglesa instalada para ambos; seleção de múltiplas vozes e download
assistido ainda não foram implementados. Não há promessa de atuação infantil.
Cada trecho é medido antes da composição; fala longa/sobreposta bloqueia produção
para editar texto/timing. Não trunca nem acelera automaticamente.

Diálogo pode receber `mouth_times` editáveis. Quando ausentes, a síntese calcula
aberturas aproximadas espaçadas durante a duração medida: **não é alinhamento
fonético nem visemas completos**. Narração em off não anima boca. WAV/MP3 importado
continua aceito; nesse caso os timings labiais devem ser fornecidos manualmente.
O Piper legado ainda usa subprocesso bloqueante durante cada trecho; o cancelamento
é checado entre trechos. Cancelamento imediato de TTS permanece pendente.

`visual_audio.py` sintetiza uma trilha simples original e efeitos tonais de passo,
brilho e toque, com fades/limitador; não são gravações nem músicas comerciais.
O mixer/biblioteca anteriores continuam disponíveis para arquivos licenciados.
Níveis/articulação precisam de escuta real, ainda pendente neste ambiente.

## Demonstrações reproduzíveis, sem consumo do ChatGPT

Primeiro a fatia vertical. Não execute os clipes longos antes de verificar os frames:

```powershell
.\.venv\Scripts\python.exe scripts/demo_3d.py slice --render
# Inspecione output/3d-demos/slice/video.mp4 e os PNGs do diretório frames.
.\.venv\Scripts\python.exe scripts/demo_3d.py dino --render
.\.venv\Scripts\python.exe scripts/demo_3d.py milo --render
.\.venv\Scripts\python.exe scripts/demo_3d.py engineering --render
```

Slice/engineering usam áudio de trilha autoral. Dino usa “Wow! What's that?” em
Piper. Milo usa sete cenas de cinco segundos com narração autoral em inglês.
`--audio C:/caminho/voz.wav` permite narração gravada compatível em duração.
`--quality final --resolution 720x1280` é uma escolha explícita. Sem `--render`,
somente o JSON é escrito e identificado como plano, nunca como vídeo.

O script chama o mesmo renderer da fila e valida H.264/AAC/dimensões/FPS/duração,
decodificação e audibilidade. O manifest/report real registra tempo e frames retomados.
As demonstrações não publicam conteúdo nem alteram projetos existentes.

O mecanismo é uma **ilustração procedural** de duas engrenagens iguais girando em
sentidos opostos, não simulação de dentes involutos ou prova de eficiência/tensão.
Fonte técnica primária para revisão: [KHK, Gear Technical Reference](https://khkgears.net/new/gear_knowledge/gear_technical_reference/).
Sem fonte conferida por humano, afirmações de engenharia continuam sinalizadas.

## Limitações e validação restante

Os frames de início/meio/fim da fatia Dino de três segundos foram inspecionados em
Blender 5.2.3 LTS; métricas e limites estão em [BLENDER_52.md](BLENDER_52.md).
Ainda faltam os três clipes longos solicitados, revisão temporal completa, contato
dos pés/mãos em ações complexas, continuidade ao pegar/soltar, transições, boca e
escuta. Não há solver físico/IK completo ou validação geométrica de penetrações.
Essas poses precisam de avaliação antes de ampliar a produção. Não há preview
interativo de poses ou edição isolada
de uma cena com re-render parcial; editar JSON/regenerar cria revisão completa.

Blender é GPL; Piper atual é GPL-3.0. Vozes possuem suas próprias licenças, que
devem ser conferidas no model card antes do download/distribuição. Os novos scripts,
personagens, cenários e tons são originais deste trabalho; não reutilizam arquivos
de terceiros ou personagens comerciais. Não foi acrescentada licença global ao
repositório. A licença de distribuição do projeto deve ser definida pelo proprietário.

O contrato `clip_contract.py` define uma extensão futura para serviços opcionais,
com modelo, duração, teto de custo confirmado e proveniência/licença. **Nenhum
serviço externo de clipes está implementado ou ativado**. O caminho Blender é local.

Git: a criação de branch foi tentada e negada pela permissão de escrita em `.git`.
Não foram feitos commits/push/PR desta mudança. Arquivos locais estão preservados.
# Execução assistida externa

Blender 3D também pode ser preparado localmente e exportado para um notebook Colab supervisionado. A escolha de execução é independente do provider textual e do motor visual. [Fluxo, limites e retomada](COLAB.md). Não transfira um render ativo sem pausar e aguardar a liberação do lease; os frames locais existentes são preservados e não são reutilizados automaticamente em GPU.
