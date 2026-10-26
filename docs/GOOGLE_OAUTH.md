# Google OAuth e Drive

1. Abra https://console.cloud.google.com/ e crie um projeto para esta aplicacao.
2. Em APIs & Services > Library habilite Google Drive API e YouTube Data API v3 se for usar ambos.
3. Configure OAuth consent screen / Google Auth Platform: nome, email, audiencia e usuarios de teste. Nao escolha producao/auditoria sem preencher os requisitos Google.
4. Em Credentials crie um OAuth client do tipo **Web application**. Cadastre exatamente `http://127.0.0.1:8000/auth/google/callback` (adapte a porta em todos os lugares se necessario).
5. Preencha GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET e GOOGLE_REDIRECT_URI em .env. Reinicie a API. Nao envie o JSON do cliente para o Git.
6. Em Google Drive clique Connect account, complete o consentimento e depois Verify account. YouTube e conectado separadamente para permitir contas distintas e escopos menores.
7. Drive solicita apenas `drive.file`. Liste pastas acessiveis ou crie o layout. Escolha a pasta raiz no painel; a preferencia fica no SQLite, sem tokens. GOOGLE_DRIVE_FOLDER_ID e alternativa de configuracao inicial.
8. Pasta existente pode nao estar acessivel com drive.file mesmo sabendo seu ID. Esta versao lista pastas acessiveis/criadas pelo app, sem Google Picker. Use Create folder layout para uma raiz criada pelo proprio aplicativo. Nao amplie automaticamente para acesso total ao Drive.
9. Aprove um MP4, confirme upload e confira IDs/links. A API envia tambem thumbnail, roteiro, SRT e metadados quando existentes. Diretorios sao reutilizados por nome e pai.

Tokens de usuario e URLs de sessao resumivel ficam no vault Windows DPAPI; scopes e IDs publicos ficam no SQLite. O segredo do cliente fica no .env local. State aleatorio de uso unico expira em 10 minutos; Google utiliza PKCE S256. Refresh e revogacao sao implementados.

Uploads persistem a URL resumivel no vault. Uma resposta ambigua nao dispara um novo upload automaticamente. Registros NEEDS_RECONCILIATION exigem conferir a conta remota antes de reiniciar, para evitar duplicatas. Uploads interrompidos com sessao conhecida podem retomar no mesmo botao com nova confirmacao. Drive consulta appProperties para reutilizar arquivos ja entregues. Reconciliacao automatica de todos os tipos de falha ainda e limitada.

Falhas comuns: redirect_uri_mismatch (URI diferente), access_denied (tester/consentimento), invalid_grant (login expirou/revogado), 403 (escopo/permissao/quota), arquivo/pasta inacessivel com drive.file.

Oficial: [OAuth Web Server](https://developers.google.com/identity/protocols/oauth2/web-server), [Drive uploads](https://developers.google.com/drive/api/guides/manage-uploads), [scopes](https://developers.google.com/drive/api/guides/api-specific-auth).
