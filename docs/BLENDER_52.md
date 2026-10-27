# Compatibilidade Blender 5.2 LTS

Instalação real detectada: **Blender 5.2.3 LTS** em
`C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`.
O valor de `BLENDER_PATH` foi corrigido para usar barras `/`: dentro de aspas duplas,
`\b` pode ser interpretado como backspace pelo parser dotenv. Nenhuma outra variável
foi substituída. Reinicie a API para carregar o valor e o adaptador atualizados.

## Alterações

- `blender_info()` aceita explicitamente as séries 4.5 e 5.2 LTS, mantendo a rejeição
  de versões não suportadas. A versão completa continua fazendo parte do hash do cache.
- O template evita escrever `Material.use_nodes` / `World.use_nodes` em Blender 5.x.
  Essas propriedades são obsoletas e não têm efeito desde 5.0; o caminho 4.5 continua
  habilitando os nós como antes. Fontes: [World API 5.2](https://docs.blender.org/api/5.2/bpy.types.World.html)
  e [Material API](https://docs.blender.org/api/current/bpy.types.Material.html).
- O probe confiável `scripts/probe_blender_api.py` confirmou em 5.2.3 a presença do
  Cycles, threads, árvores nodais e sockets `Base Color`, `Roughness`, `Emission Color`
  e `Emission Strength`. A verificação não acessa a conta ChatGPT.
- Cycles permanece em **CPU**, com dados de cena persistentes entre frames. Nenhuma
  troca silenciosa para EEVEE/GPU ou para o compositor 2D foi adicionada.
- `scripts/demo_3d.py` aceita `--resolution 180x320` para uma verificação inicial
  mais leve. O padrão existente 360×640 continua disponível; Final permanece explícito.

Consulte também as [notas oficiais de API 5.2](https://developer.blender.org/docs/release_notes/5.2/python_api/).
As mudanças de Geometry Nodes não afetam este template, que não usa modificadores
de Geometry Nodes. Não foram criadas exceções à validação de dados ou à segurança
de execução de subprocessos.

## Verificação

A sondagem real de API passou e os primeiros frames de Dino foram renderizados e
inspecionados. Os dois testes reais de Blender também passaram: exportação/retomada
de frames e produção pela fila até `HUMAN_REVIEW`, em 181,69 segundos no conjunto.
Cada fixture usa 0,5 segundo, 90×160, 24 FPS e áudio PCM de teste conhecido; não é
inferência ou narração da conta do usuário. Há 12 frames reais por clipe. A retomada
confere a reutilização dos 12 frames da mesma revisão/configuração.

O clipe autoral de Dino foi concluído de verdade: `output/3d-demos/slice/video.mp4`.
Tem **3,000 segundos**, **180×320**, **24 FPS**, **72 frames**, H.264 e AAC, em
Cycles CPU/Preview. Tempo medido: **1078,146 s (17 min 58 s)**, com outros checks
executando durante parte do render. Vídeo: 51.041 bytes; PNGs: 4.992.934 bytes.
RSS/pico de RAM não foram medidos. Esses números não são um benchmark isolado.

Passaram todas as verificações de codec, dimensões, FPS, duração, decodificação
completa, audibilidade e pico. O relatório é `output/3d-demos/slice/report.json`.
Foram inspecionados os frames 1, 36 e 72 do mesmo cache/revisão. O primeiro mostra
um blink; os seguintes mostram olhos abertos e a mudança de cor do ovo. O áudio é
trilha/efeitos sintetizados, sem narração Piper neste clipe. Não houve escuta
subjetiva nem aprovação artística do vídeo completo. O modelo permanece procedural.

A tentativa inicial sem persistência de cena foi interrompida pelo agente após
20 frames para testar a configuração de cache. Não foi uma falha de compatibilidade
nem um vídeo concluído. O hash mudou ao alterar o template, e o render final gerou
os 72 frames novamente, sem reaproveitar frames da configuração anterior.

Checks executados após a adaptação:

- Pytest geral sem os dois casos de render: **201 passaram**, sem skips, 530,55 s.
- Pytest de Blender real: **2 passaram**, sem skips, 181,69 s.
- Total: **203 testes Python aprovados**, incluindo os antigos casos que antes eram pulados.
- Ruff, typecheck e build de produção: passaram.
- Vitest: **6 passaram**. Playwright: **9 passaram**, 2,6 min, com API/interface reais
  em portas isoladas. Nenhuma inferência real ChatGPT foi solicitada.

Os relatórios JUnit estão em `data/3d-validation/blender52-general.xml` e
`data/3d-validation/blender52-render.xml`, ignorados pelo Git.

## Como usar

No `.env`:

```dotenv
BLENDER_PATH="C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
BLENDER_THREADS=2
```

Pare a execução antiga com Ctrl+C e reinicie:

```powershell
.\scripts\dev.ps1
```

Em Prompt workspace selecione **3D local · Blender CPU**, Preview, personagem,
cenário e duração. Projetos antigos continuam com seu motor original. Uma tarefa
parada pode usar Resume sem mudar a conexão ChatGPT nem apagar os checkpoints.

Diagnóstico sem render:

```powershell
.\scripts\doctor.ps1
```

Render autoral local, sem consumir ChatGPT:

```powershell
.\.venv\Scripts\python.exe scripts/demo_3d.py slice --render --resolution 180x320
```

O render em CPU é lento neste hardware. Aumentar a resolução exige medir novamente
o tempo; não há promessa de renderização rápida ou de qualidade final automática.
