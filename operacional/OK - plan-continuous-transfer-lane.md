# Plano da fila contínua de transferência

## Registro de implementação

- **Tempo de implementação consolidado:** **3h 49min 00s**.
  Inclui 2h 48min 32s das etapas anteriores, 20min 57s da primeira revisão,
  32min da reabertura de escala, handoff durável e leitura da Queue e 7min
  31s da validação final em 31/08/2026. Não inclui aceite externo,
  acompanhamento de restore real nem tempo de operação do cliente.
- **Revisão complementar em 28/08/2026:** prioridade multifator,
  persistência de segmentos, relatório por intervalo, prioridade de negócio
  por source, diagnóstico de ociosidade, guarda de capacidade do host e custo
  observado da cópia temporária foram concluídos. A etapa final acrescentou
  lotes de despacho duráveis, reavaliação por vaga Raiju livre e escalonamento
  conservador por conclusão de objeto. A suíte de regressão foi executada ao
  final: **217 testes aprovados** (quatro avisos de depreciação).
- **Situação em 31/08/2026:** a primeira entrega estabeleceu a fila durável e
  a integração básica. As auditorias posteriores corrigiram os desvios de
  preempção, escala e leitura operacional. Todos os itens de código e
  regressão local estão em `[x]`; o único item `[ ]` é o aceite operacional em
  AWS real, que depende de uma execução controlada.

## Objetivo

Evoluir o processamento do RAIJIN para separar de forma explícita o agendamento de restore da transferência dos objetos. As waves continuarão sendo a unidade de seleção, manifesto, restore, retenção, custo, aprovação e evidência. A cópia, porém, será alimentada por uma **fila contínua de transferência**: assim que um objeto restaurado se tornar elegível, ele poderá ser consumido por workers livres, independentemente de a wave de origem estar integralmente restaurada.

O objetivo é manter a lane de transferência ocupada pelo maior tempo possível, reduzir a espera artificial entre waves, responder a atrasos de restore ou variações de throughput e diminuir o tempo de permanência das cópias temporárias restauradas no S3.

## Status do plano

**IMPLEMENTAÇÃO FUNCIONAL CONCLUÍDA — aceite completo pendente — 31/08/2026.**

Os critérios ainda não comprovados em ambiente equivalente ao de produção são:

- [ ] executar uma migração controlada em AWS real, com Deep Archive, para
  comparar previsão, disponibilidade observada, ocupação da lane, custo e
  consumo real de requests.
- [ ] executar uma integração PostgreSQL concorrente que comprove os caminhos
  `FOR UPDATE SKIP LOCKED`, expiração de lease e recuperação de handoff com
  duas instâncias de Raikou/Raiju;
- [ ] executar cenário Fujin de ponta a ponta que force um micro-lote crítico
  durante cópia normal e comprove, por segmentos persistidos, que o Raiju
  concluiu o objeto em curso e recebeu o sucessor reservado antes de trabalho
  normal.

### Auditoria independente de completude — 31/08/2026

Esta auditoria confrontou cada decisão do plano com modelos, workers, API,
interface e regressões. A implementação funcional está presente; os itens
abertos abaixo são lacunas de **validação**, não funcionalidades ausentes:

- [x] a estratégia deixou de pertencer à source. Criação manual, automática e
  por prefixo registram a escolha na wave; o método `Pipeline contínuo` exibe
  a liberação imediata como regra imutável;
- [x] o horizonte dinâmico materializa três waves por padrão, mas respeita dois
  slots iniciais de restore; o Raikou replaneja somente waves não submetidas;
- [x] o dispatcher é por objeto e por source, usa lotes normais de 100
  objetos/1 GiB, micro-lotes críticos de 20 objetos/256 MiB e prioridade 90
  configurável;
- [x] Queue, timeline e relatório usam os registros duráveis da lane e exibem
  backlog, prioridade, expiração, diagnóstico de ociosidade, segmentos e
  handoffs reservados;
