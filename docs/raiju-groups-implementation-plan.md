# Plano futuro — grupos de Raijus por localização

**Status:** planejamento aprovado para detalhamento; implementação ainda não autorizada.
**Objetivo:** permitir transferências simultâneas de mais de um projeto quando cada projeto ativo estiver associado a um grupo exclusivo de Raijus, local ou remoto.

## Decisões consolidadas

| Tema | Decisão |
| --- | --- |
| Composição do grupo remoto | Um grupo remoto corresponde inicialmente a uma única instalação Raijin Transfer, com múltiplas threads/processos Raiju. |
| Projeto sem grupo | Pode executar discovery e planejamento, mas não pode admitir restores ou transferências. |
| Troca de grupo | Somente após drenagem completa: sem Raijus copiando, leases, itens reservados, retries pendentes ou checkpoints em progresso. |
| Credenciais | Permanecem localmente na instalação que executa os Raijus. O plano central não transporta segredos. |
| Exclusividade | Um grupo é exclusivo a um projeto enquanto associado. Para ser usado por outro projeto deve ser drenado e desassociado. |

## Visão de arquitetura

```text
                         ┌──────────────────────────────────┐
                         │ Raijin principal / Control Plane  │
                         │                                  │
                         │ Projetos, sources, waves          │
                         │ Raikō, restore, planejamento      │
                         │ Scheduler e evidências            │
                         │ API, console e banco central      │
                         └───────────────┬──────────────────┘
                                         │ mTLS + API de agentes
                 ┌───────────────────────┼───────────────────────┐
                 │                       │                       │
      ┌──────────▼──────────┐ ┌─────────▼──────────┐ ┌──────────▼──────────┐
      │ Grupo LOCAL          │ │ Grupo REMOTO A     │ │ Grupo REMOTO B     │
      │ instalação principal │ │ localização A      │ │ localização B      │
      │ Raijus locais        │ │ Raiju Transfer     │ │ Raiju Transfer     │
      └─────────────────────┘ │ threads Raiju       │ │ threads Raiju       │
                              └────────────────────┘ └────────────────────┘

Projeto A ── associação exclusiva ── Grupo LOCAL
Projeto B ── associação exclusiva ── Grupo REMOTO A
Projeto C ── associação exclusiva ── Grupo REMOTO B
```

O Control Plane é a única fonte de verdade para projetos, waves, objetos, decisões de restore, prioridade, leases e evidências. A instalação remota executa somente o plano de transferência recebido: ela não possui scheduler autônomo, fila de migrations ou interface de gestão de projetos.

## Modelo operacional

### Grupo de Raijus

Um `RaijuGroup` representa uma localização de transferência e possui:

- identidade estável, nome, localização e tipo (`LOCAL` ou `REMOTE`);
- estado operacional: `REGISTERING`, `HEALTHY`, `DEGRADED`, `OFFLINE`, `DRAINING`, `DISABLED`;
- uma única instalação/agente ativo no primeiro release;
- capacidade declarada: número máximo de Raijus, CPU, memória, limites de I/O e banda;
- telemetria independente: throughput, latência, I/O wait, uso de CPU/memória, workers ativos/ociosos, backlog e último heartbeat;
- referências locais às credenciais e rotas AWS/OCI suportadas;
- versão do protocolo e capacidades anunciadas pelo agente.

O grupo `LOCAL` é criado automaticamente para a instalação principal e usa os Raijus locais existentes. Ele passa a obedecer ao mesmo contrato de grupos sem exigir tráfego remoto.

### Associação exclusiva projeto → grupo

Uma associação é uma entidade versionada e auditável, não apenas uma coluna alterável no projeto.

Estados da associação:

- `PENDING`: grupo validado, aguardando ativação;
- `ACTIVE`: único grupo autorizado a transferir o projeto;
- `DRAINING`: nenhuma nova admissão; itens existentes estão sendo concluídos;
- `RELEASED`: drenagem concluída e grupo liberado;
- `FAILED`: associação não pode prosseguir por falha operacional/compatibilidade.

Invariantes obrigatórias:

1. Um projeto tem no máximo uma associação `ACTIVE`.
2. Um grupo tem no máximo uma associação `ACTIVE`.
3. Nenhuma transferência é iniciada sem associação `ACTIVE` e grupo `HEALTHY`.
4. A associação ativa é gravada como versão em cada lease e batch, impedindo que uma troca de grupo redirecione trabalho já reservado.
5. A desassociação só termina quando não houver trabalho em execução ou recuperável no grupo.

### Ciclo de transferência

