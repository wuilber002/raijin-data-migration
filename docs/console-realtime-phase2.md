# Console em tempo real — Fase 2

## Objetivo

Reduzir pressão desnecessária sobre API e PostgreSQL sem mudar o contrato
operacional: SSE continua a transportar apenas dicas de invalidação e HTTP
continua a transportar estado e comandos autenticados.

## Medidas implementadas

- Leituras HTTP continuam em modo *single-flight*: uma leitura idêntica em
  curso ou feita nos últimos cinco segundos é compartilhada pelos elementos da
  tela, em vez de gerar requisições concorrentes.
- Cada leitura recebe limite de 30 segundos. Quando a API local não responde,
  a console libera a promessa pendente e informa que a operação do servidor
  não foi cancelada; uma próxima atualização pode se recuperar normalmente.
- A remoção de uma entrada de cache após erro verifica a identidade da
  requisição. Assim, uma resposta antiga que falhe não remove uma leitura mais
  nova para a mesma URL.
- A source selecionada é conferida novamente antes de desenhar o resumo. Uma
  resposta que pertença à source anterior não pode sobrescrever o contexto que
  o operador acabou de escolher.
- Ao ficar oculta, a aba fecha sua inscrição SSE e não mantém renderizações
  pendentes. Ao voltar ao primeiro plano, ela reconecta o stream, invalida o
  cache curto e executa uma sincronização agrupada do painel ativo.
- O polling de contingência de alertas não roda em aba oculta. Com SSE saudável
  ele passa a ocorrer a cada dois minutos; se o stream estiver reconectando ou
  indisponível, permanece a cada 30 segundos.

## Resultado esperado

Várias abas abertas deixam de multiplicar assinaturas SSE e consultas de
fallback quando não estão sendo observadas. Atualizações próximas continuam
agrupadas, e a aba retorna com um snapshot HTTP consistente, sem depender de
WebSocket.

## Verificação

1. Abra DevTools → Network e confirme que `/api/stream/operations` fecha ao
   ocultar a aba e reconecta ao voltar.
2. Com SSE conectado, observe que o refresh de alertas só volta a consultar a
   cada quatro intervalos de 30 segundos.
3. Alterne rapidamente entre duas sources enquanto uma delas está carregando:
   o resumo final deve pertencer apenas à última source selecionada.
4. Simule uma API lenta. Após 30 segundos a console deve apresentar falha de
   leitura recuperável, sem deixar o painel em carregamento indefinido.

WebSocket continua fora de escopo. A fase 3 só deve ser considerada após
métricas mostrarem que SSE + snapshots HTTP ainda não atendem a necessidade.