- [x] a interface expõe prioridade de negócio por source e as configurações
  globais de estoque, lote e urgência; o modelo multi-source/projeto continua
  deliberadamente fora do escopo desta lane;
- [ ] falta o teste de integração acima para executar o handoff dentro do loop
  real de threads, em vez de validar somente sua seleção, reserva e contrato;
- [ ] falta o teste PostgreSQL concorrente acima; SQLite não reproduz
  `SKIP LOCKED` nem a contenção de produção;
- [ ] falta o aceite AWS real acima. Fujin valida contrato, estados, tempo e
  falhas controladas, mas não preço, latência, throttling e semântica AWS reais.

Todos os demais itens deste plano possuem implementação e regressão local.

### Complemento de aceite — 28/08/2026

A auditoria de implementação encontrou desvios e os corrigiu nesta revisão.
O estado abaixo representa o código atual; o aceite em AWS real continua sendo
o único ponto externo que não pode ser substituído por testes locais:

- [x] preempção cooperativa por vaga Raiju livre: o dispatcher não pode esperar
  o término de todo o lote para admitir um micro-lote crítico;
- [x] escalonamento contínuo de Raiju entre conclusões de objeto: novos slots
  são recalculados a cada conclusão e recebem somente a parcela livre do
  throughput, sem interromper objetos/partes multipart ativos;
- [x] entidade durável de lote de despacho, com motivo, prioridade, itens,
  início/fim, preempção e resultado auditáveis;
- [x] *cooldown* persistente e efetivamente consultado pela preempção, para
  impedir alternância excessiva entre handoffs;
- [x] seletor de prioridade de negócio da source com `Sem preferência`, `#1` …,
  preservando deadline como critério soberano;
- [x] interface explícita: método dinâmico identificado como pipeline contínuo,
  ajuda contextual e remoção definitiva do bloco legado de estratégia da source;
- [x] testes comportamentais de preempção, lote crítico, escalonamento e
  evidência de lote. A suíte local aprovada cobre a seleção do Raiju com menor
  trabalho pendente, o bloqueio temporário de handoff e a explicação da próxima
  decisão da lane.
- [x] Queue expõe a próxima decisão durável do Raikou, com source, wave,
  prioridade, motivo, bytes, expiração e duração prevista, sem efetuar chamada
  adicional à AWS.
- [x] remoção do antigo dispatcher exclusivo por wave e das funções de UI
  duplicadas/obsoletas que ainda remetiam ao planejamento dinâmico anterior.
- [x] proteção Fujin: indisponibilidade simulada antes da expiração observada
  vira `SIMULATOR_RESTORE_STATE_MISMATCH` recuperável; não dispara aprovação
  nem custo de um novo restore.

Este documento é a referência operacional da evolução. Cada item concluído deve ser marcado com `[x]`. Mudanças de decisão deverão registrar o impacto nos estados, contratos, critérios de aceite e estratégia de migração dos dados de homologação.

### Reabertura de completude e escala — 31/08/2026

A última auditoria reabriu o plano porque as entregas anteriores ainda
possuíam dois riscos práticos: a preempção era apenas registrada como evento
e a admissão/atualização da lane podia carregar uma wave inteira em memória.
Os pontos abaixo completam o contrato acordado e deixam explícito o que não
faz parte deste plano.

- [x] **Handoff cooperativo efetivo:** o Raikou reserva duravelmente um item
  crítico para o Raiju com menor tempo restante. O Raiju conclui somente o
  objeto atual; a vaga liberada inicia o sucessor reservado antes de qualquer
  item normal. A reserva, seu instante e os eventos de reserva/execução ficam
  persistidos; reinício ou expiração de lease desfazem uma reserva abandonada
  com segurança.
- [x] **Escala de milhões de objetos:** admissão idempotente de objetos
  restaurados em páginas de 1.000, atualização de prioridades em páginas de
  1.000 e candidatos de claim limitados a 256. A razão de disponibilidade da
  wave continua correta porque é calculada por agregação SQL, não pelo tamanho
  da página. Nenhum desses caminhos materializa a wave em Python.
