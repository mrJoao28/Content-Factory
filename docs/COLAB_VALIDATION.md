# Evidências da integração Colab assistida

Base inspecionada: `da3de24a6cf7726b12a2b05ea13ab83f3ea8ed20`, em 28/10/2026. Desenvolvimento no worktree `Content Factory Colab`, branch `feat/colab-assisted-render`. A instalação original permaneceu em `main`, com sua alteração pré-existente em `apps/web/next-env.d.ts`; não houve reinício, cancelamento de render, leitura/cópia de `.env` ou credenciais, exclusão de frames ou atualização de dependências da instalação ativa.

## Verificado

- `python -m pytest`: **223 passaram, 3 ignorados**. Os ignorados são renders Blender que exigem opt-in/configuração; o round-trip novo foi executado separadamente com Blender real.
- Teste direcionado final: `tests/test_external_render.py` + `tests/test_colab_notebook.py`: **23 passaram**, incluindo o render CPU real e validação reforçada de frames/áudio na importação.
- A cobertura adicional da preparação completa (provider textual controlado + narração importada real → espera externa) também passou. A rechecagem dirigida posterior teve **23 passando e 1 ignorado** por falta do opt-in Blender nessa execução; o render real já havia passado separadamente.
- Ruff: passou.
- Frontend typecheck: passou; Vitest: **7 testes passaram**; build de produção Next: passou.
- Playwright com API/Next reais em portas isoladas 8001/3001: **10 testes passaram**, incluindo preparação/exportação/importação/MP4/revisão e regressões OAuth/SSE/recuperação. Os testes não simulam as próprias rotas. Fixtures externas controladas são usadas somente nos testes.
- Notebook validado com `nbformat`; todas as células Python compiladas. O núcleo portátil foi executado diretamente no teste CPU; isso não significa que as células foram executadas em um runtime Colab.
- Migração upgrade/downgrade e preservação de projeto legado em SQLite temporário verificadas. Banco/vozes/outputs da instalação ativa não foram usados.

## Render CPU real

Fixture original sem dados pessoais: duas engrenagens procedurais no estúdio de engenharia, **0,5 s, 12 frames, 64×96, 24 FPS, Preview 8 samples, seed 0, uma thread**. Áudio conhecido de teste (tom), não narração real do usuário. Blender **5.2.3 LTS**, Cycles **CPU**, FFmpeg/FFprobe **9.0.2** em diretório de ferramentas isolado.

No round-trip final medido: preparação **14,168 s**; lote real **37,341 s**, **3,112 s/frame**, zero frames reutilizados. Outras duas execuções mediram 22,698 s e 60,684 s para o lote; carga/setup variaram. Essas medições pequenas não estimam a velocidade de uma produção infantil 720p nem provam aceleração GPU. Memória/VRAM de pico não foi medida.

O teste exportou por rota montada FastAPI, validou o pacote portátil, executou Blender e FFmpeg reais, salvou shard de checkpoint, montou o retorno e importou por HTTP até `HUMAN_REVIEW`. Uma segunda importação não criou artefato adicional. Aprovação permaneceu vazia. O thumbnail foi inspecionado visualmente; este clipe de diagnóstico não pretende demonstrar qualidade artística infantil.

Artefatos reproduzíveis ficam no worktree em `output/colab-validation/`: `input.zip`, `result.zip`, `video.mp4`, `thumbnail.png`, `measurement.json`. São fixtures correlacionadas ao banco temporário do teste: **não importe esse retorno em uma produção pessoal**. Para testar no Colab com retorno aceito na sua instalação, exporte a produção real pela interface após ativar a feature. Outputs não são commitados.

## Reproduzir os testes

Com dependências de desenvolvimento instaladas e FFmpeg/FFprobe disponíveis, em ambiente isolado:

```powershell
$env:AI_PROVIDER='codex' # baseline dos testes legados; não realiza inferência
python -m pytest
ruff check .
cd apps/web
npm ci --no-audit --no-fund
npm run typecheck
npm test
npm run build
npm run test:e2e
```

`npm ci` foi validado com o lockfile atual, sem alteração de versões. `nbformat` foi adicionado apenas ao extra de desenvolvimento; as versões das dependências existentes não foram atualizadas. Para opt-in no teste real, com Blender já instalado e FFmpeg/FFprobe configurados:

```powershell
$env:FACTORY_TEST_BLENDER='C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
python -m pytest tests/test_external_render.py::test_real_blender_export_render_import -q -s
```

`FACTORY_TEST_BLENDER` é apenas controle de teste, não configuração obrigatória da aplicação. `FACTORY_TEST_PYTHON` permite ao harness Playwright usar um interpretador existente de outro worktree, sem instalar/alterar esse ambiente. Testes usam bancos/pastas próprios e recusam reutilizar/encerrar servidores existentes nas portas de teste.

## Pendente de verificação humana

**GPU não testada; Colab hospedado não executado; Drive do Colab não autorizado.** A implementação enumera dispositivos Cycles e exige um probe de frames reais; OptiX→CUDA é política explícita, sem fallback CPU. Testes de lógica não são evidência de render GPU.

O proprietário deve abrir o notebook versionado, autorizar runtime/Drive opcionalmente, carregar uma exportação real registrada, verificar dispositivo/medição/imagens, executar render, interromper/retomar uma sessão com shards e importar o retorno. Não foi consumido o plano ChatGPT nem houve publicação. A etapa depende de acesso/consentimento do proprietário e disponibilidade do Colab.

O notebook usa Linux Blender **4.5.3**, baixado da fonte oficial com SHA-256 fixado; a compatibilidade real Linux/GPU deste ambiente ainda precisa desse teste manual. A API do Cycles foi conferida no código instalado Blender 5.2 e no [código oficial da versão 4.5.3](https://github.com/blender/blender/blob/v4.5.3/intern/cycles/blender/addon/properties.py), incluindo `refresh_devices()` e `compute_device_type`. O comportamento gratuito do Colab não é garantido para operação contínua.
