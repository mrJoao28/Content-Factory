# Produção musical infantil

O Music Studio fica na tela **Review / Video Preview** da produção. O fluxo usa o
login textual existente para compor letras e planejar cenas, Piper para fala,
Blender para os frames e FFmpeg para mixagem/montagem. Login ChatGPT não gera canto,
imagens ou vídeos. Personagens, letras e arranjos devem ser originais: não peça
cópias de músicas, personagens ou identidade de outras produtoras.

## Ativar sem interromper a instalação atual

Este trabalho foi desenvolvido na branch `feat/children-music-studio`, em um checkout
separado. Não é necessário atualizar a instalação que estiver renderizando agora.
Conclua ou pause explicitamente o trabalho e aguarde o lease ser liberado antes de
ativar a mudança. Preserve `.env`, banco, frames, vozes, output e vault. Não copie
credenciais entre checkouts.

Depois de revisar/integrar a branch, no diretório da instalação:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\scripts\doctor.ps1
.\scripts\dev.ps1
```

A migração `0004_music` acrescenta dois campos JSON e a tabela de histórico
`music_versions`; não apaga os projetos antigos. Para instalação limpa, use
`scripts/setup.ps1` antes desses comandos. Nenhuma variável secreta nova é obrigatória.
FFmpeg/FFprobe continuam necessários; Blender 4.5/5.2 LTS para render 3D local.
Piper/modelo/JSON de voz inglesa só são necessários para segmentos falados.
Colab pode renderizar sem Blender instalado no Windows.

## Primeira canção

1. No workspace, escolha **Blender 3D**, Preview, personagem/cenário e a duração
   desejada (8–3600 segundos, em frames inteiros). Escolha Animated song, Musical
   story ou Episode with songs. A produção fica em `WAITING_FOR_MUSIC`, sem começar
   inferência ou render automaticamente.
2. Abra a produção em Review e o **Music Studio**. Defina formato e objetivo
   educativo. **Compose original musical plan** usa a conexão/modelo textual
   escolhido para essa produção. É um pedido explícito que consome seu limite textual.
3. Revise/edite o JSON: público, idioma, história, elenco, ambiente e segmentos.
   Cada segmento possui ID estável, duração planejada, letra original em seções,
   direção musical, instrumentos, `bpm_requested`, compasso, cantor e ação visível.
   Salve com **Save musical revision**. Os segmentos precisam somar a duração total.
4. Para canto sem integração paga, declare origem/licença e importe um WAV/MP3
   original em **Complete mixed song**. Também é possível importar stems de voz
   cantada, instrumental e efeitos separadamente. Não use fala como stem cantado.
   O sistema não consegue comprovar sozinho a licença ou a presença de canto;
   escute o áudio antes de aprovar.
5. O player de cada take mostra a origem e a duração medida. Uma canção completa
   não recebe outro instrumental automaticamente. Importar uma canção completa
   substitui os stems selecionados daquela música, preservando o histórico.
6. Para um segmento `instrumental`, **Generate local instrumental** produz um
   acompanhamento original simples de síntese aditiva, no CPU, sem downloads ou
   serviço externo. Isso não é voz cantada nem uma orquestração de estúdio. Para
   `narration`/`dialogue`, use **Generate speech (Piper)** ou importe fala.
7. Resolva `audio_required`/`duration_conflict` na tabela. Edite, regenere ou altere
   explicitamente a duração total e os segmentos no JSON. Ao mudar tempos, revise
   eventos e marcadores: não são deslocados automaticamente. Não há corte de frases,
   mudança de velocidade ou repetição automática para preencher tempo. `pause` é
   silêncio deliberado e precisa existir no plano.
8. **Mix and validate final PCM16 WAV** usa a fila sequencial existente. Aguarde a
   conclusão, escute o player da mixagem final e baixe o WAV se desejar. Só então
   **Prepare storyboard and render** libera o planejamento visual/renderização.

## Canto automático opcional: ElevenLabs Music

O adaptador chama o endpoint oficial `POST https://api.elevenlabs.io/v1/music`, modelo
`music_v2_5`, com um composition plan contendo as letras e as durações das seções.
Não usa navegador automatizado, endpoints privados ou credenciais ChatGPT.
O contrato v2.5 usa `composition_plan.chunks` (`text`, `duration_ms`, estilos e
`context_adherence`), não o formato `sections`/estilos globais do v1. São aceitas até
30 seções de 3–120 segundos nesse adaptador. As letras/versos continuam editáveis
no contrato editorial da fábrica e são convertidos somente no pedido ao serviço.