- [x] **Leitura operacional escalável:** Queue usa agregados SQL para totais
  de objetos/bytes/tempo e carrega somente os objetos efetivamente em cópia.
  Também mostra handoffs críticos já reservados e a duração prevista da
  próxima decisão, sem chamadas à AWS.
- [x] **Regressão adicional:** cobertos pageamento de admissão, idempotência,
  campos duráveis de handoff, reserva cooperativa, páginas de prioridade/claim
  e a exposição da decisão/handoff na interface. Resultado final local:
  **219 testes aprovados**; restam somente quatro avisos de depreciação de
  dependências. A execução final completa levou 14,62 segundos.
- [x] **Coerência de escopo:** a lane atual é serializada por *source*;
  multiprojeto/multi-source continua pertencendo ao plano próprio de projetos
  de migração e não é uma lacuna silenciosa desta entrega.
- [ ] **Aceite AWS real:** confirmar sob carga controlada o comportamento de
  `FOR UPDATE SKIP LOCKED`, multipart, limites de throughput observados,
  consumo de requests e recuperação após reinício. Não pode ser substituído
  por Fujin ou por regressão SQLite.

### Entrega inicial e correção de escopo

O dispatcher por wave foi substituído pelo handler `TRANSFER_CONTINUOUS` e por
itens duráveis em `transfer_queue_items`. A revisão de completude concluiu a
prioridade multifator, a preempção cooperativa, os segmentos reais da lane no
timeline, as métricas de consumo e o custo observado. A única pendência é o
aceite controlado em AWS real descrito acima.

## Problema do modelo atual

No modelo por wave, a transferência tende a ficar acoplada ao estado geral da wave. Quando uma wave está restaurando parcialmente e a próxima ainda não está pronta, o scheduler pode deixar a lane sem trabalho mesmo havendo objetos restaurados em outras waves.

Esse acoplamento reduz a ocupação do link e força a previsão a acertar, antecipadamente, a combinação de tamanho, duração, restore e retenção de cada wave. Em condições reais, restauração e throughput variam; portanto, a decisão deve ser guiada pelo estoque real de objetos disponíveis e pelo risco de expiração, não apenas pelo plano inicial da wave.

## Arquitetura proposta

```text
Discovery / inventory
        │
        ▼
Waves de restore
  ├── seleção de objetos
  ├── manifesto / S3 Batch Operations
  ├── custo e aprovação
  ├── polling de disponibilidade
  └── retenção e expiração
        │
        │ objeto disponível e elegível
        ▼
Fila contínua de transferência
  ├── priorização por expiração e elegibilidade
  ├── reserva de throughput e fairness
  ├── checkpoints / leases / retries
  └── despacho aos Raiju de transferência
        │
        ▼
Destino OCI e evidência de integridade
```

Não haverá uma “wave virtual” persistida que substitua as waves reais. A fila contínua será uma **lane operacional durável**, e cada item conservará a referência obrigatória à source, bucket, região, wave de restore, objeto, versão, custo e evidências de origem.

## Decisões consolidadas

### Wave continua sendo a fronteira de restore

Uma wave continuará sendo proprietária de:

- seleção de objetos e limites de planejamento;
- manifesto e Batch Job de restore;
- tier, retenção, custo estimado e aprovação de novo restore;
- timestamps de solicitação, primeiro e último objeto disponível;
- expiração da cópia restaurada;
- relatório e auditoria do restore.

Uma wave não será concluída apenas porque seus objetos entraram na fila contínua. Ela será concluída quando todos os seus objetos estiverem transferidos e validados conforme a política de integridade.

### A fila contínua é por objeto

Cada item elegível conterá, no mínimo:

```text
source_id
wave_id
object_id
bucket / key / version_id
size_bytes
available_at
restore_expires_at
predicted_transfer_seconds
priority_score
state / lease / attempts
```

O item não duplicará o inventário. Ele será uma referência idempotente ao objeto da wave e deverá ser único para a combinação `wave_id + object_id + versão aplicável`.

