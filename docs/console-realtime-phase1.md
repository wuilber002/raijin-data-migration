# Console em tempo real — Fase 1

## Objetivo concluído

A console deixa de depender de consultas frequentes para perceber cada avanço
operacional. O canal principal é `GET /api/stream/operations`, usando
Server-Sent Events (SSE). O protocolo é unidirecional de propósito: comandos
continuam sendo HTTP autenticado e o estado continua sendo lido dos endpoints
HTTP existentes.

## Contrato

- O endpoint exige uma sessão de console com papel `VIEWER` ou superior.
- Cada evento `change` contém somente `kind`, IDs de source/wave/projeto e
  tópicos. Não contém mensagem de evento, key S3, credencial, URL de PAR nem
  qualquer snapshot operacional.
- O PostgreSQL envia o aviso somente após o commit da transação (`pg_notify`).
  O processo web escuta o canal e replica a dica aos navegadores conectados.
- Cada navegador possui fila limitada. Sob pressão, a dica mais antiga é
  descartada em favor da mais recente; como os eventos invalidam estado, e não
  transportam estado incremental, não há perda de correção.
- Há comentário de keepalive a cada 15 segundos e os cabeçalhos impedem cache
  e buffering de proxy (`Cache-Control: no-cache, no-transform` e
  `X-Accel-Buffering: no`).

## Comportamento da interface

- Dicas próximas são agrupadas por 350 ms.
- A interface limpa apenas seu cache curto de GET e recarrega somente o painel
  ativo afetado: dashboard, queue ou source selecionada em Migrações.
- Um modal de edição de source aberto não é redesenhado pelo stream.
- A atualização periódica de alertas e o refresh configurável da fila continuam
  como contingência para interrupção do SSE, reinício do PostgreSQL, proxy sem
  suporte a streaming ou navegador sem `EventSource`.

## Verificação operacional

1. Com uma sessão autenticada, abra DevTools → Network e confirme a conexão
   contínua para `/api/stream/operations` com `text/event-stream`.
2. Inicie ou conclua uma operação e confirme a chegada de um evento `change`.
   A interface deve atualizar o painel pertinente sem recarregar a página.
3. Interrompa temporariamente o stream ou reinicie PostgreSQL: a console deve
   continuar utilizável e os refreshes de contingência devem preservar o
   estado; após a reconexão, o stream volta automaticamente.
4. Nunca use o conteúdo do stream para investigação. A evidência durável está
   nos relatórios, eventos e no bundle de diagnóstico.

WebSocket não faz parte desta fase. Ele só será avaliado se, após a medição
operacional, houver necessidade real de comunicação bidirecional de baixa
latência que SSE + HTTP não atendam.