1. O operador associa um projeto a um grupo saudável.
2. O Control Plane valida compatibilidade de rota, credenciais declaradas, versão do agente e capacidade mínima.
3. Raikō planeja restores considerando exclusivamente a capacidade e o backlog do grupo associado.
4. Objetos restaurados entram na fila do projeto com o `raiju_group_id` e a versão da associação.
5. O scheduler central seleciona itens elegíveis dentro do grupo, preservando peso de source, prioridade e risco de expiração.
6. O agente remoto busca leases por conexão de saída, confirma o início e executa Raijus locais.
7. Checkpoints multipart, progresso e resultado são enviados ao Control Plane por operações idempotentes.
8. Em falha de agente, leases expiram, itens não iniciados retornam à fila e checkpoints multipart permitem retomada segura.

## Regras de scheduler e restore

### Isolamento por grupo

O controlador atual de lane física, capacidade e autoscaling é singleton por runtime. Ele deverá se tornar um controlador por `raiju_group_id`:

- uma lane contínua por grupo;
- autoscaling, baseline de throughput, cooldown e telemetria por grupo;
- capacidade e alvo de Raijus por grupo;
- decisões e batches com grupo e versão de associação;
- timeline e previsão de conclusão por grupo.

Não haverá fairness entre grupos: grupos diferentes representam capacidade física independente. Dentro de cada grupo, o scheduler preserva a prioridade atual por expiração, peso da source, idade e risco operacional.

### Projetos sem grupo

Um projeto sem grupo pode:

- criar/editar sources;
- executar discovery;
- criar waves e estimativas;
- visualizar custo, inventário e planejamento.

Ele não pode:

- submeter novos restores;
- liberar objetos à lane;
- criar leases de transferência;
- iniciar Raijus.

O console deve explicar o bloqueio como `TRANSFER_GROUP_REQUIRED`; o planejador não deve criar backlog restaurado que não tenha capacidade de transferência associada.

### Restore orientado ao grupo

O planejamento de restore deixa de considerar apenas a capacidade genérica do projeto. Ele deve considerar:

- estado e saúde do grupo associado;
- throughput medido e limite de Raijus do grupo;
- backlog já restaurado naquele grupo;
- prazo de expiração e margem de segurança;
- slots de restore ativos e projetados do projeto/grupo;
- indisponibilidade, drenagem ou incompatibilidade do agente.

Se o grupo estiver `DEGRADED`, `OFFLINE`, `DRAINING` ou sem rota de credenciais validada, novas admissões de restore do projeto ficam suspensas. Transfers já em progresso obedecem lease/checkpoint até concluir ou expirar de modo recuperável.

## Contrato Control Plane ↔ Raiju Transfer Agent

### Conectividade e identidade

- O agente remoto inicia toda a conectividade para o Control Plane; não há porta administrativa de entrada requerida no site remoto.
- Registro inicial usa token de bootstrap de uso único e vincula chave pública/certificado do agente.
- Comunicação posterior usa mTLS, rotação de certificado e identificação do grupo/agente.
- Heartbeats curtos informam versão, capacidade, Raijus ativos, telemetria e rotas disponíveis.
- Falta de heartbeat transiciona o grupo para `DEGRADED` e, depois do limiar configurado, `OFFLINE`.

### Leases e idempotência

O protocolo deve ser pull-based e durável:

1. Agente solicita trabalho para sua capacidade livre.
2. Control Plane reserva itens exclusivamente para o grupo/agente e retorna lease com token, expiração e versão de associação.
3. Agente confirma início antes de copiar.
4. Agente reporta progresso e checkpoint multipart com token idempotente.
5. Agente conclui ou devolve a lease com causa classificada.
6. Control Plane só aceita atualizações da associação/grupo/agente esperados.

Nenhuma operação remota deve escrever diretamente no banco central. A API transacional do Control Plane é a única fronteira de persistência.

### Credenciais e dados

- O agente recebe chave, tamanho, destino autorizado, identificadores de conexão e parâmetros mínimos da cópia.
- Segredos AWS/OCI não são retornados pelo Control Plane.
- Cada localização mantém referências criptografadas locais às suas credenciais, registradas como capacidades da instalação.
- Antes de associar o projeto, o Control Plane exige que o grupo declare compatibilidade com a conexão AWS e rota OCI das sources do projeto.
- O agente executa leitura S3 e escrita OCI diretamente; dados não atravessam o Control Plane.

## Persistência e evolução de esquema

Novas entidades propostas:

| Entidade | Responsabilidade |
| --- | --- |
| `raiju_groups` | localização, tipo, estado, capacidade, configuração e última saúde conhecida. |
| `raiju_group_agents` | instalação única do grupo, identidade mTLS, versão, heartbeat e capacidades. |
| `project_raiju_group_assignments` | associação exclusiva, versionada, estados de drenagem e auditoria. |
| `raiju_group_control_states` | memória de autoscaling e limites da lane por grupo. |
| `raiju_group_measurements` | série temporal de throughput e saúde por grupo. |
| `raiju_group_route_capabilities` | conexões AWS e destinos OCI declarados pelo agente, sem segredos. |