### Elegibilidade e transferência imediata

Um objeto entra na fila assim que sua disponibilidade for observada por polling. Não haverá limiar percentual de disponibilidade por wave: a lane contínua começa a consumir trabalho imediatamente, porque esperar 15% de uma wave pode desperdiçar uma janela de retenção já paga.

O controle de segurança passa a ser global e baseado em estoque real de cópia: o Raikou mantém uma reserva alvo de **6 horas**, uma reserva mínima de **3 horas** e um limite máximo de **24 horas**, todos configuráveis globalmente. A reserva considera bytes elegíveis, duração prevista por objeto, throughput efetivo, retries e margem operacional. A wave continua em `RESTORING` enquanto houver objetos indisponíveis e pode simultaneamente drenar objetos já liberados.

### Uma lane de transferência por source nesta versão

Nesta versão há uma lane contínua por source ativa. Seus Raiju compartilham a
mesma fila de objetos dessa source e recebem objetos individuais ou pequenos
lotes compatíveis, sem que uma wave monopolize a cópia. A arbitragem entre
sources e o escopo de projeto de migração serão introduzidos pelo plano próprio
de projetos; não são inferidos nem simulados silenciosamente nesta lane.

O número efetivo de Raiju será controlado pelo scheduler, nunca abaixo de **5** workers. A expansão respeita throughput observado, CPU, memória, backlog disponível e limites de multipart. O modelo inicial opera uma lane por source; o schema já reserva `project_id` para a evolução multi-source, que ainda não pertence ao escopo desta versão.

### Lotes, prioridade e preempção segura

O Raikou forma lotes normais de, no máximo, **100 objetos ou 1 GiB**, o que ocorrer primeiro. Objetos da mesma prioridade são agrupados; itens críticos não são misturados a itens normais.

A prioridade é um score de **0 a 100**, derivado principalmente do *slack*: `expiração − duração prevista − orçamento de retry − margem operacional`. As faixas são normal (0–59), elevada (60–79), urgente (80–89) e crítica (90–100). Objetos críticos podem formar micro-lotes de até **20 objetos ou 256 MiB**.

Em prioridade crítica, a preempção é cooperativa: o Raiju conclui o objeto ou a parte multipart em curso, devolve ao estado `READY` apenas itens ainda não iniciados e assume o micro-lote crítico. A escolha recai sobre o Raiju com menor tempo restante estimado; há *cooldown* para impedir alternância excessiva. Nenhum objeto ou parte multipart é interrompido.

### Restore scheduler separado do transfer dispatcher

Dois componentes lógicos atuarão sobre a mesma base durável:

1. **Restore scheduler**: mantém um horizonte limitado de waves, solicita restores antecipados, controla slots, estima disponibilidade e procura manter uma reserva saudável de bytes disponíveis.
2. **Transfer dispatcher**: mantém Raiju ocupados, escolhe objetos elegíveis e prioriza expiração, duração prevista, tamanho, retries e fairness.

Eles poderão estar no mesmo processo de governança inicialmente, mas terão handlers, contratos, métricas e decisões separáveis para preparar a futura arquitetura distribuída. O restore scheduler começa com **2 slots** e pode escalar, por decisão auditável do Raikou, até **4 slots**. Um slot é liberado quando a wave fica 100% disponível ou entra em estado terminal que não pode avançar.

### Priorização por deadline, não somente por ordem de wave

O dispatcher calculará um score explicável. A ordem inicial será:

1. objeto cuja cópia restaurada expira mais cedo;
2. objeto que cabe com segurança na janela restante, considerando duração prevista e reserva operacional;
3. objeto de wave com maior porcentagem disponível, para reduzir fragmentação e liberar slots de restore;
4. objeto pequeno que evita ociosidade enquanto um multipart grande ainda não é elegível;
5. regra de anti-starvation para que uma wave não fique indefinidamente atrás de outras.