- Requer conta/assinatura com acesso à Music API e chave obtida no painel oficial.
  Veja [autenticação](https://elevenlabs.io/docs/api-reference/authentication) e
  [preços atuais](https://elevenlabs.io/pricing/api). A contratação é sua decisão;
  a aplicação não compra créditos, ativa cobrança nem muda de conta.
- A configuração fica em **Optional ElevenLabs Music configuration**, no vault do
  sistema (DPAPI do usuário no Windows). Não coloque a chave em `.env`, SQLite,
  navegador, ZIP Colab ou Git. Salvar a chave não comprova acesso à geração.
- O botão pago exige marcar a autorização e clicar na música específica. Consulte
  o preço vigente antes de cada pedido. Em 28/10/2026 a página de preços consultada
  anunciava US$0,15/minuto; assinatura, impostos e condições da conta podem alterar
  o custo. Esse valor não é uma cotação garantida nem um limite financeiro imposto
  pelo app.
- O adaptador aceita **3–300 segundos por canção**. A documentação de compose
  anuncia até 600 segundos, enquanto o pricing consultado informa limite de cinco
  minutos; por isso este adaptador usa o limite conservador. Divida explicitamente
  músicas maiores ou importe áudio; não há corte silencioso.
- O serviço executa a geração fora do notebook; não exige GPU local. A chamada
  envia letras/direção ao provedor, com timeout total finito de 600 segundos e
  resposta limitada a 32 MiB. Há uma única tentativa, sem retry pago automático.
  Cancelar pode não cancelar a geração/cobrança no serviço. Verifique seu histórico
  antes de solicitar novamente após erro/timeout.
- São registrados provedor, modelo e `song-id` quando enviado. O áudio retorna
  mixado; a aplicação não inventa stems. O arquivo passa por decodificação e medição,
  e a mixagem é validada localmente. Escuta humana confirma pronúncia, letra e canto.

Fontes: [contrato compose](https://elevenlabs.io/docs/api-reference/music/compose),
[guia musical oficial](https://elevenlabs.io/docs/eleven-api/guides/cookbooks/music).
Não foi feita geração paga durante a implementação. Sem uma canção original
importada ou autorização/configuração do serviço, a demonstração **cantada** permanece
pendente; os testes com tons conhecidos não são apresentados como canto.

Os novos sons locais são síntese procedural original do código do projeto, sem
samples de terceiros adicionados. Vozes Piper mantêm a licença específica do modelo
ONNX escolhido; consulte seu model card. Áudio importado exige declaração de origem
e direitos. A permissão comercial de canto gerado depende dos termos e do plano
vigentes no serviço, não do login ChatGPT nem de uma garantia da fábrica.

## Timeline e sincronização

O editor JSON expõe segmentos, seções, `beats` e `events`. A tabela mostra início/fim
global planejado e duração medida do áudio. Eventos e marcadores usam segundos
locais ao segmento; os tempos globais somam os segmentos anteriores. `bpm_requested`
é direção, nunca BPM medido. Não há detector de batidas nesta versão: use marcadores
manuais ou timings fornecidos por uma fonte verificável e preserve seu `source`.

Eventos suportados: `idle`, `wave`, `smile`, `tilt`, `clap`, `sway`, `dance`. As três
últimas ações têm implementação real no template Blender. Elas usam um movimento
estilizado baseado no andamento solicitado; não são dança capturada ou IK completo.
Um ator não pode executar ações sobrepostas. O storyboard precisa deixar os
intervalos reservados pelos eventos livres; conflitos impedem aceitar o planejamento.

Exemplo de evento e marcação manual:

```json
{
  "events": [{"time": 4, "end": 8, "character_id": "dino", "action": "clap"}],
  "beats": [{"time": 4, "source": "manual"}],
  "singer": "offscreen"
}
```

Para canto visível, selecione `singer: "character"` e `character_id` do catálogo.
A abertura de boca usa energia do stem vocal (ou da mixagem, quando só ela existe),
em blocos de 150 ms. **É uma aproximação, não alinhamento fonético.** Uma mixagem pode
produzir aberturas motivadas pelos instrumentos. Edite `mouth_times` explicitamente
com segundos locais; `[]` desliga aberturas. Canto offscreen não aciona a boca.
Os personagens atuais são os rigs Dino/Milo; o plano não fixa um protagonista,
mas adicionar outro personagem exige implementar/versionar seu asset e rig no
catálogo confiável. A IA não pode inventar uma malha nova.

## Mixagem, versões e retomada

- `gain`, `instrumental_gain`, `effects_gain`, `fade_in`, `fade_out` e `ducking` são
  editáveis por segmento. Ducking atua no instrumental quando há voz/fala separada.
  Material premixado não recebe ducking/separação artificial.
- Mixagem por arquivos/segmentos, PCM16 mono 24 kHz, sem carregar um episódio inteiro
  na RAM. Cache por receita/hashes preserva segmentos concluídos. Clipping, silêncio
  inesperado maior que dois segundos dentro de material sonoro e conflito de duração
  impedem validar; divida pausas intencionais explicitamente. A presença de áudio não
  garante qualidade musical/artística.
- Plano e takes antigos permanecem no histórico; arquivos anteriores não são apagados.
  Trocar letra/direção mantém os takes das outras músicas. Ajustar volume conserva
  os takes e o storyboard compatível; a mixagem/render/aprovação são invalidados.
- Storyboards musicais são pedidos/validados por segmento, com checkpoints
  `_music_boards`. Retomar não repete segmentos cujo hash/contexto permaneceu igual.
  Mudança na continuidade da cena anterior pode exigir replanejar segmentos seguintes.
- A fila persiste a operação, possui lease/heartbeat e cancelamento. Pause pelo
  Music Studio e aguarde o lease soltar antes de editar. Após erro/interrupção, clique
  novamente na operação desejada: um pedido de canto não é repetido pelo Resume genérico.
- A referência `narration.final` contém revisão, path relativo permitido, SHA-256,
  duração, hash do plano e proveniência. Player final, render local e exportação usam
  **o mesmo arquivo**. Importação legada prioriza a importação nova, removendo referências
  geradas obsoletas. Não apague o banco para resolver áudio antigo.

## Colab e revisão

Depois da mixagem validada, escolha preparação para Colab e siga [COLAB.md](COLAB.md).
O notebook recebe somente o storyboard validado e o WAV final. Não compõe letras,
gera voz ou recebe chave musical. O transporte v2 mantém limites de ZIP/arquivo e
exige o commit confiável registrado na exportação; exportações de uma revisão
substituída são recusadas. Pacotes antigos precisam do notebook/release indicado
na própria exportação; não altere hashes para forçar compatibilidade.

O ZIP de resultado é salvo no Drive e o download é iniciado **antes** da tentativa
de exibir o vídeo. Um erro de player é tratado sem impedir obter o resultado.
Importar um resultado válido leva a `HUMAN_REVIEW`; escute o MP4 completo e confirme
o hash antes de aprovar. Não há publicação automática.

## Compilações

Escolha Compilation no Music Studio, marque unidades já aprovadas e use **Build
editable compilation plan**. Revise a ordem e a alteração explícita da duração,
salve e clique **Assemble reviewed units for human review**. A montagem é local em
FFmpeg, sem nova inferência/Blender. Só aceita fontes existentes com hash aprovado,
mesmas dimensões/FPS e duração correspondente. O áudio é decodificado por unidade
para evitar acumular padding do codec AAC entre elas; o conteúdo aprovado não é
encurtado para caber num plano arbitrário. A compilação recebe uma aprovação nova.
Esta versão não transporta as unidades de compilação ao Colab.

## Limites e validações

São limites técnicos explícitos, não garantia de viabilidade nesse notebook:
3600 s por produção, 256 segmentos, 600 s por take local/importado, 300 s por pedido
cantado, 720 cenas 3D, 60 s por cena e limites por ator/ações/partículas já existentes.
Cada segmento planejado precisa caber em frames inteiros para fechar o storyboard.
O transporte mantém 200 MiB para áudio, ZIP de 256 MiB e expansão de 512 MiB; não
foram relaxadas as proteções globais de upload. Render mantém limites finitos de
tempo/disco e checkpoints; um episódio HD pode exceder o orçamento de disco.
Nesse caso, reduza o perfil explicitamente ou produza unidades menores e compile.
Não há promessa de geração/renderização ilimitada ou velocidade no Colab gratuito.

Exemplo planejado original de 35 segundos: `examples/music/helping-hands.json`.
Esse arquivo contém letras e direção, **não uma canção gravada**. O teste de lógica
também monta 620 s em múltiplos segmentos sem renderizar um episódio inteiro.

Teste real curto, em ambiente/banco isolados (não usa conta ChatGPT):

```powershell
$env:FACTORY_TEST_BLENDER='C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
$env:FACTORY_MUSIC_EVIDENCE='./output/music-evidence'
.\.venv\Scripts\python.exe -m pytest tests/test_music.py::test_real_blender_musical_round_trip -q
```

Gera 12 frames em resolução diagnóstica, instrumental local original, ZIP de entrada,
MP4, checkpoint, ZIP de retorno e importa pelas rotas reais até revisão humana.
É uma prova técnica CPU local, não uma demonstração cantada, artística, GPU ou Colab.
