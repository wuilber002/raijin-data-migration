# OK — Plano de evolução: scheduler adaptativo de pipeline

## Registro de implementação

- **Tempo total de implementação:** a telemetria de tempo ativo não era registrada nesta fase; portanto não há duração efetiva recuperável sem estimativa artificial.
- **Janela registrada de implementação:** 23/08/2026 a 27/08/2026, conforme os commits de evolução do pipeline.
- **Observação:** o modelo por wave foi posteriormente evoluído pela fila contínua de transferência. Este plano permanece como histórico das decisões que introduziram o scheduler adaptativo.

## 1. Objetivo

Evoluir o agendador de *waves* do Raijin para manter a faixa única de
transferência ocupada pelo maior tempo possível, sem ampliar custos de
restauração de forma imprudente nem permitir que cópias temporárias expirem
antes de serem copiadas.

O modelo mantém uma transferência simultânea por vez. Restaurações são uma
capacidade independente: começam com dois slots concorrentes e podem ser
expandidas pelo próprio scheduler somente quando dados observados demonstrarem
benefício e segurança operacional.

## 2. Princípios de decisão

- Priorizar continuidade da transferência, não apenas ordem numérica das
  *waves*.
- Planejar restores de trás para frente a partir do próximo início previsto de
  transferência.
- Tratar *waves* ainda não submetidas como replanejáveis; uma submissão aceita
  pela AWS é custo potencial já assumido e não é desfeita automaticamente.
- Usar volume restaurado em bytes — nunca apenas quantidade de objetos — para
  liberar transferência antecipada.
- Manter 15% como limiar inicial configurável por *source* para a estratégia
  **Release files as they become available**.
- A transferência parcial deve ser liberada somente se, além do limiar por
  bytes, houver previsão de alimentação contínua dos workers por uma janela
  mínima. O limiar evita iniciar com volume irrelevante; a previsão evita
  ocupar a faixa única de transferência e voltar a deixá-la ociosa.
- Aplicar margem operacional dentro da janela de retenção; ela representa risco
  calculado, não tempo extra acrescentado ao limite rígido do restore.
- Preservar explicabilidade: toda decisão automática deve ter evidência,
  previsão, motivo e alternativa registrada no histórico operacional.

## 3. Acompanhamento de implementação

Atualizar este quadro somente depois de validar os critérios de aceite da fase.
O marcador `[x]` representa fase concluída; `[~]`, fase em implementação; e
`[ ]`, fase ainda não iniciada.

| Estado | Fase | Marco | Data de conclusão | Evidência / versão |
| --- | --- | --- | --- | --- |
| [x] | 0 — Linha de base e instrumentação | Observabilidade confiável | 27/08/2026 | Eventos de atribuição da faixa registram bytes, percentual, reserva e objetos pendentes. |
| [x] | 1 — Modelo de previsão por perfil | Previsões explicáveis | 27/08/2026 | Previsão por objeto usa histórico por perfil e *fallback* conservador de link. |
| [x] | 2 — Composição adaptativa de waves | Waves viáveis por retenção | 27/08/2026 | Waves futuras são reempacotadas somente antes da submissão AWS. |
| [x] | 3 — Pipeline inicial e restore em paralelo | Pipeline aquecido | 27/08/2026 | Horizonte inicial de três: dois restores e uma wave futura replanejável. |
| [x] | 4 — Replanejamento contínuo | Replanejamento preventivo | 27/08/2026 | Replaneja tamanho e horários de waves ainda não submetidas após novas evidências. |
| [x] | 5 — Escalonamento adaptativo de restore | Escala baseada em evidência | 27/08/2026 | Baseline de dois slots; escala com histórico até o teto global configurável de quatro. |
| [x] | 6 — Simulação, testes e homologação | Pronto para teste real ampliado | 27/08/2026 | 211 testes automatizados aprovados, incluindo fluxo Fujin/worker real. |

## 4. Indicadores de sucesso

| Indicador | Definição | Meta inicial |
| --- | --- | --- |
| Ocupação da transferência | Tempo com transferência ativa / duração do pipeline | Medir por source; aumentar a cada ciclo sem comprometer retenção |
| Lacuna ociosa | Período em que não há transferência elegível por restore tardio | Identificar causa e reduzir progressivamente |
| Antecedência de restore | Tempo entre submissão e início efetivo da transferência | Manter suficiente para o tier observado, sem excesso de retenção |
| Risco de expiração | Waves restauradas cuja cópia pode expirar antes da posição de transferência | Zero em operação normal |
| Acurácia da previsão | Diferença entre duração prevista e observada | Acompanhar p50, p75 e p90 por perfil |
| Custo evitável | Restaurações repetidas ou cópias temporárias expiradas sem cópia | Zero em operação normal |

## 5. Fase 0 — Linha de base e instrumentação

**Status:** `[x] Concluída`  
**Conclusão validada em:** 27/08/2026  
**Evidência / versão:** eventos `TRANSFER_LANE_ASSIGNED` e contratos automatizados.

