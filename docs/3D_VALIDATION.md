# Relatório da implementação 3D local

**Histórico da etapa inicial, anterior à instalação do Blender.** O suporte e os
testes posteriores com Blender 5.2.3 LTS estão em [BLENDER_52.md](BLENDER_52.md).

Base inspecionada: branch `main`, commit
`f1520ed9ce774032ebea61aac7abf9f37094d070`. Não havia alterações locais no início.
Alterações desta implementação permanecem locais; a criação de
`feat/local-blender-production` falhou porque `.git` não permite escrita.
Sem commits, push, PR ou merge desta mudança.

## Implementado no código

- Escolha explícita de motor independente da IA, perfil, personagem, cenário,
  resolução/FPS e duração no workspace; diagnóstico real de dependências.
- Coluna `visual_config`, migração aditiva, compatibilidade dos projetos existentes
  com `compositor_2d`. Migração testada com um projeto legado preservado.
- Schema 3D limitado e catálogo versionado; geração textual pelo provider existente,
  JSON compacto, reparo limitado com feedback sem incluir valores privados nos erros
  enviados como feedback Pydantic; checkpoint somente após validação.
- Templates procedurais originais Dino/Milo, floresta/jardim/estúdio, ovo/estrela e
  engrenagens, pivôs, ações, câmera e iluminação. **Execução visual não verificada.**
- Renderer de produção conectado à fila, Cycles CPU, frames PNG em disco,
  manifest/hash, lock entre processos, retomada por frames, cancelamento/timeout,
  composição MP4 H.264/AAC e validação técnica existente.
- Áudio 3D com narração/diálogo separados, validação da configuração Piper,
  mensuração, rejeição de silêncio e fala longa/sobreposta, score/efeitos autorais,
  normalização de voz, fades/limitador e timings labiais aproximados editáveis.
- Revisão com configurações visuais, timeline de checkpoints e regeneração explícita
  que preserva conceito/roteiro, invalida dependências/aprovação, respeita leases e
  evita criar duas revisões por repetição de uma requisição desatualizada.
- Doctor com smoke render explícito; receitas reproduzíveis sem uso de ChatGPT.
  Contrato futuro para serviços de clipes, sem adaptador externo ativado.

## Arquivos principais

| Grupo | Arquivos |
|---|---|
| Contrato e catálogo | `visual_schema.py`, `storyboard_limits.py`, `visual_demos.py`, `clip_contract.py` |
| Render | `visual_render.py`, `visual_errors.py`, `templates/blender/factory_scene.py` |
| Produção | `pipeline.py`, `routes_projects.py`, `routes_visual.py`, `models.py`, `schemas.py`, `main.py` |
| Migração | `services/api/migrations/versions/0002_visual_config.py` |
| Texto preservado | `chatgpt_provider.py` (instrução do motor e feedback de reparo), `text_roles.py` |
| Áudio/diagnóstico | `visual_audio.py`, `doctor.py`, `providers.py`, `config.py` |
| Interface | `visual-production.tsx`, `studio.tsx`, `project-editor.tsx`, `integration-view.tsx`, `types.ts` |
| Operação | `.env.example`, `scripts/dev.ps1`, `scripts/doctor.ps1`, `scripts/demo_3d.py` |
| Testes | `tests/test_visual_production.py`, `tests/test_migrations.py`, `apps/web/e2e/studio.spec.ts` |

Módulos Python sem prefixo na tabela ficam em `services/api/factory`; componentes
em `apps/web/src/components`. `next-env.d.ts` foi regenerado pelo Next durante os checks.
Nenhuma configuração OAuth, segredo ou arquivo de projeto existente foi substituído.

## Checks executados

| Check | Resultado observado |
|---|---|
| `python -m pytest -q ...` | **193 passed, 2 skipped**, 343,78 s |
| Testes focados após o ajuste final de validação do personagem/checkpoint | **24 passed, 2 skipped**, 17,69 s |
| `python -m ruff check .` | Passou |
| `python scripts/check_syntax.py` | Passou; parsing de fontes Python |
| `npm run typecheck` | Passou |
| `npm test` | **6 passed** |
| `npm run build` | Passou, build Next.js de produção |
| `npm run test:e2e` | **9 passed**, 1,2 min; API/FastAPI e frontend iniciados realmente em portas isoladas 8001/3001 |
| `git diff --check` | Passou |