Entidades existentes a estender de forma aditiva:

- `transfer_queue_items`: `raiju_group_id`, `assignment_id`, `assignment_version`;
- `transfer_dispatch_batches` e decisões: grupo/agente/associação;
- checkpoints, leases e eventos: contexto de grupo e agente;
- telemetria/timeline: escopo de grupo;
- projeto: referência derivada à associação ativa, nunca como única evidência histórica.

Migrações devem ser aditivas, reversíveis e compatíveis com a versão atual. O backfill inicial cria o grupo local e associa apenas projetos que já estavam transferindo; itens existentes recebem a associação ativa correspondente sem alterar seus checkpoints.

## Console principal

### Tela “Raiju groups”

Deve apresentar por grupo:

- localização, tipo e estado;
- projeto associado e estado de associação;
- agente, versão, último heartbeat e compatibilidade;
- Raijus ativos/ociosos, capacidade configurada e limite efetivo;
- throughput, I/O, CPU, memória, backlog, leases e retries;
- rotas AWS/OCI autorizadas, sem segredos;
- ações seguras: registrar, desabilitar, iniciar drenagem, visualizar diagnóstico e desassociar após drenagem.

### Projeto

No card do projeto, incluir:

- grupo associado e localização;
- capacidade/saúde resumidas;
- motivo claro quando a transferência estiver bloqueada;
- ação de associar grupo apenas após pré-validação;
- ação de drenagem/desassociação com confirmação e painel de pendências.

Queue, timeline, decisões e métricas devem mostrar o grupo responsável. Filtros por projeto continuam funcionando e filtros por grupo são adicionados para operação transversal.

## Drenagem, indisponibilidade e recuperação

### Drenagem intencional

1. Operador inicia `DRAINING`.
2. Scheduler bloqueia novos restores e novas leases para o grupo/projeto.
3. Raijus terminam apenas os objetos já iniciados; itens reservados sem início retornam à fila.
4. Checkpoints multipart permanecem preservados.
5. Quando não existirem leases, transfers, retries imediatos ou checkpoints em progresso, a associação muda para `RELEASED`.
6. O grupo pode então ser associado a outro projeto.

Não haverá troca forçada de grupo no primeiro release. Falha de localização é recuperada pelo retorno das leases e retomada no mesmo grupo após recuperação; mover para outro grupo requer drenagem completa e ação explícita posterior.

### Falha de grupo

- `DEGRADED`: não cresce concorrência nem admite novos restores; operações já iniciadas são observadas.
- `OFFLINE`: nenhuma nova lease; leases vencidas retornam à fila com evidência de causa.
- credencial inválida ou rota incompatível: bloqueio de admissão e alerta acionável.
- agente incompatível: bloqueio antes de qualquer trabalho ser entregue.

## Estratégia de desenvolvimento e disponibilização sem risco à versão atual

Esta funcionalidade **não será desenvolvida diretamente no runtime atualmente usado**. O trabalho deverá ocorrer em linha futura, com isolamento de código, imagens, banco e infraestrutura.

### Linhas de código e versões

- `main`/release atual: permanece como versão estável utilizada no ambiente corrente e recebe somente correções aprovadas de produção.
- Branch de longo prazo sugerida: `feature/raiju-groups-control-plane`.
- Imagens futuras devem usar namespace/tag distinto, por exemplo `localhost/s3-oci-migration:raiju-groups-dev-<revision>`.
- Nenhum script de deploy da versão atual deve selecionar, por padrão, imagens da futura build.
- Correções compartilháveis devem ser extraídas em commits pequenos e podem ser aplicadas seletivamente à versão atual somente após revisão explícita.

### Ambientes

| Ambiente | Finalidade | Isolamento obrigatório |
| --- | --- | --- |
| Atual/homologação existente | continuidade do Raijin atual e testes em curso | imagem, banco, portas e volumes atuais preservados. |
| Desenvolvimento Raiju Groups | refatoração, contratos e agentes remotos simulados | banco próprio, compose/runtime próprio, portas e credenciais de teste próprias. |
| Pré-produção futura | testes reais controlados após maturidade | VM/recursos próprios ou isolamento completo, credenciais dedicadas, grupos de teste sem tocar no runtime atual. |

O ambiente futuro deve usar banco independente. Não é aceitável apontar uma build de desenvolvimento para o PostgreSQL da versão atual. Migrações de banco serão ensaiadas em cópia anonimizada/sintética antes de qualquer promoção.

### Compatibilidade durante a refatoração

