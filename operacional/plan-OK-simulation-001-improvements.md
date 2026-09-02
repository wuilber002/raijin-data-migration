# Plano — melhorias identificadas em `simulation-001`

**Status:** OK — implementação concluída e revalidada
**Tempo de implementação:** 23 min e 40 s do ciclo inicial + aproximadamente 16 min desta conclusão = aproximadamente 40 min
**Referência da análise:** `simulation-001`, cenário Fujin `CONTROL`, concluído em 2026-09-01/02.

## Objetivo

Preservar as propriedades comprovadas na execução — transferência contínua, nenhuma expiração e evidência de entrega — enquanto tornamos a previsão do Fujin mais fiel, reduzimos churn operacional e calibramos o autoscaling dos Raijus.

## Linha de base observada

| Métrica | Resultado |
|---|---:|
| Objetos / dados | 100.000 / 100 TB decimais |
| Waves concluídas | 10 / 10 |
| Entregas com `OCI_ACCEPTED` | 100.000 |
| Objetos expirados ou transferidos após expiração | 0 |
| Tempo de restore, previsto / realizado | 14d 3h / 12d 17h |
| Tempo de lane, previsto / realizado | 8d 9h / 11d 20h |
| Ociosidade da lane | 21h 26m |
| Ociosidade entre restores | 1h 38m |
| Capacidade configurada / efetiva aproximada | 1.100 / 781 Mbps |
| Maior duração de restore BULK observada | 73h 42m |
| Leases recuperados / itens com segunda tentativa | 47 / 76 |
| Eventos de decisão de despacho | 99.992 |

> A fonte começou antes do congelamento da previsão de transferência. Portanto, a previsão desta execução foi recuperada da capacidade configurada, e não de um snapshot criado no primeiro restore.

## Fase 1 — tornar a previsão de restore e transferência confiável

**Marco:** o relatório final explica a diferença entre previsto e realizado sem usar premissas fixas incompatíveis com o comportamento do Fujin.

- [x] Separar no modelo Fujin os marcos `primeiro arquivo disponível` e `último arquivo disponível` de uma wave.
- [x] Substituir a janela fixa de restore por uma previsão configurável por tier, com marcos distintos de primeiro e último disponível.
- [x] Persistir, por wave, a previsão usada no instante do agendamento: primeiro disponível, último disponível e intervalo de confiança.
- [x] Fazer o Raikou usar a previsão de **último disponível** para reserva de slots e a de **primeiro disponível** para alimentar a lane.
- [x] Calibrar a taxa agregada do Fujin: o resultado separa capacidade configurada, taxa efetiva, utilização e overhead por suprimento de restore, despacho/lease, worker, throttle/retry e capacidade.
- [x] Congelar, no primeiro restore, as premissas de previsão da source: link, perfil de restore, limite de workers e versão do scheduler.
- [x] Exibir no resultado final se a estimativa foi congelada ou recuperada por compatibilidade histórica.

**Critérios de aceite**

- [x] Nenhuma previsão apresenta BULK como limite rígido de 48h quando o cenário permite disponibilização total posterior.
- [x] O relatório final informa a diferença de restore/transferência, capacidade congelada, taxa efetiva, utilização e atribuição de overhead.
- [x] Os contratos automatizados exercitam previsões, janelas de calendário e a tolerância numérica do perfil Fujin.

## Fase 2 — reduzir lacunas da lane sem antecipar risco de expiração

**Marco:** o Raikou mantém backlog restaurado suficiente para a lane, sem restaurar além da capacidade útil e sem aumentar risco de expiração.

- [x] Medir ociosidade por causa: restore, despacho/lease, worker indisponível, throttle/retry e limite de capacidade usam o mesmo relógio da lane.
- [x] Registrar a fronteira entre a espera inicial e lacunas operacionais posteriores.
- [x] Ajustar o horizonte de restore e a quantidade de slots a partir do backlog, taxa e retenção.
- [x] Antecipar restores quando o buffer da lane ficar abaixo do mínimo/objetivo seguro.
- [x] Garantir que uma wave libere slot de restore ao atingir 100% disponível, mesmo que seus arquivos ainda estejam na lane.
- [x] Manter bloqueio para waves com falha/reaprovação até decisão explícita; elas não consomem slot indefinidamente.

**Critérios de aceite**

- [x] A explicação da ociosidade aparece na API, no relatório final e na timeline, com cada causa identificada.
- [x] A lane não mantém objetos `READY` sem despacho por causa de lote mínimo.
- [x] Nenhum objeto restaurado expira durante a execução simulada exercitada pelos testes.
- [x] A métrica de ociosidade potencialmente evitável é separada e percentual, permitindo comparar diretamente execuções CONTROL contra a linha de base.

## Fase 3 — autoscaling Raiju baseado em ganho real de capacidade

