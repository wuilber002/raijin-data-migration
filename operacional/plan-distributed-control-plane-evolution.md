# Plano de evolução distribuída do RAIJIN

## Registro de implementação

- **Tempo total de implementação:** não iniciado.
- **Observação:** este é um direcionador arquitetural para a futura separação entre control plane e agentes remotos; não autoriza uma migração para Kubernetes nesta fase.

## Status

**DIRETRIZ ARQUITETURAL APROVADA — IMPLEMENTAÇÃO FUTURA E INCREMENTAL.**

Este documento define o destino arquitetural do RAIJIN e passa a orientar novas decisões. Ele não autoriza nem inicia agora a migração para Kubernetes ou multi-tenancy. Toda implementação presente deve continuar funcional na VM única, mas evitar decisões que dificultem a futura separação entre control plane e execução no ambiente do cliente.

## Visão

Evoluir o RAIJIN de uma plataforma local executada em uma única VM para um control plane central, multi-tenant e altamente disponível, capaz de coordenar transferências executadas por agentes remotos dentro do ambiente de cada cliente.

```text
                         RAIJIN CONTROL PLANE
                 API, UI, scheduler e governança global
                                  │
                    work orders, leases e telemetria
                                  │
             ┌────────────────────┼────────────────────┐
             │                    │                    │
             ▼                    ▼                    ▼
      Edge Agent A         Edge Agent B         Edge Agent C
      Kubernetes           VM/container         Kubernetes
             │                    │                    │
        AWS A → OCI A         AWS B → OCI B         AWS C → OCI C
```

O payload nunca deverá atravessar o control plane. Downloads, streaming, SHA-256, multipart e uploads ocorrerão no Edge Agent implantado próximo às origens e destinos do cliente.

## Premissa obrigatória para decisões futuras

Toda nova arquitetura, modelo de dados, contrato, worker ou funcionalidade deverá ser avaliada pela seguinte pergunta:

> Esta decisão preserva a possibilidade de executar o mesmo trabalho por um Edge Agent remoto, com isolamento por tenant e sem acesso direto ao banco central?

Uma solução local poderá ser adotada agora quando for simples e segura, desde que:

- a lógica de domínio não dependa de systemd, Podman, filesystem ou identidade da VM;
- integrações externas estejam atrás de contratos explícitos;
- comandos, resultados e checkpoints sejam serializáveis e versionáveis;
- identidade de tenant, projeto, execução e agente possa ser acrescentada sem reinterpretar o histórico;
- nenhum estado global impeça concorrência entre clientes;
- credenciais e payloads possam permanecer exclusivamente no ambiente de execução;
- relógio, storage, fila, telemetria e clientes cloud possam ser substituídos por adapters;
- operações permaneçam idempotentes e retomáveis depois de perda de comunicação.

## Terminologia

- **Control Plane:** serviço central que mantém configuração, planejamento, ordens, leases, histórico, políticas, interface e visão multi-tenant.
- **Data Plane:** ambiente onde os bytes são lidos, validados e enviados.
- **Edge Agent:** runtime do RAIJIN instalado no ambiente do cliente e responsável por executar trabalhos locais.
- **Worker Pool:** conjunto de workers pertencentes a um Edge Agent e com capacidades declaradas.
- **Work Order:** comando durável, versionado e idempotente entregue a um agente.
- **Tenant:** cliente isolado administrativamente.
- **Project:** migração ou agrupamento operacional pertencente a um tenant.
- **Execution:** execução concreta e imutável de um plano, cenário ou conjunto de waves.
- **Capability:** função declarada por um agente, como discovery, restore, transfer, multipart ou deep audit.

## Princípios consolidados

### O mesmo núcleo operacional

Não serão criados produtos independentes para execução local, Kubernetes e VM remota. O mesmo núcleo de domínio, máquina de estados, integridade, restore, polling, multipart, retry e checkpoint será reutilizado por diferentes empacotamentos.

### Control plane não transfere payload

O control plane recebe somente configurações não sensíveis, ordens, progresso, métricas, checksums, evidências, diagnósticos e relatórios. Conteúdo de objetos não passa por ele e não é persistido nele.

### Conexão iniciada pelo agente

O Edge Agent deverá estabelecer conexão de saída com o control plane. Não será exigida porta de entrada no ambiente do cliente. Long polling, streaming bidirecional ou protocolo equivalente poderá transportar ordens e eventos sobre mTLS.

### Banco central não é exposto ao agente

Edge Agents remotos nunca acessarão diretamente o PostgreSQL central. Toda comunicação ocorrerá por um contrato autenticado e autorizado do control plane.

### Credenciais permanecem no ambiente do cliente

