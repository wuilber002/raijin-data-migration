# Plano de projetos de migração multi-source

## Registro de implementação

- **Tempo total de implementação:** não iniciado.
- **Observação:** a fila contínua atual permanece delimitada por source. A evolução para projeto multi-source será feita sem fundir manifests, restores ou evidências entre buckets.

## Objetivo

Evoluir o RAIJIN para que o operador administre um **projeto de migração** como escopo principal, contendo várias sources independentes. Cada source continuará delimitada por uma conexão AWS, um bucket S3, uma região, prefixes não sobrepostos e um destino OCI seguro. O projeto consolidará visibilidade, planejamento, custos, falhas e conclusão, sem eliminar as evidências operacionais por bucket.

O objetivo não é fundir artificialmente buckets em uma única source ou em um único job de restore. O objetivo é coordenar vários escopos técnicos sob uma única operação de migração.

## Status do plano

**PLANEJADO — sem implementação iniciada.**

Este documento é a referência para a evolução. Cada item concluído deve ser marcado com `[x]`; decisões que substituírem alguma premissa devem ser registradas na seção de decisões e refletidas nos critérios de aceite.

## Modelo de domínio proposto

```text
Projeto de migração
├── Source A: conexão AWS + bucket A + região A + prefixes
├── Source B: conexão AWS + bucket B + região A + prefixes
└── Source C: conexão AWS + bucket C + região B + prefixes
```

| Entidade | Papel |
|---|---|
| **Projeto de migração** | Agrega escopo, fontes, destino lógico, política operacional, timeline, custo, saúde e conclusão. |
| **Source** | Unidade operacional de um bucket em uma região: discovery, inventário, waves, manifests, restore, transferência, auditoria e arquivamento. |
| **Wave** | Unidade executável pertencente a uma única source. Mantém seleção de objetos, manifesto, restore, retenção, checkpoints, custos e evidências. |
| **Wave agrupada** | Visão lógica opcional do projeto que reúne waves de sources pequenas, sem transformar seus manifests, jobs ou evidências em um único registro físico. |
| **Segmento da wave agrupada** | Referência a uma wave real, por source/bucket, usada para composição da visão consolidada. |

## Decisões consolidadas

### Preservar source como unidade técnica

Uma source não terá múltiplos buckets. Esse limite preserva:

- um inventário e re-discovery consistentes;
- uma região AWS inequívoca;
- uma política de IAM e um conjunto de evidências rastreáveis;
- um manifesto e job de restore com escopo claro;
- reprocessamento, expiração, custo e aprovação de novo restore isoláveis;
- prevenção de colisões de chaves no destino OCI.

O Amazon S3 Batch Operations executa uma operação por job e uma task por objeto do manifesto. Para listas customizadas, a documentação trata o escopo como objetos de um único bucket; por isso o RAIJIN continuará produzindo manifestos e jobs por source/bucket. Consulte a documentação oficial: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops.html>.

### Projeto pode conter múltiplas regiões

Um projeto poderá agrupar buckets de várias regiões AWS. A região será propriedade da source, nunca apenas do projeto ou da conexão. Cada pipeline regional manterá seus próprios jobs de restore, polling e control bucket/manifests adequados à região.

Não haverá job de Batch Operations nem wave física que misture objetos de regiões distintas. A AWS não suporta geração de object list entre regiões para Batch Operations: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops-create-job.html>.

### Uma conexão AWS pode ser reutilizada

Uma conexão poderá atender várias sources e projetos quando as credenciais, roles e permissões tiverem acesso aos respectivos buckets. O cadastro da source continuará validar bucket e região contra a conexão antes de permitir discovery ou restore.

### Destino OCI e prevenção de colisões

Cada source deverá possuir um prefixo de destino OCI obrigatório e imutável após a primeira wave entrar em processamento. A convenção recomendada será:

```text
<prefixo-do-projeto>/<identificador-da-source>/<bucket-s3>/<chave-original>
```

O RAIJIN preservará também metadata de proveniência (`source bucket`, chave, versão quando aplicável, ETag e timestamps). Dois buckets com a mesma chave nunca poderão sobrescrever o mesmo objeto de destino.

