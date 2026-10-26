# TikTok

1. Crie app em https://developers.tiktok.com/apps/ e obtenha Client Key e Client Secret. Configure Login Kit e Content Posting API no portal.
2. Este adapter usa **Login Kit Web**, cujas URIs precisam ser HTTPS estaticas registradas. O exemplo http://127.0.0.1 nao e valido nesse produto. TIKTOK_REDIRECT_URI fica vazio de proposito em .env.example.
3. Para OAuth Web local, providencie um callback HTTPS sob dominio registrado que encaminhe **somente** `/auth/tiktok/callback` ao backend. Preserve state/codigo, encaminhe Host `127.0.0.1` e nao registre query strings. Nao exponha as outras rotas nem o frontend local. Esta infraestrutura externa nao e criada automaticamente pelo projeto.
4. Sem callback HTTPS/approval, use imediatamente o modo manual; renderizacao, revisao e ZIP continuam funcionando. Login Kit Desktop e uma possivel extensao futura, nao esta sendo simulado por este adapter Web.
5. Solicite `user.info.basic` e `video.upload` para envio a inbox. Conecte pela UI, complete consentimento e use Verify account.
6. Para Direct Post, solicite `video.publish`, configure Direct Post e conclua a avaliacao/auditoria necessaria no portal. So depois habilite `TIKTOK_DIRECT_POST_ENABLED=true`, reinicie e reconecte OAuth para conceder o escopo adicional.
7. Em Direct Post, consulte creator info, confira apelido/conta, selecione explicitamente privacidade dentre opcoes devolvidas, edite caption, escolha interacoes, declare publicidade e confirme direitos musicais/postagem. A API confere scopes, duracao e restricoes atuais. O conteudo recebe is_aigc=true.
8. Apps nao auditados podem ficar restritos a privado ou ser recusados. A flag local nao altera aprovacao do TikTok. Nunca contorne restricoes ou publique com valores de privacidade inventados.

Inbox usa `/v2/post/publish/inbox/video/init/`, transferencia sequencial em chunks e consulta `/v2/post/publish/status/fetch/`. SEND_TO_USER_INBOX nao significa publicacao. Direct Post usa `/v2/post/publish/video/init/`; so PUBLISH_COMPLETE confirma publicacao. Nenhum agendamento nativo e inventado.

Para modo manual: aprove video, baixe ZIP com MP4/caption/tags/metadados/SRT, marque horario no calendario, finalize na plataforma e registre URL HTTPS final. A confirmacao fica identificada como manual.

OAuth implementa state de uso unico, exchange, refresh e revogacao. Nenhum token aparece nos dados enviados ao frontend. A transferencia so aceita hosts HTTPS TikTok esperados. Resultados ambiguos exigem reconciliacao antes de novo upload.

Oficial: [Login Kit Web](https://developers.tiktok.com/doc/login-kit-web/), [Upload](https://developers.tiktok.com/doc/content-posting-api-get-started-upload), [Direct Post](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post), [transferencia](https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide).