Secrets AWS, OCI e outras credenciais de data plane serão resolvidas localmente pelo Edge Agent. O control plane manterá apenas referências, identidade da conexão, status de validação e políticas necessárias ao planejamento.

### Kubernetes não é o scheduler de domínio

Kubernetes manterá processos vivos, escalará réplicas e administrará recursos. O scheduler do RAIJIN continuará decidindo waves, restore, prioridade, fairness, retenção e elegibilidade dos trabalhos.

### Sem pod master único

O control plane será composto por serviços replicáveis. Liderança exclusiva, quando necessária, usará eleição ou lock durável. Nenhum pod individual será fonte única de verdade ou ponto único de falha.

## Arquitetura alvo

### Control plane central

- API e interface web replicáveis;
- autenticação, tenants, projetos e autorização;
- scheduler e política de fairness;
- PostgreSQL central altamente disponível;
- fila de work orders e leases;
- registry de Edge Agents e capabilities;
- gestão de versões e rollout;
- telemetria, relatórios e auditoria;
- estimativas e planejamento global;
- armazenamento de evidências sem payload.

### Edge Agent

- supervisor local;
- governance workers;
- transfer workers;
- adapters AWS e OCI;
- resolução local de credenciais;
- checkpoint local mínimo para tolerar desconexão;
- spool durável de eventos ainda não confirmados;
- rate limits e throughput locais;
- health, métricas e logs;
- canal mTLS de saída para o control plane.

### Formas de implantação do Edge Agent

- Helm chart em Kubernetes;
- container Docker ou Podman em VM Linux;
- instalação single-node administrada pelo cliente;
- futuramente, outras plataformas que satisfaçam o mesmo contrato de agente.

## Modelo de execução distribuída

1. O operador cria ou aprova uma execução no control plane.
2. O scheduler gera um work order com ID global, tenant, projeto, versão do contrato, requisitos e chave de idempotência.
3. Um Edge Agent autorizado e compatível solicita trabalho e recebe um lease limitado.
4. O agente valida capacidades, configuração local e referências de credenciais.
5. O mesmo handler de domínio usado localmente executa discovery, restore, polling, transferência ou auditoria.
6. Heartbeats renovam o lease e enviam progresso monotônico.
7. Checkpoints são persistidos localmente antes da confirmação ao control plane.
8. Eventos usam sequência e idempotency key; reenvios não duplicam efeitos.
9. O resultado final inclui evidências, checksums, contadores, timestamps e diagnóstico sanitizado.
10. Se o agente desaparecer, o trabalho só poderá ser reatribuído após expiração do lease e análise do checkpoint.

## Estados e ownership

O control plane será autoridade sobre intenção, planejamento, ownership do lease e histórico consolidado. O Edge Agent será autoridade temporária sobre progresso local ainda não confirmado, sessões multipart e evidências produzidas durante a execução.

Estados deverão ser monotônicos ou possuir transições compensatórias explícitas. Nenhum agente poderá substituir silenciosamente um resultado anterior. Conflitos de epoch, lease ou sequência serão rejeitados e auditados.

Cada work order deverá conter, no mínimo:

- `tenant_id`;
- `project_id`;
- `execution_id`;
- `work_order_id`;
- `agent_id` e `worker_pool_id`, quando atribuídos;
- tipo e versão do contrato;
- idempotency key;
- lease epoch e expiração;
- requisitos de capability;
- referências opacas de origem e destino;
- política de retry e deadline;
- checkpoint esperado ou versão anterior.

## Multi-tenancy

O isolamento deverá existir desde o modelo de dados até métricas e logs:

- `tenant_id` obrigatório nos agregados de domínio novos;
- `project_id` obrigatório em sources, pipelines e execuções futuras;
- autorização por tenant e projeto em todas as APIs;
- quotas de workers, throughput, requests, restores e armazenamento de evidências;
- fairness para impedir que um cliente monopolize a fila;
- chaves de criptografia e retenção configuráveis por tenant;
- exportações, relatórios e métricas sempre filtrados por tenant;
- testes automáticos de isolamento horizontal;
- possibilidade de PostgreSQL RLS como defesa adicional, nunca como única camada.

A limitação atual de uma wave de transferência deverá futuramente ser escopada por projeto ou política do tenant, não permanecer como lock global da plataforma.

## Segurança e enrollment

1. O administrador cria um enrollment token de uso único, curto e associado ao tenant/projeto.
2. O agente usa o token para registrar sua identidade e chave pública.
3. O control plane emite certificado mTLS de curta duração.
4. O agente passa a autenticar todas as mensagens com esse certificado.
5. Certificados são rotacionados automaticamente e podem ser revogados.
6. Work orders são autorizados pelas capabilities e pelo escopo do agente.
7. Credenciais cloud nunca são retornadas pelo control plane.
8. Logs e erros passam por redaction antes do envio.