### Agrupamento de buckets pequenos

O agrupamento será implementado somente como planejamento e visualização de projeto:

- o scheduler pode selecionar waves de sources pequenas para ocupar a janela de transferência;
- cada source continuará com sua wave, manifesto, job Batch, custo e aprovação próprios;
- a interface poderá exibir uma **wave agrupada** com seus segmentos e andamento consolidado;
- falhar, pausar ou reprocessar um segmento não invalidará automaticamente os demais.

Não será criado um único manifesto multi-bucket nem um único job de restore compartilhado.

### Scheduler

O projeto terá uma fila de decisão global. O scheduler respeitará as regras já estabelecidas:

- uma única lane de transferência ativa na primeira versão;
- slots de restore configurados globalmente e administrados pelo scheduler;
- prioridade baseada em expiração, disponibilidade, janela operacional, custo de oportunidade e previsão observada;
- preferência por waves pequenas elegíveis quando ajudarem a evitar ociosidade da transferência;
- restore, polling e transferência continuam auditáveis por source.

Pipelines de regiões diferentes competem por recursos globais apenas quando a política do projeto o permitir. A primeira implementação manterá a lane única de transferência, mesmo quando houver várias regiões.

### Estados de projeto

Estados propostos:

- `CONFIGURED`: projeto criado, sem source pronta para execução;
- `DISCOVERING`: ao menos uma source em discovery;
- `READY`: todas as sources selecionadas possuem inventário e não há waves ativas;
- `RUNNING`: há restore, transferência, polling ou auditoria ativa;
- `PAUSED`: o operador pausou o projeto e não há claims novos;
- `COMPLETED`: todas as sources foram concluídas e validadas conforme a política;
- `COMPLETED_WITH_ATTENTION`: processamento terminou, mas existem divergências, pendências de auditoria ou failures não resolvidas;
- `FAILED`: não há progresso possível sem intervenção;
- `ARCHIVED`: projeto preservado apenas para consulta.

Os estados de source e wave não serão substituídos por esses estados agregados.

## Experiência do operador

### Fluxo de criação

1. Criar o projeto: nome, destino lógico OCI, política de custo e parâmetros globais.
2. Adicionar uma ou mais sources: conexão AWS, bucket, região, prefixes e prefixo OCI de destino.
3. Executar discovery de cada source por API ou arquivo de inventário.
4. Revisar inventários e conflitos de destino.
5. Criar pipeline do projeto.
6. Iniciar ou pausar o projeto como operação consolidada.

### Visão do projeto

O projeto exibirá, por source:

| Source | Região | Objetos | Tamanho | Estado | Próxima ação |
|---|---|---:|---:|---|---|
| Bucket A | us-east-1 | 1.200.000 | 12 TB | TRANSFERRING | Wave 08 em cópia |
| Bucket B | us-east-1 | 80.000 | 600 GB | RESTORING | Wave 03 aguardando restore |
| Bucket C | sa-east-1 | 430.000 | 4 TB | DISCOVERED | Aguardando planejamento |

Também serão apresentados:

- totais consolidados de objetos, bytes, transferidos, validados, falhos e pendentes;
- custo estimado por source, região e projeto;
- timeline global e filtro por source/região;
- fila consolidada de restores e transferência;
- alertas que identifiquem explicitamente source, bucket, região e wave;
- conclusão e pendências por source.

### Operação detalhada

O operador continuará podendo abrir uma source para executar ações locais: re-discovery, ver inventory, validar OCI, aprovar restore, pausar, reprocessar, auditar ou arquivar. Ações globais nunca ocultarão o resultado individual de cada bucket.

## Plano de implementação

### Fase 0 — contratos e migrations

- [ ] Criar a entidade `migration_projects` com identificador imutável, nome, estado, política e timestamps.
- [ ] Associar `sources` a um projeto por migration explícita.
- [ ] Criar `source_destination_prefix` obrigatório para sources novas.
- [ ] Criar constraints para unicidade de prefixo de destino dentro do projeto.
- [ ] Criar entidades de referência para `project_wave_groups` e seus segmentos, sem alterar a ownership de waves existentes.
- [ ] Atualizar contratos de API, eventos e auditoria para sempre carregar `project_id` quando houver projeto.
- [ ] Definir migration e limpeza para dados de teste descartáveis, conforme a diretriz de homologação vigente.

