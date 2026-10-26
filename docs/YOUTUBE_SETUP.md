# YouTube

Use o mesmo projeto/cliente OAuth descrito em GOOGLE_OAUTH.md. Habilite YouTube Data API v3 na Library e conecte pelo painel YouTube. Scopes solicitados: youtube.upload e youtube.readonly; o segundo permite consultar canal/status e estatisticas expostas.

Verify account usa channels.list(mine=true). Copie o channel ID retornado para YOUTUBE_CHANNEL_ID; essa verificacao impede enviar ao canal errado quando ha Brand Accounts. O callback e compartilhado com Google, mas a credencial fica separada no vault.

O upload e resumivel, com snippet (titulo, descricao, tags, idioma) e status (privacidade e selfDeclaredMadeForKids derivado do canal, nunca de uma resposta livre da IA). WonderNest e sempre Made for Kids. Revise audiencia no YouTube Studio.

Para agendar: crie um plano futuro no calendario com modo youtube; aprove o video; no painel confirme o upload. O payload envia privacyStatus=private e publishAt UTC. O plano local continua PLANNED ate consulta da plataforma confirmar o agendamento. A aceitacao do upload nao comprova publicacao publica.

Use Refresh status para consultar uploadStatus/privacyStatus/publishAt. Somente um video processado e publico e marcado PUBLISHED pela API. Uma publicacao manual registrada pelo usuario usa MANUAL_CONFIRMED e api_verified=false.

Projetos nao auditados podem ter uploads limitados a privado. As quotas da sua conta/projeto sao a fonte de verdade; nao ha numeros de quota fixados na UI. Um erro 403/429 mostra diagnostico sem prometer aumento de limite.

A thumbnail PNG e exportada e enviada ao Drive. Depois do upload, use Upload thumbnail no registro da publicacao; o endpoint oficial thumbnails.set confirma o resultado separadamente. Restricoes de Shorts e funcionalidades de thumbnail dependem da plataforma.

Alternativa manual: baixe o ZIP de postagem, abra https://studio.youtube.com/, envie MP4, metadados/legenda/thumbnail, defina Made for Kids e horario e depois registre a URL final. A aplicacao nao automatiza a interface do Studio.

Oficial: [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert), [recurso videos/status](https://developers.google.com/youtube/v3/docs/videos), [upload resumivel](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol).