Ordens sensíveis deverão ser assinadas ou protegidas pelo canal autenticado com binding de tenant, agente, epoch e idempotency key. Replay fora do lease será rejeitado.

## Operação desconectada

O Edge Agent deve tolerar indisponibilidade temporária do control plane:

- uma transferência já autorizada poderá continuar enquanto o lease e a política permitirem;
- checkpoints, eventos e métricas serão mantidos em spool local durável;
- nenhuma nova ordem será inventada localmente;
- depois da reconexão, eventos serão reenviados em sequência e deduplicados;
- se o lease expirar sem renovação, o comportamento será definido pela política da ordem: concluir o objeto atual e pausar, ou interromper no próximo checkpoint seguro;
- o control plane exibirá claramente `AGENT_OFFLINE`, progresso conhecido e idade da última confirmação.

## Observabilidade

Todas as métricas deverão carregar dimensões de baixa cardinalidade para tenant, projeto, agente, pool, tipo de tarefa e resultado. IDs de objeto não deverão ser labels de métricas.

O control plane deverá acompanhar:

- agentes online, degradados, incompatíveis e offline;
- idade de heartbeat e lease;
- fila e tempo de espera por tenant;
- progresso confirmado e progresso apenas local;
- throughput, throttling, retries e falhas;
- versão do agente e capabilities;
- diferenças entre planejamento e execução;
- volume de telemetria pendente no spool;
- uso de quotas e fairness.

Logs terão correlation IDs para tenant, projeto, execução, work order e tentativa. Traces distribuídos poderão ser adicionados sem alterar o contrato de domínio.

## Versionamento e atualização

- Control plane, Edge Agent e contratos terão versões independentes e declaradas.
- O agente anunciará versão e capabilities durante o handshake.
- O control plane só atribuirá ordens compatíveis.
- Uma janela curta de compatibilidade entre versões adjacentes será necessária para rollout distribuído, mesmo que o simulador local continue sendo atualizado junto com o RAIJIN.
- Alterações destrutivas de schema usarão expansão, migração e contração.
- Rollback deverá preservar work orders, checkpoints e eventos produzidos pela versão nova.

## Etapas de evolução

### Estágio 0 — preparação na arquitetura atual

- Introduzir interfaces para cloud, relógio, fila, storage e telemetria.
- Remover novas dependências diretas entre domínio e systemd/Podman/filesystem.
- Criar IDs e contratos serializáveis e versionados.
- Tornar locks e configurações explicitamente escopáveis.
- Adotar migrations controladas fora do startup da API.
- Preservar idempotência e checkpoints portáveis.
- Usar o backend simulado para validar fronteiras e falhas.

### Estágio 1 — Kubernetes single-tenant

- Empacotar API, governance e transfer workers como Deployments.
- Usar StatefulSet ou PostgreSQL gerenciado para persistência.
- Substituir timers systemd por CronJobs.
- Criar Helm chart, probes, requests/limits, PodDisruptionBudgets e NetworkPolicies.
- Adotar identidade de workload e Secrets compatíveis com o cluster.
- Manter o mesmo banco e fila, sem execução remota.

### Estágio 2 — workers escaláveis no mesmo cluster

- Remover locks globais e escopá-los por projeto/pool.
- Centralizar rate limiting distribuído.
- Declarar capabilities e capacidade de cada worker pool.
- Implementar fairness e quotas.
- Validar múltiplos tenants logicamente isolados no mesmo cluster.

### Estágio 3 — separação Control Plane e Edge Agent

- Introduzir work orders, leases remotos, epochs e event sequencing.
- Criar canal de saída autenticado e spool local.
- Remover acesso direto dos workers remotos ao banco central.
- Distribuir Edge Agent como Helm chart e container para VM.
- Manter credenciais e payload no ambiente do cliente.
- Validar desconexão, reconexão, atualização e rollback.

### Estágio 4 — operação multi-tenant

- Habilitar tenants e projetos em produção.
- Aplicar autorização, quotas, fairness, retenção e billing por tenant.
- Tornar control plane altamente disponível.
- Implementar fleet management, rollout e revogação de agentes.
- Executar testes de isolamento, carga, disaster recovery e segurança.

## Impacto no backend simulado

O backend simulado continua representando AWS, OCI, rede e tempo; ele não se transforma em worker. Entretanto, sua implementação deverá ajudar a preparar a evolução distribuída:

- contratos serializáveis, explícitos e versionados;
- relógio e integrações injetáveis;
- nenhuma dependência do singleton global da VM;
- IDs de execução e correlação presentes desde o início;
- falhas de desconexão, heartbeat, lease e replay adicionáveis aos cenários;
- suporte futuro a múltiplos tenants e agentes simulados;
- evidência de que payload nunca alcança o control plane.

As modalidades `CONTROL` e `DATA` permanecem válidas. `CONTROL` provará scheduler, leases e replanejamento em escala; `DATA` provará streaming e integridade no data plane local.

## Anti-padrões proibidos daqui em diante

- criar um novo worker que altere estados sem executar os handlers reais;
- adicionar locks globais sem chave de escopo;
- usar hostname como identidade definitiva de negócio;
- fazer um Edge Agent depender de acesso ao PostgreSQL central;
- enviar credenciais cloud ou payload ao control plane;
- armazenar estado essencial apenas no filesystem efêmero de um pod;
- depender de chamadas de entrada no ambiente do cliente;
- misturar scheduling de domínio com criação direta e individual de pods;
- criar contratos não versionados ou resultados sem idempotency key;
- usar um único pod master como fonte de verdade;
- adicionar tabelas de domínio novas sem considerar tenant, projeto e execução;
- introduzir sleeps ou acesso direto ao relógio em lógica que precisará ser simulada.

## Checklist obrigatório para novas decisões

Toda mudança arquitetural ou funcional relevante deverá responder e registrar:

1. Qual é o tenant, projeto e execution scope do novo estado?
2. Existe lock, limite ou configuração global que deveria ser escopado?
3. O comando e seu resultado são serializáveis, versionados e idempotentes?
4. Um Edge Agent poderia executar a operação sem consultar o banco central?
5. A operação continua segura com mensagem duplicada, fora de ordem ou reenviada?
6. O checkpoint sobrevive a reinício de processo, pod, VM e perda de conexão?
7. Alguma credencial ou payload sairia indevidamente do ambiente do cliente?
8. Há dependência direta de filesystem, hostname, systemd, Podman ou relógio real?
9. Métricas, logs e eventos possuem correlation IDs e evitam dados sensíveis?
10. Como a mudança será testada no backend simulado em `CONTROL` e, quando aplicável, em `DATA`?
11. Como upgrade, incompatibilidade e rollback afetam trabalhos em andamento?
12. A versão single-tenant na VM continua funcionando sem complexidade operacional desnecessária?

Uma resposta negativa não proíbe automaticamente a mudança, mas exige registrar a exceção, justificativa, dívida técnica e caminho de remoção. Exceções silenciosas não serão aceitas.

## Registro de decisões

Decisões relevantes deverão ser adicionadas a este plano ou a um ADR operacional contendo:

- contexto e problema;
- decisão adotada;
- alternativas consideradas;
- impacto na VM atual;
- impacto em Kubernetes e Edge Agents;
- segurança e isolamento;
- estratégia de migração e rollback;
- testes e critérios de aceite;
- dívida técnica deliberadamente assumida.

## Critérios de aceite da transformação futura

- a versão single-tenant continua operando durante a evolução;
- o mesmo handler de domínio pode executar localmente ou por Edge Agent;
- três tenants conseguem transferir simultaneamente sem acessar dados entre si;
- indisponibilidade do control plane não corrompe transferência em andamento;
- reenvio de eventos e resultados não duplica efeitos;
- um agente comprometido não acessa ordens ou evidências de outro tenant;
- credenciais e payloads permanecem no data plane;
- rollout e rollback preservam checkpoints multipart;
- scheduler aplica quotas e fairness sem lock global;
- backend simulado reproduz perda de agente, lease expirado e reconciliação;
- Kubernetes pode substituir pods sem perda de estado durável.

## Decisões técnicas futuras, não bloqueadoras agora

Estas escolhas serão feitas no estágio correspondente:

- protocolo do canal de agente: gRPC, streaming HTTP ou long polling;
- broker dedicado ou fila persistida no PostgreSQL;
- PostgreSQL gerenciado ou operado no cluster;
- tecnologia do spool local do agente;
- modelo exato de identidade de workload por provedor;
- duração de leases e política durante desconexão;
- granularidade final de quotas e fairness;
- janela suportada de compatibilidade entre versões de Edge Agent.

Essas decisões não impedem o backend simulado ou a operação atual, desde que as premissas e interfaces deste documento sejam respeitadas.

## Próximo passo quando autorizado

Ao retomar a implementação do backend simulado, iniciar pelo Estágio 0 em conjunto com a Fase 1 do plano de simulação: definir portas de domínio, contexto de execução, contrato versionado e isolamento, sem ainda implantar Kubernetes nem Edge Agents remotos.