**Marco:** a quantidade de Raijus cresce apenas enquanto aumenta a vazão agregada útil e reduz quando não há trabalho suficiente.

- [x] Registrar decisões por lote com alvo de workers, curva temporal, taxa da lane, taxa por Raiju e pressão de host por ciclo.
- [x] Definir histerese para scale-up e scale-down, evitando oscilações a cada ciclo.
- [x] Basear o scale-up na taxa observada robusta por Raiju, no limite agregado de link e no limiar configurável de ganho marginal agregado.
- [x] Diminuir slots gradualmente quando o backlog não justificar capacidade, nunca abaixo do mínimo global de 5.
- [x] Distinguir slots lógicos e cópias de fato ativas na interface.
- [x] Consolidar bloqueios recorrentes do host guard em vez de gerar um alerta por heartbeat.

**Critérios de aceite**

- [x] O relatório mostra pico, média e curva temporal dos workers, incluindo pressão de host e razão da decisão.
- [x] A decisão de slots é limitada por link/host/backlog, reduz em passos e só mantém scale-up quando o ganho marginal atinge o limiar configurado.
- [x] O host guard não gera alertas repetidos para a mesma condição estável.

## Fase 4 — durabilidade de leases e telemetria proporcional

**Marco:** retries são rastreáveis, mas decisões normais não produzem um evento por objeto.

- [x] Expor no resultado os itens com retry, recuperações agregadas de lease, segmentos vazios e payload repetido; a instrumentação permite atribuição por execução.
- [x] Diferenciar segmento de cópia (bytes) de segmento vazio/reconciliação na telemetria.
- [x] Consolidar decisões normais de despacho por intervalo/lote; preservar evidência individual para anomalias relevantes.
- [x] Consolidar reconciliações repetidas de leases já entregues em um evento com intervalo.
- [x] Criar métricas de retry, recuperação e segmentos vazios; bytes efetivos permanecem separados de recuperação.
- [x] Manter a idempotência de destino e os testes de recovery, incluindo retry explícito que confirma `payload repetido = 0`.

**Critérios de aceite**

- [x] Uma source não gera um evento de despacho normal por objeto; o evento é limitado por intervalo.
- [x] Segmentos sem bytes são telemetria de recuperação e não entram na taxa efetiva nem no tempo da lane.
- [x] A suíte exerce transferência simulada, recovery, integridade e retry explícito com as métricas finais de bytes repetidos.

## Fase 5 — fechamento verificável da source

**Marco:** `Resultado final` distingue entrega aceita de destino totalmente reconciliado.

- [x] Tornar a validação do destino OCI uma etapa explícita de fechamento quando aplicável.
- [x] Exibir no modal: `entrega aceita`, `validação de destino`, `auditoria profunda` e respectivos dados.
- [x] Permitir resultado final parcial apenas como leitura, identificado como “aguardando validação de destino”.
- [x] Adicionar resumo de divergências: ausentes, tamanho, metadados/proveniência e objetos extras.
- [x] Manter a validação idempotente e sem retransferir objetos.

**Critérios de aceite**

- [x] Uma source só recebe selo de “destino reconciliado” após a comparação OCI correspondente.
- [x] O operador entende claramente a diferença entre `OCI_ACCEPTED` e validação completa do bucket.

## Sequência recomendada

1. Fase 1 — corrige a qualidade das decisões e das expectativas.
2. Fase 4 — reduz ruído e torna as próximas medições confiáveis.
3. Fase 2 — usa essas medições para reduzir ociosidade.
4. Fase 3 — calibra custo e capacidade dos Raijus.
5. Fase 5 — fecha a evidência operacional e de destino.

## Registro de conclusão

| Fase | Concluída em | Evidência / commit | Observações |
|---|---|---|---|
| 1 — Previsões | 2026-09-02 | implementação atual | Perfil Fujin, snapshot, tolerância e atribuição de overhead concluídos. |
| 2 — Ociosidade | 2026-09-02 | implementação atual | Gaps por causa, timeline e métrica comparável concluídos. |
| 3 — Autoscaling | 2026-09-02 | implementação atual | P75, histerese, host guard, curva e ganho marginal configurável concluídos. |
| 4 — Leases e telemetria | 2026-09-02 | implementação atual | Eventos agregados, métricas e retry sem payload repetido concluídos. |
| 5 — Fechamento | 2026-09-02 | `8f2798c` | Entrega, reconciliação real/Fujin e selo explícito comprovados. |

## Auditoria final de implementação — 2026-09-02

Revalidação integral concluída: 235 testes passaram, incluindo fluxo fim a fim no modo Simulation. Esta conclusão acrescentou a instrumentação por decisão do Raikou, a trava de ganho marginal configurável, a curva compactada de autoscaling, a atribuição de ociosidade/overhead, o detalhamento na timeline e os contratos explícitos de tolerância Fujin e retry sem payload repetido. Não permanecem itens parciais neste plano.