O score, seus componentes e a decisão serão persistidos no histórico operacional. Cada source terá prioridade de negócio configurável (`ANY`, `#1`, `#2` …); ela funciona como desempate/fairness, jamais permite ignorar um deadline crítico.

### Retenção menor é consequência, não garantia

A fila contínua permite iniciar cópia logo após a disponibilidade e, portanto, pode reduzir a necessidade de retenções longas. Ainda assim, a retenção será validada por previsão conservadora.

O scheduler não poderá assumir que 24 horas representam 24 horas úteis de cópia. A decisão considerará throughput observado, overhead por arquivo, multipart, margem operacional, backlog disponível, retries e variação recente. Se a janela não for viável, a wave deverá ser menor, a retenção maior ou o operador deverá receber um alerta antes da submissão.

### Polling e chamadas AWS

O polling permanecerá focado nos objetos pertencentes às waves em restore. A entrada na fila contínua será derivada da mesma evidência de disponibilidade já coletada; ela não deve criar um ciclo adicional de chamadas AWS por objeto.

Depois da primeira disponibilidade observada, o polling seguirá a política adaptativa existente: mais frequente quando a estratégia liberar arquivos à medida que chegam e mais espaçado quando a transferência exigir disponibilidade integral.

## Estados propostos

### Wave

| Estado | Significado |
|---|---|
| `RESTORE_SCHEDULED` | Planejada, ainda sem solicitação efetiva. |
| `RESTORING` | Restore solicitado; pode possuir objetos entrando na fila contínua. |
| `RESTORE_DRAINING` | Há objetos disponíveis sendo transferidos, porém ainda existem objetos indisponíveis. |
| `RESTORED` | Todos os objetos estão disponíveis; podem estar pendentes, em cópia ou concluídos. |
| `TRANSFER_DRAINING` | Não há restore pendente; restam objetos da wave na fila ou em cópia. |
| `COMPLETED` | Todos os objetos foram transferidos e passaram pela validação normal. |
| `COMPLETED_AUDITED` | Além da validação normal, houve auditoria profunda bem-sucedida. |
| `RESTORE_REAPPROVAL_REQUIRED` | A cópia restaurada expirou antes da cópia; novo restore requer aprovação explícita. |

Os estados legados equivalentes deverão ser migrados ou removidos conforme a diretriz de homologação: não será mantida compatibilidade desnecessária com dados descartáveis.

### Item da fila contínua

| Estado | Significado |
|---|---|
| `AVAILABLE` | Restore observado; aguarda política de admissão ou worker. |
| `READY` | Elegível para claim por Raiju. |
| `LEASED` | Está sob responsabilidade de um Raiju. |
| `MULTIPART_RESUME` | Requer retomada de upload multipart. |
| `TRANSFERRED` | Cópia e validação normal concluídas. |
| `RETRY_WAIT` | Falha transitória com próxima tentativa agendada. |
| `EXPIRED` | Cópia restaurada expirou antes da conclusão. |
| `REAPPROVAL_REQUIRED` | Somente o operador pode autorizar novo restore. |
| `CANCELLED` | Wave/source/projeto foi pausado, arquivado ou cancelado. |

## Observabilidade e interface

### Queue

A tela Queue terá duas áreas distintas:

- **Restore schedule**: waves planejadas, jobs submetidos, slots ocupados, previsão e risco de janela.
- **Continuous transfer lane**: bytes disponíveis, bytes em cópia, tempo até a expiração mais próxima, Raiju ativos/idle, objetos por estado e próxima decisão de despacho.

O operador poderá abrir uma wave para ver seus objetos disponíveis, transferidos, pendentes, expirados e em retry. A visualização não deve sugerir que uma wave inteira monopoliza a transferência.

### Timeline

O inventário de bordo continuará representar restore, margem operacional e transferência por wave. A fase de transferência poderá surgir em intervalos descontínuos, pois seus objetos podem alternar com os de outras waves. O tooltip deve informar:

