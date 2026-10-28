# Renderização assistida no Google Colab

O Windows prepara texto, storyboard 3D validado e áudio medido. O notebook executa somente Blender/Cycles e FFmpeg. O resultado volta para validação local e `HUMAN_REVIEW`; não existe aprovação/publicação automática. OAuth, Piper, vozes, SQLite e conexões permanecem no PC. Nenhum token, `.env`, banco, perfil ou log é exportado.

[Abrir o notebook versionado no Colab](https://colab.research.google.com/github/mrJoao28/Content-Factory/blob/b294cd057fc826ee5eb02044b9ab3bbd196985ab/notebooks/content_factory_colab.ipynb).

## Ativação no Windows

**Não atualize nem reinicie a instalação durante o render atual.** Esta funcionalidade foi desenvolvida em worktree separado. Termine o trabalho atual ou pause explicitamente e espere a liberação do lease. Depois de revisar/integrar o PR, com os processos encerrados:

```powershell
git pull --ff-only
.\scripts\setup.ps1
.\scripts\dev.ps1
```

Não apague banco/frames/output, não substitua `.env` e não execute `setup -StopRunning` enquanto houver produção ativa. A migração `0003_external_render` cria apenas o registro de exportações. Projetos antigos continuam com execução local. Não há novas variáveis nem segredos obrigatórios; `PIPER_PATH`, `PIPER_VOICE_PATH` e OAuth existentes são preservados. Não é necessário instalar Blender no PC para **preparar/exportar** um projeto Colab; FFprobe e FFmpeg continuam necessários para áudio e importação.

## Preparar e exportar

1. Na criação, escolha **Blender 3D**, duração, qualidade, resolução/FPS e **Execution location → Assisted Colab notebook**. O provider textual continua sendo a conexão/modelo já selecionados.
2. A produção gera roteiro/storyboard e narração localmente. Para em `WAITING_FOR_EXTERNAL_RENDER` depois de validar os dados e medir o áudio, antes de iniciar Blender local. O worker libera o lease e não reivindica essa espera nem incrementa tentativas.
3. Em Review studio, para um projeto existente com storyboard/áudio válidos, use **Prepare for Colab**. Se houver render/lease/upload ativo, pause e espere; a API rejeita a transferência. A mudança de local mantém revisão, roteiro e checkpoints. Preparação ainda incompleta usa a conexão textual atual; exportar dados já prontos não chama IA.
4. Escolha hardware: **GPU** permite testar OptiX e depois CUDA; as opções individuais restringem o backend. **CPU** exige escolha explícita. Clique **Prepare for Colab** para registrar a política escolhida e depois **Export package → Download input ZIP**.
5. Reexportar a mesma revisão/perfil/áudio/board devolve o mesmo `export_id`. Alterar hardware/local invalida exportações pendentes anteriores. O botão Resume genérico não inicia render local enquanto se aguarda um resultado externo. Use as ações explícitas.

O pacote inclui apenas `manifest.json` e `audio/narration.wav` PCM16 medido. O manifesto estrito contém UUIDs, revisão, board do catálogo procedural, versões, perfil (samples/seed/dimensões/FPS/hardware), hash do template normalizado LF, hash/tamanho do áudio e commit imutável do renderer. Não inclui caminhos absolutos, scripts, `.blend` ou manifesto bruto do Windows. Assets Dino/Milo/ambientes são gerados pelo código confiável do catálogo; assets arbitrários não são aceitos nesta versão.

## Executar no Colab

1. Abra o link acima; selecione **Python 3**, ambiente **hospedado pelo Colab**, e GPU disponível em **Ambiente de execução → Alterar tipo de ambiente de execução**. Runtime local usa o próprio PC e não fornece aceleração externa.
2. Execute diagnóstico e instalação. O notebook fixa **Blender Linux 4.5.3**, compatível com o template, a partir de `download.blender.org`; verifica SHA-256 oficial antes de extrair. Instala FFmpeg/bibliotecas de sistema e somente Pydantic/Pillow para o renderer. Não instala servidor, SDK/OAuth/vault nem troca drivers/CUDA. O código vem do commit confiável fixado no notebook, nunca de um endereço fornecido no ZIP.
3. Opcional: crie a pasta `MyDrive/ContentFactory`. Na célula Drive, marque `MOUNT_DRIVE=True` e execute/autorize `drive.mount`. Padrão: `/content/drive/MyDrive/ContentFactory`. Não configure Google Cloud Console/client secret/conta de serviço. A integração Drive da aplicação Windows é independente dessa autorização padrão do notebook.
4. Faça upload de **um ZIP** (até 256 MiB) ou escolha o arquivo no Drive autorizado. A validação compara commit/template, schema/catalog, áudio e caminhos antes do render. Confira o resumo da revisão/perfil.
5. Configure threads, orçamento de disco, lote de frames e tempo finito. Qualidade/resolução/FPS/samples/seed vêm da exportação registrada. Para mudá-los, altere o perfil localmente e reexporte explicitamente: o importador rejeita divergências. A política GPU testa OptiX; se incompatível, informa e tenta CUDA. Se ambos falharem, interrompe; CPU exige nova exportação explícita. `nvidia-smi` não comprova uso por Blender.
6. Execute **teste curto**: 12–24 frames reais da cena recebida. O probe GPU tem timeout de até 300 s por backend; CPU usa o limite finito configurado. Veja imagens, dispositivo efetivo e segundos/frame. A estimativa varia conforme cena/setup e não garante aceleração. Nenhum render longo começa automaticamente.
7. Após inspecionar o teste, execute **Render completo**. O progresso é real por lote. Para cancelar, interrompa a célula: o subprocesso é encerrado; frames/checkpoints válidos permanecem. Não existe progresso remoto inventado no app Windows.
8. Execute montagem/preview/download. Assista ao MP4 e baixe `<export_id>-result.zip`. Se Drive foi autorizado, também é feita uma cópia verificada do retorno.

I/O de render fica em `/content/content-factory-work`. Sem Drive, tudo em `/content` é temporário e pode desaparecer. O notebook não abre portas, SSH, túneis nem serviços web, não hospeda FastAPI/Next.js e não faz novas chamadas ao ChatGPT. O usuário supervisiona e executa as células interativamente.

## Checkpoints e retomada

Cada lote de até 120 frames é salvo localmente, compactado e copiado como shard. O índice imutável com hashes é publicado **somente após verificar a cópia persistente**. PNGs não são gravados individualmente no Drive; shards incompletos/sem índice não contam como salvos. A sessão pode perder o lote desde o último índice publicado.

Na próxima sessão: reexecute instalação, autorize Drive, carregue **o mesmo pacote** e selecione as mesmas configurações. O teste restaura os shards compatíveis; execute novamente o render completo para completar os frames ausentes. A restauração verifica hashes, numeração e dimensões. O fingerprint inclui insumos semânticos, commit/template/catalog, Blender/build, dispositivo/driver, backend, threads, qualidade, samples/seed, resolução e FPS. Caminhos `/content`, Windows e executável não participam. Export ID é correlação, não identidade dos frames.

**Não há promessa de reutilizar os 100 frames Windows/CPU atuais no Colab GPU.** Caches são separados por padrão; backend, dispositivo, versão ou perfil diferente não compartilha frames automaticamente. Os originais locais são preservados.

## Importar e revisar

Na produção original, em Review studio, use **Import result ZIP**. A API recebe ZIP bruto com limite próprio, extrai apenas arquivos permitidos e confere a exportação registrada localmente. Rejeita IDs desconhecidos, revisão desatualizada, retorno cancelado/substituído, perfil ou insumos divergentes, hashes/arquivos inválidos. Hashes enviados no próprio ZIP não provam autoria; o registro local define a comparação.

O retorno contém `result.json`, `video.mp4`, `thumbnail.png`, `report.json`; não contém scripts ou milhares de PNGs. FFprobe/FFmpeg locais conferem H.264/AAC, dimensões, duração, FPS, número de frames, decodificação completa e volume/áudio. O thumbnail utilizado é extraído novamente do vídeo validado. O relatório do notebook é proveniência declarada, não prova independente de que uma GPU foi usada. Não se confia nele para aprovar mídia.

A importação publica os arquivos por rename atômico e registra um único artefato por exportação; repetir o mesmo retorno é idempotente. Arquivos/histórico anteriores permanecem. A aprovação atual é limpa ao importar um novo MP4. O projeto vai para **HUMAN_REVIEW**; assista e aprove explicitamente o hash atual. As exigências de publicação continuam iguais. Use **Return to local render** para retomar Blender local com os checkpoints preparados, sem nova inferência/áudio; é necessário Blender local configurado.

Cancelar a produção na fábrica invalida o retorno pendente, mas não controla o runtime externo. Interrompa também a célula no Colab; não existe canal remoto entre o aplicativo e o notebook.

CLI opcional, com a API local já iniciada:

```powershell
.\.venv\Scripts\python.exe scripts/external_render.py export PROJECT_UUID input.zip --revision 1
.\.venv\Scripts\python.exe scripts/external_render.py import PROJECT_UUID result.zip
```

## Limites e diagnóstico

ZIP: até 256 MiB comprimido, 512 MiB expandido, 256 arquivos, diretório central limitado, razão de expansão até 250. São rejeitados traversal, nomes absolutos/UNC, symlinks, nomes duplicados/ambíguos, volumes/ZIP64 e arquivos fora da allowlist. Manifesto de entrada: até 2 MiB; metadados de retorno: até 64 KiB cada. Esses limites não desabilitam controles globais de upload.

Execução: padrão 2 threads, 24 frames/lote, limite interativo 1.800 s, orçamento 8 GiB; controles permitem tempo finito até 21.600 s, disco até 64 GiB e até 120 frames/lote. Ajuste explicitamente conforme disco/runtime; isso não garante disponibilidade. Sem VRAM/backend funcional, escolha outro backend autorizado ou reexporte CPU; sem disco, use Preview/reexporte ou aumente orçamento dentro do disponível. Timeout/cancelamento preserva apenas frames completos e shards verificados. Shards de outra configuração não são silenciosamente misturados.

Conforme a [FAQ oficial do Colab](https://research.google.com/colaboratory/faq.html), recursos/GPU e duração não são garantidos; sessões gratuitas podem terminar antes do teto de 12 horas. Não há garantia de 60 horas em três dias, nem compra de armazenamento que aumente cota de GPU. Não use keep-alive, auto-reconexão, múltiplas contas ou encadeamento de sessões para contornar cotas. Render assistido é computação interativa no notebook, não worker distribuído/serviço permanente.

Fontes técnicas: [Blender — render GPU Cycles](https://docs.blender.org/manual/en/latest/render/cycles/gpu_rendering.html), [distribuições oficiais 4.5](https://download.blender.org/release/Blender4.5/), [checksums Blender 4.5.3](https://download.blender.org/release/Blender4.5/blender-4.5.3.sha256). `refresh_devices()`/`compute_device_type` também foram conferidos no add-on Cycles da instalação Blender 5.2. Não foi prometida placa específica, velocidade ou operação gratuita 24/7.

## Verificação

Veja `COLAB_VALIDATION.md` para comandos/resultados realmente executados. O teste CPU local prova transporte/Blender/MP4/importação; não equivale a execução Linux/Colab/GPU ou autorização de Drive. A validação final manual requer que o proprietário execute o notebook em um runtime Colab e importe seu retorno.
