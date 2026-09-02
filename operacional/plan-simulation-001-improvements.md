# Plano — melhorias identificadas em `simulation-001`

**Status:** planejado  
**Tempo de implementação:** — (ainda não iniciado)  
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

- [ ] Separar no modelo Fujin os marcos `primeiro arquivo disponível` e `último arquivo disponível` de uma wave.
- [ ] Substituir a janela fixa de restore (`48h` BULK / `12h` STANDARD) por uma previsão com distribuição configurável por cenário, tier, tamanho da wave e número de objetos.
- [ ] Persistir, por wave, a previsão usada no instante do agendamento: primeiro disponível, último disponível e intervalo de confiança.
- [ ] Fazer o Raikou usar a previsão de **último disponível** para reserva de slots e a de **primeiro disponível** para alimentar a lane.
- [ ] Calibrar a taxa agregada do Fujin: capacidade configurada, overhead modelado e taxa efetiva devem aparecer separadamente.
- [ ] Congelar, no primeiro restore, todas as premissas de previsão da source: link, perfil Fujin, distribuição de restore, limite de workers e versão do scheduler.
- [ ] Exibir no resultado final se a estimativa foi congelada ou recuperada por compatibilidade histórica.

**Critérios de aceite**

- [ ] Nenhuma previsão apresenta BULK como limite rígido de 48h quando o cenário permite disponibilização total posterior.
- [ ] O relatório final informa a razão da diferença: restore, disponibilidade da lane, overhead de transferência ou mudança de configuração.
- [ ] Em cenários de teste, o erro absoluto da previsão de transferência fica dentro da tolerância definida para o perfil Fujin.

## Fase 2 — reduzir lacunas da lane sem antecipar risco de expiração

**Marco:** o Raikou mantém backlog restaurado suficiente para a lane, sem restaurar além da capacidade útil e sem aumentar risco de expiração.

- [ ] Medir ociosidade por causa: falta de arquivos restaurados, worker indisponível, lease em recuperação, throttle simulado ou limite de capacidade.
- [ ] Registrar a fronteira entre a ociosidade inicial inevitável (primeiro restore) e lacunas evitáveis durante a execução.
- [ ] Ajustar o horizonte de restore e a quantidade de slots a partir do backlog em segundos, da taxa efetiva e do prazo de expiração mais próximo.
- [ ] Avaliar antecipação de restore quando a previsão indicar que a lane ficará sem trabalho antes do próximo primeiro disponível.
- [ ] Garantir que uma wave libere slot de restore ao atingir 100% disponível, mesmo que seus arquivos ainda estejam na lane.
- [ ] Manter bloqueio para waves com falha/reaprovação até decisão explícita; elas não devem consumir slot indefinidamente.

**Critérios de aceite**

- [ ] A explicação da ociosidade aparece na API, timeline e relatório final.
- [ ] A lane não mantém objetos `READY` sem despacho por causa de lote mínimo.
- [ ] Nenhum objeto restaurado expira durante a execução.
- [ ] A métrica de ociosidade evitável diminui em relação aos 21h 26m da linha de base, sem elevar restores desnecessários.

## Fase 3 — autoscaling Raiju baseado em ganho real de capacidade

**Marco:** a quantidade de Raijus cresce apenas enquanto aumenta a vazão agregada útil e reduz quando não há trabalho suficiente.

- [ ] Registrar por ciclo: workers ativos, capacidade configurada, taxa agregada, backlog em bytes/segundos e pressão do host.
- [ ] Definir histerese para scale-up e scale-down, evitando oscilações a cada ciclo.
- [ ] Limitar scale-up pela taxa agregada medida: novos Raijus só são mantidos se aumentarem a taxa dentro de uma margem mínima configurável.
- [ ] Diminuir slots gradualmente quando backlog, taxa ou disponibilidade de objetos não justificarem a capacidade atual, nunca abaixo do mínimo global de 5.
- [ ] Distinguir slots lógicos da lane de processos/threads efetivamente ativos para que a interface não sugira recursos inexistentes.
- [ ] Revisar os eventos `RAIJU_AUTOSCALE_HOST_GUARD` e transformar bloqueios recorrentes em uma razão operacional agregada.

**Critérios de aceite**

- [ ] O relatório mostra pico, média e curva de workers ativos, não somente o máximo configurado.
- [ ] A execução não permanece em 64 slots quando a taxa agregada já está saturada ou o backlog é pequeno.
- [ ] O host guard não gera alertas repetidos para a mesma condição estável.

## Fase 4 — durabilidade de leases e telemetria proporcional

**Marco:** retries são rastreáveis, mas decisões normais não produzem um evento por objeto.

- [ ] Investigar a origem dos 47 leases recuperados e dos 76 itens com segunda tentativa no cenário CONTROL.
- [ ] Diferenciar no banco: segmento de cópia efetiva, segmento vazio de recuperação e simples mudança de lease.
- [ ] Registrar decisões normais de despacho como contadores por ciclo/lote/wave; preservar evento individual para falha, retry, preempção, expiração e recuperação relevante.
- [ ] Consolidar reconciliações repetidas de leases já entregues em um único evento com quantidade e intervalo.
- [ ] Criar métricas: taxa de recuperação de lease, tentativas por objeto, segmentos vazios e bytes repetidos.
- [ ] Manter prova de que retries não duplicam bytes nem criam segundo objeto no OCI.

**Critérios de aceite**

- [ ] Uma source de 100.000 objetos não gera aproximadamente 100.000 eventos de despacho normal.
- [ ] Todo segmento extra informa seu motivo; segmentos sem bytes não contam como transferência na UI nem na taxa efetiva.
- [ ] Testes simulam reinício, lease expirado e recovery sem duplicar bytes nem violar expiração.

## Fase 5 — fechamento verificável da source

**Marco:** `Resultado final` distingue entrega aceita de destino totalmente reconciliado.

- [ ] Tornar a validação do destino OCI uma etapa explícita de fechamento para fontes reais e simuladas quando aplicável.
- [ ] Exibir no modal: `entrega aceita`, `validação de destino`, `auditoria profunda` e respectivos timestamps.
- [ ] Permitir resultado final parcial apenas como leitura, identificado como “aguardando validação de destino”.
- [ ] Adicionar resumo de divergências: ausentes, tamanho, metadados/proveniência e objetos extras.
- [ ] Manter a validação idempotente e sem retransferir objetos.

**Critérios de aceite**

- [ ] Uma source só recebe selo de “destino reconciliado” após a comparação OCI correspondente.
- [ ] O operador entende claramente a diferença entre `OCI_ACCEPTED` e validação completa do bucket.

## Sequência recomendada

1. Fase 1 — corrige a qualidade das decisões e das expectativas.
2. Fase 4 — reduz ruído e torna as próximas medições confiáveis.
3. Fase 2 — usa essas medições para reduzir ociosidade.
4. Fase 3 — calibra custo e capacidade dos Raijus.
5. Fase 5 — fecha a evidência operacional e de destino.

## Registro de conclusão

| Fase | Concluída em | Evidência / commit | Observações |
|---|---|---|---|
| 1 — Previsões | — | — | — |
| 2 — Ociosidade | — | — | — |
| 3 — Autoscaling | — | — | — |
| 4 — Leases e telemetria | — | — | — |
| 5 — Fechamento | — | — | — |