### Escopo

- Consolidar eventos de restore, primeira disponibilidade, disponibilidade
  completa, início/fim de transferência, throughput e expiração.
- Registrar, por wave e por objeto quando aplicável, previsões usadas pelo
  scheduler e valores observados.
- Classificar lacunas: restore tardio, indisponibilidade parcial, falta de
  workers, limite de transferência, pausa operacional, falha/retry ou decisão
  de retenção.
- Expor no relatório e na linha do tempo: início previsto/observado, duração
  prevista/observada, margem operacional e motivo de qualquer replanejamento.

### Marco 0 — Observabilidade confiável

Concluído quando uma execução permite explicar, sem inferência manual, por que
cada intervalo sem transferência ocorreu e qual previsão o scheduler utilizou.

### Critérios de aceite

- Nenhuma decisão de pipeline relevante fica sem evento auditável.
- Linha do tempo mostra restore, espera de disponibilidade, margem e
  transferência sem sobreposição inconsistente.
- Métricas de simulação CONTROL nunca ultrapassam a capacidade de link
  configurada.

## 6. Fase 1 — Modelo de previsão por perfil

**Status:** `[x] Concluída`  
**Conclusão validada em:** 27/08/2026  
**Evidência / versão:** previsão por objeto, perfis de histórico e *fallback* de link cobertos por teste.

### Escopo

- Criar perfis estatísticos por source, região, tier, classe de armazenamento e
  faixa de tamanho/quantidade de objetos.
- Calcular duração de cópia por objeto com tamanho, custo fixo por objeto,
  multipart, workers efetivos e throughput observado.
- Manter previsões de restore p50, p75 e p90; usar p75 inicialmente para
  planejamento e p90 para alertas de risco.
- Aplicar decaimento de histórico para que medições recentes tenham maior peso.
- Definir fallback explícito quando não houver histórico suficiente.

### Marco 1 — Previsões explicáveis

Concluído quando cada wave criada apresenta a previsão de restore e
transferência, a confiança do modelo e os dados que a compõem.

### Critérios de aceite

- Previsões não usam média simples como única referência.
- Uma source nova usa fallback documentado; uma source com histórico passa a
  usar dados observados.
- A diferença previsto × observado alimenta o perfil seguinte automaticamente.

## 7. Fase 2 — Composição adaptativa de waves

**Status:** `[x] Concluída`  
**Conclusão validada em:** 27/08/2026  
**Evidência / versão:** `repackage_unsubmitted_dynamic_waves` preserva waves já submetidas.

### Escopo

- Gerar waves por duração viável dentro da janela de retenção, e não por um
  tamanho fixo escolhido manualmente.
- Dimensionar cada wave pela soma das previsões dos objetos, respeitando
  retenção menos margem operacional.
- Usar limite máximo de dados e de objetos apenas como guardrails de segurança,
  não como alvo primário.
- Revisar somente objetos ainda não atribuídos e waves planejadas, preservando
  waves já submetidas.

### Marco 2 — Waves viáveis por retenção

Concluído quando nenhuma wave dinâmica é criada se sua previsão conservadora de
cópia não couber na janela útil de retenção.

### Critérios de aceite

- Exibir, antes da criação, janela útil, margem, duração estimada e tamanho
  resultante da wave.
- Registrar o motivo de corte da wave: retenção, bytes, objetos ou confiança
  insuficiente.
- Permitir que o tamanho de waves varie naturalmente entre execuções.

## 8. Fase 3 — Pipeline inicial e restore em paralelo

**Status:** `[x] Concluída`  
**Conclusão validada em:** 27/08/2026  
**Evidência / versão:** horizonte de três, dois slots de restore e faixa de cópia exclusiva.

### Escopo

- Manter horizonte inicial de três waves: duas elegíveis para restore e uma
  futura, replanejável e sem custo AWS.
- Usar dois slots de restore como capacidade padrão.
- Liberar um slot assim que todos os objetos da wave estejam disponíveis; a
  faixa de transferência permanece exclusiva.
- Implementar seletor de próxima transferência por elegibilidade, previsão de
  expiração e continuidade do link — não exclusivamente por sequência.
- Aplicar transferência antecipada somente quando a estratégia da source
  permitir e bytes disponíveis atingirem o limiar configurado, inicialmente
  15%.

### Marco 3 — Pipeline aquecido

Concluído quando, em cenário estável, uma wave em transferência coexistir com
até duas waves em restauração/aguardo, sem criar restores ilimitados.

### Critérios de aceite

- Uma única wave transfere por vez.
- No máximo dois restores simultâneos no período inicial.
- Waves futuras não têm Batch Job nem custo até se tornarem elegíveis.
- O relatório evidencia a decisão de antecipar ou aguardar transferência.

## 9. Fase 4 — Replanejamento contínuo

