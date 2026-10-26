# Windows 11

1. Instale Python 3.11+ de https://www.python.org/downloads/windows/ e Node.js LTS de https://nodejs.org/en/download. Habilite PATH. Use Python x64 convencional se o alias Microsoft Store retornar acesso negado.
2. Instale FFmpeg com FFprobe: https://ffmpeg.org/download.html. Builds Windows sao listados no site oficial. Extraia e coloque `bin` no PATH, ou defina caminhos absolutos no .env. Valide `ffmpeg -version` e `ffprobe -version`. O FFmpeg reduzido do Playwright nao fornece os codecs/audio exigidos.
3. Instale o CLI oficial: `npm install -g @openai/codex`. Execute `codex login` e `codex login status` no usuario que rodara o backend. Nao transfira tokens para a aplicacao.
4. Abra PowerShell na raiz do projeto. Se a politica de scripts impedir execucao, use a politica permitida pela sua organizacao; os comandos manuais abaixo dispensam scripts.
5. Execute `scripts/setup.ps1`. Ele cria venv, instala dependencias, copia .env.example apenas se .env nao existir, prepara diretorios, executa migracao e doctor.
6. Configure uma voz Piper ou importe audio WAV/MP3. Para Piper, veja ENV_GUIDE. Blender e opcional: https://www.blender.org/download/.
7. Execute `scripts/dev.ps1`. Acesse http://127.0.0.1:3000. Logs ficam em data/logs. Nao publique essa aplicacao local na internet.

## Comandos manuais

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pip install openai-codex
npm.cmd ci --prefix apps/web
Copy-Item .env.example .env # apenas se ainda nao existe
$env:PYTHONPATH = "$PWD/services/api"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m factory.doctor
.\.venv\Scripts\python.exe -m uvicorn factory.main:app --host 127.0.0.1 --port 8000 --no-access-log
# outro terminal na raiz:
npm.cmd run dev --prefix apps/web
```

API: /docs fornece o contrato real. Para um worker separado, use `FACTORY_DISABLE_WORKER=1` na API e `python services/worker/main.py` no outro terminal com PYTHONPATH configurado. Nao e preciso Docker.

## Docker experimental

`docker compose up --build` e opcional. Portas do host ficam limitadas a loopback. Dentro dos containers os servidores escutam a interface isolada do container. O vault Windows DPAPI nao e portavel; integracoes OAuth em Linux/container exigem backend de keyring do sistema operacional configurado, nao fornecido pelo Compose. Portanto, Windows nativo e o caminho suportado para OAuth. Login Codex no container deve ocorrer pelo proprio CLI oficial, sem copiar auth.json.

## Sem rede

O setup precisa baixar pacotes se nao estiverem instalados. `WinError 10013` indica bloqueio de rede do ambiente e nao um erro de senha. Este desenvolvimento utilizou pacotes Python preinstalados e tarballs npm do cache local, sem trocar implementacoes por mocks. Nao ha cache privado ou dependencia do proxy temporario no repositorio final; package-lock usa URLs oficiais.