- Introduzir modelos, endpoints e flags de forma aditiva.
- Manter o caminho atual de grupo local atrás de um adaptador compatível durante a transição.
- Não remover as estruturas atuais de lane até a futura build comprovar equivalência no modo local.
- Usar feature flag `RAIJU_GROUPS_ENABLED=false` por padrão em todos os ambientes até a homologação futura.
- Testar upgrade e rollback: schema aditivo, leitura de dados antigos, retorno seguro ao runtime atual e ausência de novas leases remotas após rollback.

## Fases de implementação futura

### Fase 0 — fundação e contratos

- Formalizar OpenAPI/protocolo do agente, autenticação mTLS, códigos de erro e tempos de lease.
- Criar modelo de ameaças, estratégia de certificados e matriz de credenciais por localização.
- Definir limites de heartbeat, transições de saúde e SLOs.
- Produzir ADRs para exclusividade, drenagem e ownership de credenciais.

**Saída:** contratos revisados e ambiente de desenvolvimento isolado criado; nenhum comportamento da versão atual alterado.

### Fase 1 — Control Plane e grupo local em modo compatível

- Criar schema, migrações aditivas e APIs administrativas de grupos/associações.
- Provisionar automaticamente o grupo local.
- Adaptar scheduler, telemetria e leases para escopo de grupo, mantendo apenas o grupo local habilitado.
- Criar testes de regressão que comparem decisões do caminho atual com o caminho de grupo local.

**Saída:** futura build opera com grupo local e reproduz as garantias atuais sem agente remoto.

### Fase 2 — Transfer Agent remoto em modo sombra

- Criar runtime transfer-only, registro, heartbeat e inventário de capacidade.
- Implementar autenticação mTLS e validação de rotas/credenciais declaradas.
- Agente recebe telemetria/planos de teste, mas não recebe leases executáveis.

**Saída:** grupo remoto pode ser registrado e observado sem risco de transferência.

### Fase 3 — Leases remotas e recuperação

- Implementar pull de leases, confirmação, progresso, checkpoints e conclusão idempotente.
- Implementar expiração, devolução, reinício de agente e recuperação multipart.
- Exercitar falhas de rede, relógio, duplicação de requisição, agente reiniciado e Control Plane reiniciado.

**Saída:** uma source de teste transfere de ponta a ponta por grupo remoto no ambiente de desenvolvimento.

### Fase 4 — Planejamento/restore por grupo e console

- Tornar restore admission group-aware.
- Implementar tela de grupos, associação, pré-validação, drenagem e diagnóstico.
- Tornar queue, timeline, decisões e métricas conscientes do grupo.

**Saída:** dois projetos de teste em grupos distintos executam em paralelo, com isolamento verificável de capacidade.

### Fase 5 — pré-produção e promoção

- Instalar Control Plane e um grupo remoto em ambiente de pré-produção futuro isolado.
- Executar testes reais com dados, custos e credenciais controlados.
- Validar desempenho, I/O, recuperação, contenção de restores e segurança.
- Promover somente após critérios de aceite atendidos e aprovação explícita.

## Critérios de aceite

1. Dois projetos associados a grupos distintos transferem simultaneamente sem compartilhar autoscaling, throughput, leases ou decisões de capacidade.
2. Dois projetos não conseguem associar o mesmo grupo simultaneamente.
3. Projeto sem grupo não submete restore nem transfere, mas pode descobrir e planejar.
4. Uma source do mesmo projeto respeita pesos/prioridades dentro do grupo associado.
5. Grupo remoto não recebe nem armazena segredos enviados pelo Control Plane.
6. Perda do agente não perde objetos nem duplica entrega; leases expiram e checkpoints retomam com segurança.
7. Drenagem bloqueia novas admissões, conclui/retorna trabalho corretamente e só libera o grupo quando estiver vazio.
8. Timeline, queue e eventos identificam corretamente grupo, agente e versão de associação.
9. O grupo local na futura build mantém, no mínimo, as garantias de segurança e desempenho da versão atual.
10. A versão atual continua implantável e utilizável sem depender de schema, imagens ou agentes da futura build.

## Riscos a tratar antes da promoção

- latência e indisponibilidade WAN entre agente e Control Plane;
- gestão/rotação de certificados e credenciais por localização;
- consistência de leases em falhas parciais;
- capacidade real de I/O e rede do site remoto;
- compatibilidade de checkpoints multipart entre localizações;
- custo e limites AWS/OCI distribuídos por credenciais/rotas;
- complexidade de observar backlog e expiração em múltiplos grupos;
- operação de rollback sem deixar leases remotas órfãs.

## Fora de escopo do primeiro release

- múltiplas instalações por um mesmo grupo;
- realocação automática de projeto entre grupos;
- failover automático entre localizações;
- scheduler distribuído/autônomo no agente remoto;
- compartilhamento simultâneo de um grupo por vários projetos.