- tipo da fase;
- início observado ou previsto;
- duração observada/estimada;
- bytes e objetos transferidos naquele intervalo;
- razão de entrada ou saída da lane;
- expiração mais próxima da wave naquele momento.

### Métricas

Métricas mínimas:

- bytes e objetos `AVAILABLE`, `READY`, `LEASED`, `RETRY_WAIT` e `EXPIRED`;
- ocupação da lane e períodos de ociosidade explicados;
- idade e deadline do item mais urgente;
- taxa de entrada de objetos restaurados versus taxa de consumo;
- previsão de esgotamento do backlog disponível;
- slots de restore ocupados, previstos e elegíveis;
- utilização de Raiju por tipo, ativos e idle;
- decisões de dispatch, preempção e anti-starvation.

## Plano de implementação

### Fase 0 — contrato, schema e invariantes

- [x] Modelar tabela durável de itens da fila contínua e seus índices por estado, deadline, source e wave.
- [x] Criar constraint idempotente para um único item ativo por objeto/wave/versão.
- [x] Criar eventos e motivos normalizados para entrada, claim, retry, expiração, cancelamento e conclusão.
- [x] Definir migration dos estados de wave para `RESTORE_DRAINING` e `TRANSFER_DRAINING`.
- [x] Documentar invariantes: um objeto não pode possuir dois leases, não pode transferir depois de expirar e não pode ser re-restaurado sem aprovação quando exigida.
- [x] Remover caminhos de execução e contratos de interface incompatíveis com a transferência exclusiva por wave.

**Marco:** schema suporta disponibilidade por objeto e fila contínua sem mudar o dispatcher ativo.

### Fase 1 — alimentar a fila a partir do polling

- [x] Alterar polling para registrar disponibilidade individual de objeto de modo idempotente.
- [x] Inserir objetos disponíveis na fila contínua sem chamadas AWS adicionais.
- [x] Persistir `available_at`, `restore_expires_at` e evidência que determinou a disponibilidade.
- [x] Implementar contador de bytes disponíveis por wave/source e percentual de liberação.
- [x] Aplicar liberação imediata por objeto e manter o buffer global de 3h/6h/24h.
- [x] Registrar diagnósticos para expiração, ausência de evidência e inconsistência de estado no evento e relatório da wave.

**Marco:** objetos restaurados passam a uma fila durável, mesmo antes do dispatcher ser usado para copiá-los.

### Fase 2 — transfer dispatcher contínuo

- [x] Separar o claim de objetos do claim exclusivo de uma wave.
- [x] Implementar seleção por deadline, viabilidade, tamanho, reserva e ordenação estável anti-starvation dentro da source. A prioridade persiste componentes de deadline, disponibilidade, idade, tamanho e ordem de negócio; o índice da fila preserva a ordenação estável.
- [x] Delegar objetos ou pequenos lotes aos Raiju de transferência existentes.
- [x] Reutilizar multipart, SHA-256, checkpoints, retries, evidência e limites de throughput atuais.
- [x] Liberar imediatamente a lane quando uma wave ficar sem objetos elegíveis.
- [x] Garantir que pausa, arquivamento e falha de source/wave cancelem ou bloqueiem itens corretamente.

**Marco:** workers transferem continuamente objetos de mais de uma wave elegível sem alterar a semântica de integridade.

### Fase 3 — estados, conclusão e reaprovação

- [x] Calcular estado de wave a partir de seus objetos e tasks, sem transições contraditórias.
- [x] Implementar `RESTORE_DRAINING` e `TRANSFER_DRAINING` na API, interface, relatórios e timeline.
- [x] Marcar objeto expirado e wave `RESTORE_REAPPROVAL_REQUIRED` sem tentar novo restore automaticamente.
- [x] Exigir aprovação explícita e auditada para novo restore, com nova estimativa de custo.
- [x] Concluir wave somente quando todos os objetos estiverem `TRANSFERRED` e íntegros.
- [x] Ajustar conclusão de source e execução Fujin para o novo modelo; o schema reserva `project_id` para a evolução multi-source.

