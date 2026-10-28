# Verificações da produção musical — 28/10/2026

Base inspecionada: `ae1ae8f087c33292d185848b659fc50e18c558ec`.
Branch: `feat/children-music-studio`. Checkout isolado:
`C:/Users/joaof/Content Factory Music`. A instalação original permaneceu na mesma
revisão e com as alterações locais de `next-env.d.ts`/egg-info preservadas.
Durante o trabalho, `main` avançou para `bd1d56158c80a6261e1b6c327be0ce1c533d975b`.
A mudança era no link de abertura do notebook. Ela foi conciliada nesta branch,
preservando metadados e usando o link da nova versão revisada. Nenhuma célula de
código remota foi descartada. A branch musical não foi integrada automaticamente à main.

## O que foi executado

- Instalação limpa do frontend com o lockfile existente: `npm ci --no-audit --no-fund`.
- Última suíte completa Python: **240 passaram, 4 pulados** (380,40 s), mais uma
  regressão dirigida adicional de preservação de histórico publicada depois da coleta
  dessa execução. Antes disso, a suíte completa também passou com 237 testes.
  Os testes não usam a conta ChatGPT real.
- Verificação dirigida de áudio/Codex e Music Studio: **18 passaram, 1 pulado**.
- Suíte musical final, com Blender habilitado: **19 passaram**, sem skips,
  em 122,11 s. Após a proteção da importação multipart, seus dois testes dirigidos
  de importação/mixagem e conflito também passaram.
- TypeScript strict/typecheck, **7 testes Vitest**, build de produção Next.js.
- **11 testes Playwright**, usando API FastAPI e frontend reais em 127.0.0.1:8001/3001,
  banco/output isolados e worker desabilitado nos testes de UI. Incluem editar/salvar
  plano musical, persistir volume, bloquear geração paga sem consentimento, mostrar
  áudio ausente, cancelar operação, importar um WAV real e processar a mixagem pela
  fila até carregar o player final. A fixture é um tom, não evidência de canto.
  Login, revisão e Colab existentes
  continuam cobertos. Os processos da instalação em uso não foram reiniciados.
- Notebook validado com nbformat e todas as células Python compiladas. Isso não
  equivale a execução no runtime Colab.
- Os quatro skips da suíte padrão são opt-ins de testes Blender. O round-trip
  musical foi executado separadamente com o executável explícito e passou.
- Plano original de 35 s validado contra Pydantic: `examples/music/helping-hands.json`.
  É planejamento/letra, sem afirmar que existe uma gravação cantada correspondente.
- Montagem de **620 s** em segmentos de 300 + 300 + 20 s, com arquivos PCM reais,
  pausa explícita e invalidação seletiva. Os tons dessa fixture são áudio de teste,
  não canto ou uma demonstração musical comercial.
- Compilação real de dois MP4s aprovados: montagem FFmpeg, validação técnica, áudio
  PCM final e novo `HUMAN_REVIEW`, sem herdar aprovação das fontes.

## Round-trip real Blender CPU

`test_real_blender_musical_round_trip` executa importação/exportação pelas rotas
montadas, síntese instrumental local, mixagem validada, Cycles CPU, composição AAC,
checkpoint em shards, ZIP de retorno e importação até `HUMAN_REVIEW`. O teste compara
também o áudio decodificado do MP4 com o WAV exportado (correlação acima de 0,95),
para detectar uso de áudio antigo, nova trilha ou deslocamento indevido.

Execução CPU mais recente observada:

| Parâmetro | Resultado |
|---|---|
| Sistema | Windows, Python 3.14.2, Node 26.8.1 |
| Blender | 5.2.3 LTS, build e13b728c6880 |
| Motor/dispositivo | Cycles CPU, 1 thread, sem GPU |
| Perfil diagnóstico | 64×96, 24 FPS, 8 samples |
| Vídeo | 12 frames / 0,5 s, instrumental original, sem voz cantada |
| Preparação | 12,924 s |
| Lote de frames | 20,841 s, aproximadamente 1,74 s/frame |
| Tempo no runner após preparação | 21,338 s |
| Aprovação/publicação | Nenhuma; resultado aguardando revisão humana |

Os números variaram nas repetições. Não extrapole esse teste minúsculo para HD ou
um episódio inteiro. Não foi medido pico de RAM/VRAM; não há medição de GPU.

Artefatos locais de evidência, fora do Git:

```text
output/music-evidence/cdbe7464-4c4c-47e1-b3f4-4cd6db9c1ec9/
  input.zip
  result.zip
  result/video.mp4
  result/thumbnail.png
  result/report.json
```

O campo genérico `origin: assisted-notebook` do relatório é produzido pelo runner
portável; nesta verificação ele foi executado **localmente no Windows**, não no
Google Colab. Frames do início, meio e fim foram inspecionados, mas a resolução/duração não permitem
declarar acabamento artístico, atuação ou coreografia de produção final.

Para reproduzir, use os comandos em [MUSIC_STUDIO.md](MUSIC_STUDIO.md). Cada execução
de evidência recebe subpasta própria; arquivos anteriores não são apagados.

## Pendências reais

- O proprietário informou não possuir uma canção original disponível para o teste.
  Não foi usado serviço pago nem autorizada geração musical externa. A integração
  oficial tem testes HTTP controlados, mas **canto com uma conta real não foi
  validado**, e a demonstração cantada de 35 s não foi produzida.
- Não foram executadas inferência ChatGPT real, geração Piper com a voz do usuário,
  render GPU nem uma sessão hospedada Colab nesta mudança. O login existente foi
  preservado; os testes não copiam suas credenciais.
- O fluxo Colab precisa do teste manual documentado: autorizar Drive no notebook,
  carregar o pacote, verificar o dispositivo, renderizar/salvar/restaurar e importar.
- Sincronização de boca é por energia de áudio ou marcadores manuais, não por fonemas.
  Marcadores de batida são editáveis; não há medição automática confiável de BPM.
- Biblioteca visual continua com os rigs confiáveis atuais. Outros personagens
  requerem novos assets/rigs versionados no catálogo. O planner não inventa esses assets.
- Edição avançada é por JSON, com players, controles de volume/fade e tabela de
  tempos; não há editor de waveform com arrastar clipes nesta versão.