**Status:** `[x] Concluída`  
**Conclusão validada em:** 27/08/2026  
**Evidência / versão:** `replan_dynamic_pipeline` recalcula somente as waves mutáveis.

### Escopo

- Recalcular o plano ao ocorrer: primeira disponibilidade, disponibilidade
  completa, início/fim de transferência, variação de throughput, retry, pausa,
  falha ou risco de expiração.
- Reposicionar apenas waves não submetidas; reordenar transferência entre waves
  restauradas quando isso reduzir lacuna ou risco de expiração.
- Identificar lacuna futura antes de ela ocorrer e antecipar o restore seguinte
  se houver slot e segurança de retenção.
- Registrar cada mudança como decisão do scheduler com comparação antes/depois.

### Marco 4 — Replanejamento preventivo

Concluído quando o scheduler detecta uma lacuna prevista e toma decisão antes do
fim da transferência corrente, em vez de reagir quando o link já está ocioso.

### Critérios de aceite

- Mudanças de plano não afetam Batch Jobs já aceitos sem ação explícita.
- Nenhuma wave restaurada é deixada expirar por fila planejada incorretamente.
- A linha do tempo distingue plano original, plano revisado e observado.

## 10. Fase 5 — Escalonamento adaptativo de restore

**Status:** `[x] Concluída`  
**Conclusão validada em:** 27/08/2026  
**Evidência / versão:** teto ajustável de 2 a 4 e decisão por p75 de restores observados.

### Escopo

- Manter dois slots como padrão frio.
- Após histórico mínimo de três waves concluídas, estimar se slots adicionais
  reduzem lacunas sem aumentar o risco de retenção ou custo desnecessário.
- Escalar gradualmente, com teto inicial conservador de quatro slots e possibilidade
  de redução automática quando a pressão de retenção aumentar.
- Reverter para dois slots na ausência de evidência, em degradação de link ou
  quando o modelo perder confiança.

### Marco 5 — Escala baseada em evidência

Concluído quando o número de restores concorrentes é uma decisão justificada por
dados observados, não um valor fixo global.

### Critérios de aceite

- Cada ajuste informa capacidade anterior, nova capacidade, evidência e duração
  esperada.
- Escalar nunca cria restore que não tenha posição segura de transferência.
- Um cenário de pior caso mostra redução automática antes de expirações.

## 11. Fase 6 — Simulação, testes e homologação

**Status:** `[x] Concluída`  
**Conclusão validada em:** 27/08/2026  
**Evidência / versão:** suíte completa: 211 testes aprovados em 27/08/2026.

### Escopo

- Criar cenários Fujin para restore rápido/lento, disponibilidade parcial,
  throughput degradado, oscilação de link, objetos pequenos numerosos, objetos
  grandes multipart, falhas e retenção curta.
- Validar o mesmo comportamento do scheduler nos modos de simulação CONTROL e
  DATA, respeitando suas diferenças de fidelidade.
- Executar testes de regressão sobre prioridade, slots, limiar de 15%,
  replanejamento, expiração e idempotência.
- Comparar ocupação do link, lacunas e custo potencial antes/depois em execução
  controlada.

### Marco 6 — Pronto para teste real ampliado

Concluído quando os cenários críticos não produzem expiração artificial, restores
duplicados, sobreposição de transferência nem telemetria acima do link.

### Critérios de aceite

- Testes automatizados cobrem cada decisão de scheduler.
- Linha do tempo e relatório permitem reproduzir uma decisão.
- A execução simulada demonstra melhoria mensurável de ocupação sem aumento de
  restaurações repetidas.

## 12. Ordem recomendada de implementação

1. Fase 0 — corrigir e consolidar observabilidade.
2. Fase 1 — previsões por perfil e confiança.
3. Fase 3 — estabilizar horizonte de três waves e dois slots.
4. Fase 4 — replanejamento preventivo.
5. Fase 2 — composição de waves guiada pela janela útil, usando o modelo já
   validado.
6. Fase 5 — escalonamento adaptativo somente após dados suficientes.
7. Fase 6 — regressão contínua no Fujin e teste real controlado.

## 13. Decisões já consolidadas

- Uma transferência por vez.
- Dois restores simultâneos como ponto de partida.
- Escalonamento de restores somente por decisão do scheduler baseada em dados.
- Teto global configurável de quatro restores simultâneos; na ausência de
  histórico confiável, o scheduler retorna ao padrão de dois slots.
- Horizonte inicial de três waves dinâmicas.
- Transferência antecipada por bytes restaurados, com limiar de 15% configurável
  por source e validação de continuidade prevista da oferta de arquivos.
- Uma source é a unidade operacional ativa inicial. Não haverá arbitragem entre
  sources nesta etapa; suporte concorrente entre sources será evolução futura.
- Reprocessamento de restore que possa gerar custo exige aprovação explícita do
  operador.
- Margem operacional é parte da janela de retenção, não extensão do prazo AWS.