**Marco:** expiração, reprocessamento e conclusão refletem o estado real dos objetos, sem perda de evidência.

### Fase 4 — restore scheduler guiado por backlog

- [x] Calcular estoque de bytes disponíveis e previsão de esgotamento da lane.
- [x] Manter alvo configurável de reserva mínima e máxima de bytes/tempo disponíveis.
- [x] Submeter apenas o horizonte configurado de restores, inicialmente três waves.
- [x] Respeitar slots de restore e permitir expansão somente mediante sinais históricos definidos.
- [x] Recalcular tamanho/composição das próximas waves ainda não submetidas conforme throughput, liberação e expiração observados.
- [x] Priorizar waves que reduzam períodos previstos de ociosidade sem comprometer deadlines. A prioridade é por deadline, disponibilidade, idade, tamanho e ordem de negócio; a arbitragem entre sources/projetos permanece explicitamente fora do escopo da lane por source.
- [x] Registrar o motivo de toda antecipação, postergação, resize ou seleção.

**Marco:** o scheduler deixa de planejar todas as waves de uma vez e passa a alimentar continuamente a fila de transferência.

### Fase 5 — timeline, Queue e relatórios

- [x] Criar painel separado de restore schedule e continuous transfer lane na tela Queue.
- [x] Mostrar backlog disponível, urgência, Raiju ativos/idle e próxima decisão.
- [x] Atualizar waves timeline para intervalos de transferência descontínuos e tooltip explicável. Segmentos observados persistem entrada, saída, quantidade, bytes e expiração próxima.
- [x] Atualizar relatórios de wave com objetos transferidos em múltiplos intervalos e causas de entrada/saída da lane.
- [x] Exibir diagnóstico local de ociosidade: `BUSY`, `DISPATCH_PENDING`, `RETRY_WAIT`, `AWAITING_RESTORE`, `PLANNED_RESTORE` ou `EMPTY`, sem criar chamadas à AWS.
- [x] Atualizar estimativas com o custo observado da cópia temporária restaurada, separado da estimativa de retenção solicitada.

**Marco:** o operador compreende por que a lane está ocupada ou ociosa e quais objetos serão transferidos a seguir.

### Fase 6 — validação, simulação e regressão

- [x] Criar cenário Fujin com liberação gradual de objetos e transferência antecipada.
- [x] Criar cenário de restore lento, link oscilante e expiração para validar prioridades.
- [x] Provar que a fila não duplica objetos durante polling, retries, reinício de VM ou lease expirado.
- [x] Validar liberação imediata, esgotamento temporário e retomada automática da lane.
- [x] Validar troca entre waves sem interrupção de objeto ou parte multipart: a tarefa só mantém em lease os objetos ocupando Raijus; entradas não iniciadas retornam imediatamente a `READY`, e a próxima vaga concluída reavalia a prioridade. Não há interrupção de streaming em curso.
- [x] Validar nova aprovação após expiração sem submissão automática de restore.
- [x] Validar multipart interrompido, retries, integridade normal e auditoria profunda.
- [ ] Executar teste em AWS real controlado após aprovação, comparando previsão, disponibilidade e consumo real.
- [x] Executar suíte completa de regressão para source única, pipeline dinâmico e execução simulada; projetos multi-source permanecem fora do escopo desta versão.

**Marco:** a lane contínua é comprovadamente mais ocupada, sem reduzir rastreabilidade, integridade ou controle de custo.

## Revisão de completude — 28/08/2026

Esta revisão substitui a alegação anterior de conclusão integral. Os seguintes
itens são obrigatórios antes de marcar o plano como `OK`:

### Fase 7 — prioridade, fairness e preempção cooperativa

- [x] Persistir componentes explicáveis de prioridade: deadline, viabilidade,
  tamanho, percentual disponível, idade e prioridade de negócio.
- [x] Implementar anti-starvation verificável dentro da source por idade e
  ordenação estável; cada claim registra o evento
  `CONTINUOUS_TRANSFER_DISPATCH_DECISION`.