**Marco:** schema e contratos suportam projeto sem alterar o fluxo de uma source existente.

### Fase 1 — cadastro e validações de sources

- [ ] Criar tela e APIs para criar, editar e arquivar projeto.
- [ ] Permitir adicionar source a um projeto existente ou criar projeto durante o cadastro da primeira source.
- [ ] Validar conexão AWS, bucket, região e prefixes por source.
- [ ] Tornar obrigatório o prefixo OCI de destino e mostrar o mapeamento completo de chaves.
- [ ] Impedir colisões entre prefixes de destino de sources do mesmo projeto.
- [ ] Manter a proteção atual contra sobreposição de prefixes dentro do mesmo bucket e entre sources equivalentes.
- [ ] Exibir aviso claro para buckets de regiões diferentes, explicando que o processamento será segmentado regionalmente.

**Marco:** um operador consegue cadastrar um projeto com várias sources independentes sem risco de colisão no destino.

### Fase 2 — discovery e inventário consolidados

- [ ] Mostrar discovery por source e progresso agregado do projeto.
- [ ] Consolidar contadores de objetos, tamanho, storage class e duração de discovery.
- [ ] Implementar export consolidado do projeto com `project`, `source`, `bucket`, `region`, `prefix` e chave original.
- [ ] Garantir re-discovery incremental isolado por source, incluindo objetos novos e modificados.
- [ ] Manter marca de proveniência do discovery por API ou arquivo de inventory em cada source.
- [ ] Incluir validações automáticas de duplicidade de chave lógica no destino antes da criação de waves.

**Marco:** inventários de múltiplos buckets são visíveis como um projeto, mas permanecem distinguíveis e reprocessáveis isoladamente.

### Fase 3 — scheduler orientado a projeto

- [ ] Introduzir uma fila de decisão por projeto, sem remover filas de source/wave.
- [ ] Avaliar elegibilidade por source: restore slots, região, expiração, disponibilidade e reserva operacional.
- [ ] Manter uma lane de transferência global por projeto na primeira versão.
- [ ] Permitir restores concorrentes de sources diferentes até o limite global administrado pelo scheduler.
- [ ] Escolher a próxima transferência pela política já usada: elegibilidade, risco de expiração, bytes disponíveis, janela prevista e ganho de ocupação.
- [ ] Registrar cada decisão com motivo, candidatos e métricas usadas.
- [ ] Replanejar somente waves ainda não submetidas ou restauradas, sem mutar manifests ou retenções já efetivadas.

**Marco:** várias sources podem restaurar em paralelo, enquanto o projeto mantém uma transferência controlada e explicável.

### Fase 4 — waves agrupadas para buckets pequenos

- [ ] Definir critérios configuráveis de “source pequena” e “wave pequena”.
- [ ] Criar composição lógica de wave agrupada a partir de waves independentes elegíveis.
- [ ] Apresentar segmentos, custos, jobs e erros individualmente na interface agrupada.
- [ ] Garantir que uma aprovação de restore, falha ou reprocessamento afete somente o segmento correspondente.
- [ ] Permitir que o scheduler selecione outro segmento elegível quando um segmento aguardar restore, sem violar a lane única de transferência.
- [ ] Criar auditoria consolidada e por segmento.

**Marco:** buckets pequenos melhoram ocupação da lane sem perder isolamento técnico ou custo por bucket.

### Fase 5 — interface operacional do projeto

- [ ] Adicionar seletor de projeto na área de Migrations.
- [ ] Criar painel de saúde, custos, timeline e conclusão do projeto.
- [ ] Criar timeline global colorida por source/região, com filtro e tooltip por segmento.
- [ ] Exibir source/bucket/região em todos os reports, notificações, histórico e filas.
- [ ] Adicionar ações globais: iniciar, pausar, retomar e arquivar projeto, sempre com detalhamento das fontes impactadas.
- [ ] Manter os painéis atuais de source como modo de detalhe.
- [ ] Ajustar exportações CSV e relatórios para visão consolidada e visão individual.