Os dois skips são exportação/retomada real Blender e fila Blender até revisão humana.
Eles não usam render falso: ficam pendentes quando `blender_info()` não encontra uma
instalação compatível. Os demais testes cobrem validação, duração, identidade/versão,
inputs inseguros, ausência de fallback, snapshot visual sem trocar o provider textual,
invalidação, lease, cache, silêncio e cancelamento/timeout de subprocesso real.

O teste de navegador novo faz regeneração pelas rotas FastAPI reais, com banco isolado.
OAuth e inferência externos continuam controlados nos testes; não houve consumo da
conta ChatGPT do proprietário. Nenhum vídeo foi publicado.

Foi detectada e corrigida uma regressão de duração no roteamento automático do canal
legado. Um teste antigo de Pause também precisou selecionar seu próprio projeto,
pois os testes novos criam mais produções no banco isolado do navegador. Os resultados
da tabela são posteriores às respectivas correções; falhas intermediárias não foram
contadas como testes aprovados.

Ambiente observado: Python **3.14.2**, AMD64, 5 CPUs lógicas; Node **26.8.1**;
Next **16.4.1**; FFmpeg/FFprobe **5.1.2**. RAM disponível/RSS não foram medidos.
Não houve execução de Blender; 4.5 LTS é a série alvo documentada, não uma versão
declarada como testada. As APIs foram consultadas na documentação oficial
[Blender Python 4.5](https://docs.blender.org/api/4.5/bpy.types.Scene.html) e no
[manual CLI 4.5](https://docs.blender.org/manual/pt/4.5/advanced/command_line/arguments.html).

## Evidência e demonstrações

`scripts/demo_3d.py slice --render` foi executado e parou com:

```text
Blender 4.5 LTS is missing. Set BLENDER_PATH to blender.exe; 3D never falls back to 2D.
```

A tentativa de acessar o download oficial pelo Python falhou com `WinError 10013`,
negação de socket pelo ambiente. Não há tempo de render, frame 3D, vídeo 3D ou
qualidade artística observada para relatar. Não é correto declarar o objetivo visual
concluído. Os JSONs autorais foram gerados em:

```text
output/3d-demos/slice/storyboard.json        # 3 segundos
output/3d-demos/dino/storyboard.json         # 8 segundos
output/3d-demos/milo/storyboard.json         # 35 segundos, sete cenas
output/3d-demos/engineering/storyboard.json  # 3 segundos
```

Esses arquivos são planos, não vídeos. Um teste de áudio sintetizado produziu
`data/3d-validation/audio-validation-fixture.mp4`, com fundo de cor explícito,
para conferir audibilidade, pico, AAC, H.264, FPS, dimensões e decodificação.
**Esse arquivo não é uma demonstração 3D.** Todas essas verificações passaram.

O relatório JUnit da suíte completa fica em
`data/3d-validation/pytest-verified.xml`. Esses arquivos de teste estão ignorados no Git.

## Pendências para concluir o objetivo visual

Instalar Blender 4.5 LTS, executar primeiro a fatia de três segundos e inspecionar
início/meio/fim. Corrigir modelos/contatos/câmera com base nos frames observados
antes de renderizar Dino 8s, Milo 35s e o mecanismo. Medir tempo, memória e disco
nesse hardware; ouvir as vozes e a mixagem reais. Depois executar os dois testes
Blender pendentes. Detalhes de funcionalidades ainda ausentes (IK físico completo,
visemas fonéticos, múltiplas vozes, preview interativo e re-render de uma cena) estão
explicitados em [LOCAL_3D.md](LOCAL_3D.md).

Configuração, comandos exatos e retomada sem apagar projetos:
[guia 3D local](LOCAL_3D.md). A primeira ação de smoke não usa o plano ChatGPT:

```powershell
.\scripts\doctor.ps1 -Smoke3D
```