- [x] Implementar preempção cooperativa segura entre lotes: itens ainda não
  iniciados retornam a `READY` e um micro-lote crítico é escolhido no próximo
  claim. Objetos ou partes multipart já em streaming nunca são interrompidos,
  preservando integridade e checkpoints.
- [x] Explicitar no Queue a decisão de prioridade por banda, backlog, estado,
  idade e evento operacional; a causa por item está no relatório/timeline.

### Fase 8 — autoscaling e observabilidade operacional

- [x] Ajustar Raijus por throughput recente, backlog, limites de multipart e
  guarda conservadora de CPU/memória do host, sem cair abaixo do piso de cinco
  workers quando houver trabalho.
- [x] Expor backlog por estado, idade do item mais antigo, prioridade, prazo
  mais próximo e diagnóstico local de ociosidade. Séries históricas de
  telemetria são aprimoramento futuro, não pré-requisito da lane.
- [x] Expor a ocupação de slots de restore, backlog por estado e decisões de
  antecipação/postergação de modo consultável.

### Fase 9 — evidência por segmento e custo observado

- [x] Persistir segmentos observados de transferência por objeto/lote para a
  timeline descontínua, incluindo motivo de entrada/saída e expiração próxima.
- [x] Consolidar segmentos e esperas no relatório da wave.
- [x] Calcular custo de cópia temporária restaurada também pela permanência
  observada, mantendo a estimativa solicitada separada do custo observado.
- [x] Cobrir fila, expiração, lease, prioridade, segmentos e execução simulada
  na regressão. Casos de stress multi-source pertencem ao plano de projetos
  de migração, fora deste escopo.

## Riscos e controles

| Risco | Controle |
|---|---|
| Fome de waves grandes | Anti-starvation, prioridade por deadline e reserva por wave. |
| Objetos pequenos monopolizam a fila | Limites de lote, fairness e score ponderado por bytes/tempo. |
| Mais operações no banco | Índices por deadline/estado, inserts idempotentes e claims em lote. |
| Duplicidade após retry/restart | Constraint única, leases transacionais e checkpoints por objeto/parte. |
| Expiração durante transferência | Checagem antes de claim, deadline-aware scheduling e reaprovação explícita. |
| Polling AWS excessivo | Reutilizar apenas evidência das waves ativas e manter polling adaptativo. |
| Interface confusa | Preservar a wave como origem visível de cada objeto e explicar intervalos descontínuos na timeline. |
| Redução prematura de retenção | Validação conservadora da janela e alerta antes de submeter restore. |

## Critérios mínimos de aceite

- objetos disponíveis entram uma única vez na fila contínua;
- nenhum objeto é transferido sem evidência de restore disponível;
- os mesmos Raiju, multipart, checkpoint, retry e integridade atuais são reutilizados;
- uma wave pode restaurar e drenar objetos simultaneamente, sem transições contraditórias;
- workers permanecem ocupados quando houver objetos elegíveis, respeitando a lane única;
- a seleção é explicável por deadline, viabilidade, tamanho e fairness;
- nenhum novo restore é enviado automaticamente depois de expiração que exija aprovação;
- custo, restore, expiração, integridade e auditoria permanecem atribuíveis à wave/source original;
- polling adicional não é criado apenas para alimentar a fila;
- timeline, Queue e reports distinguem claramente previsão, restore, disponibilidade e transferência;
- a operação atual de source única continua coberta por regressão.

## Resultado esperado

Ao final, o RAIJIN não dependerá de uma wave inteira estar restaurada para aproveitar o link. O restore scheduler manterá um buffer saudável de objetos disponíveis; o transfer dispatcher selecionará continuamente o próximo objeto mais adequado; e cada wave preservará toda a sua identidade operacional, financeira e de integridade.

Isso deve reduzir lacunas de transferência, melhorar a adaptação a variações reais, permitir retenções potencialmente menores quando a previsão for segura e tornar a utilização dos recursos mais próxima do comportamento desejado para migrações de grande escala.