**Marco:** o operador controla o projeto sem precisar alternar manualmente entre sources para acompanhar o trabalho diário.

### Fase 6 — custo, integridade e conclusão

- [ ] Consolidar estimativas de custo por projeto, source, bucket, região e wave.
- [ ] Manter cálculo de restore e requisições por source, nunca ratear valores sem evidência.
- [ ] Consolidar resultados de validação OCI e auditoria profunda sem perder o vínculo ao objeto de origem.
- [ ] Implementar estado `COMPLETED_WITH_ATTENTION` e lista explícita de pendências.
- [ ] Exigir que todas as sources estejam concluídas conforme a política para marcar o projeto como `COMPLETED`.
- [ ] Preservar histórico do projeto após arquivamento, sem permitir novas waves.

**Marco:** custo, integridade e conclusão do projeto são reproduzíveis e auditáveis.

### Fase 7 — testes e validação operacional

- [ ] Testar projeto com duas sources na mesma região e conexão.
- [ ] Testar projeto com sources em regiões distintas.
- [ ] Testar colisão de chave original entre buckets com mapeamento OCI seguro.
- [ ] Testar restore paralelo em sources diferentes e uma única transferência ativa.
- [ ] Testar agrupamento lógico de buckets pequenos, falha parcial e reprocessamento de um segmento.
- [ ] Testar re-discovery de uma source durante projeto em andamento.
- [ ] Testar pausa, retomada, reinício de VM e recuperação de scheduler em projeto multi-source.
- [ ] Testar custos, reports, CSV, timeline e conclusão consolidada.
- [ ] Executar suíte completa e teste de regressão de source única.

**Marco:** o fluxo multi-source é validado sem regressão da operação atual de uma source.

## Limites da primeira versão

- Não haverá transferência simultânea de várias waves; a lane global permanecerá única.
- Não haverá um único job S3 Batch Operations para vários buckets.
- Não haverá combinação física de manifestos de regiões distintas.
- Uma source não mudará de bucket, região, conexão ou prefixo OCI após possuir wave submetida.
- O agrupamento de buckets pequenos será uma composição de planejamento, não uma alteração na semântica de restore da AWS.

## Riscos e controles

| Risco | Controle |
|---|---|
| Colisão de chaves no OCI | Prefixo de destino obrigatório por source, metadata de proveniência e constraint de mapeamento. |
| Falta de rastreabilidade | Todo evento, custo, job, object e report referencia projeto, source, bucket, região e wave. |
| Mistura incorreta de regiões | Scheduler regionalizado para restore; jobs e manifests sempre por source/região. |
| Uma source pequena atrasar outras | Política de prioridade documentada, eventos de decisão e fallback para a próxima wave elegível. |
| Custo de restore inesperado | Estimativas e aprovações permanecem por wave/segmento; nenhuma aprovação global implícita. |
| Regressão da operação atual | Testes de source única em todas as fases e feature flag de projeto enquanto a migração de interface não estiver concluída. |

## Critérios mínimos de aceite

- um projeto pode conter múltiplas sources, cada uma com bucket e região próprios;
- nenhuma source contém mais de um bucket;
- nenhuma colisão de chave de destino é possível entre sources do mesmo projeto;
- discovery, waves, manifests, restore, polling, custo e auditoria continuam atribuíveis a uma única source;
- a interface permite acompanhar projeto e source sem perda de detalhe;
- múltiplos restores podem progredir conforme slots globais;
- somente uma transferência permanece ativa por projeto na primeira versão;
- falha ou aprovação de um segmento não desbloqueia nem invalida outro segmento indevidamente;
- projeto só se torna `COMPLETED` quando todas as sources atenderem à política de conclusão;
- o fluxo atual de source única permanece funcional e coberto por testes.

## Próxima decisão antes da implementação

Definir o modelo de destino OCI do projeto:

1. um bucket OCI único por projeto, com prefixo obrigatório por source; ou
2. permitir bucket OCI diferente por source, preservando ainda um prefixo obrigatório por source.

A recomendação inicial é a opção **1**, pois simplifica a governança, a política OCI, a conclusão e a visão de custos. A opção 2 deve permanecer possível se houver requisito de isolamento ou residência de dados.
