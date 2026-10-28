# RAIJIN — fluxo operacional, acessos e evidências

Este documento descreve o runtime **RAIJIN real/local** implementado hoje. O
navegador é apenas uma console de operação: não recebe credenciais e não chama
AWS ou OCI diretamente. O estado, a fila, os checkpoints e as evidências ficam
no PostgreSQL.

## Visão geral

```mermaid
flowchart LR
    Operator[Operador / console web] -->|localhost ou HTTPS| API[API RAIJIN]
    API <--> DB[(PostgreSQL\ninventário, fila, leases\ncheckpoints e evidências)]
    subgraph VM[VM OCI — runtime RAIJIN]
      API
      DB
      Shin[Raikō::Shin\nplanejamento e admissão]
      Sei[Raikō::Sei\nrestore e polling]
      Ko[Raikō::Kō\ndiscovery]
      Kai[Raikō::Kai\ndeep audit]
      Raiju[Raiju\ncópia e multipart]
    end
    Shin <--> DB
    Sei <--> DB
    Ko <--> DB
    Kai <--> DB
    Raiju <--> DB
    VM -->|Instance Principal| OCIAuth[OCI IAM / Dynamic Group]
    OCIAuth --> Vault[OCI Vault\nSecrets AWS e senha PostgreSQL]
    OCIAuth --> OCI[OCI Object Storage\ndestino]
    Ko -->|AssumeRole temporário| AWSSTS[AWS STS]
    Sei -->|S3 Batch Operations + polling| S3[AWS S3\nsource / Glacier]
    Raiju -->|GetObject após restore| S3
    Raiju -->|PutObject ou multipart| OCI
    AWSSTS --> S3
```

## 1. Autenticação, credenciais e pré-check

```mermaid
sequenceDiagram
    participant O as Operador
    participant UI as Console RAIJIN
    participant API as API / workers
    participant OCI as OCI IAM + Vault
    participant STS as AWS STS
    participant S3 as AWS S3
    participant DST as OCI Object Storage

    O->>UI: Seleciona conexão AWS e source
    UI->>API: Registra configuração, sem segredo
    API->>OCI: Instance Principal lê Secret JSON permitido
    OCI-->>API: Valor somente em memória
    API->>STS: GetCallerIdentity + AssumeRole(migration role)
    STS-->>API: Credenciais AWS temporárias
    API->>S3: HeadBucket source e controle
    API->>DST: Consulta autorizada de namespace/bucket
    API-->>UI: VALIDATED ou diagnóstico
```

| Componente | Permissão | Limite importante |
|---|---|---|
| Navegador | Console local | Não lê Secret e não chama cloud. |
| API e workers | Instance Principal da VM | Não expõem valores de Secret em tela, API ou logs. |
| OCI Vault | `read secret-bundles` via Dynamic Group | Apenas fornece segredo em memória ao runtime. |
| AWS bootstrap | Access key dentro do Secret OCI | Apenas assume a role AWS de migração. |
| AWS migration role | Credenciais STS temporárias | Acessa source; não é a role de Batch Operations. |
| AWS Batch role | Assumida pelo serviço S3 Batch Operations | Não é assumida diretamente pelo RAIJIN. |
| OCI destino | Dynamic Group limitada aos buckets permitidos | Não grava fora da policy OCI. |

O pré-check é não destrutivo: valida identidade, `AssumeRole`, buckets e OCI,
mas não lista objetos de source, não submete restore e não transfere dados.

## 2. Discovery, inventário e waves

```mermaid
flowchart TD
    A[Projeto e source cadastrados] --> B{Pré-check válido?}
    B -- não --> BX[Corrigir Secret, IAM, região ou bucket]
    B -- sim --> C{Método de discovery}
    C -->|API remota| D[Raikō::Kō\nListObjectsV2 paginado]
    C -->|S3 Inventory| E[Importa manifest.csv ou manifest.json]
    C -->|CSV/CSV.GZ local| F[Importa inventário sem chamar AWS]
    D --> G[(Inventário durável\nchave, tamanho, ETag, classe, data)]
    E --> G
    F --> G
    G --> H[Operador cria ou libera waves]
    H --> I[Congela membros, rota OCI e parâmetros]
    I --> J[(Tarefas duráveis e estado da wave)]
```

- O discovery remoto persiste checkpoints; após falha, retoma do cursor salvo.
- Re-discovery exige justificativa e não reescreve histórico de objeto já em wave.
- A rota OCI é congelada para os objetos planejados; mudança posterior de
  configuração não desloca dados que já estão no fluxo.

## 3. Planejamento e admissão

```mermaid
flowchart TD
    Q[(Waves READY / RESTORE_SCHEDULED)] --> Shin[Raikō::Shin]
    Metrics[Telemetria: throughput, Raijus,\nbacklog, expiração e retries] --> Shin
    Policy[Políticas: projeto ativo, peso das sources,\nteto de restore e buffer seguro] --> Shin
    Shin --> Risk{Capacidade e risco aceitáveis?}
    Risk -- não --> Hold[Registra espera e motivo]
    Risk -- sim --> RestoreTask[Enfileira restore]
    RestoreTask --> Sei[Raikō::Sei]
    Ready[Objetos restaurados] --> Shin
    Shin --> Dispatch{Lane e Raijus têm folga?}
    Dispatch -- sim --> Lease[Reserva micro-lote para Raiju]
    Dispatch -- não --> ReadyQueue[(Fila contínua pronta)]
```

As decisões são persistentes e auditáveis. O navegador não decide admissão: o
Raikō registra prioridade, capacidade, previsão, motivo e lease. Sem estatística
suficiente em um projeto novo, o comportamento inicial é conservador e limita
concorrência de restores até haver telemetria confiável.

## 4. Restore e janela temporária

```mermaid
stateDiagram-v2
    [*] --> RESTORE_SCHEDULED: wave aprovada/elegível
    RESTORE_SCHEDULED --> RESTORE_REQUESTED: admissão do Raikō
    RESTORE_REQUESTED --> RESTORING: Batch aceito pela AWS
    RESTORE_REQUESTED --> RESTORE_REAPPROVAL_REQUIRED: ação humana necessária
    RESTORING --> READY_FOR_TRANSFER: HeadObject confirma disponível
    READY_FOR_TRANSFER --> TRANSFERRING: Raiju recebe objeto
    TRANSFERRING --> VERIFIED: aceite OCI e evidência persistidos
    VERIFIED --> COMPLETED: wave entregue
    RESTORING --> RESTORE_REQUEST_FAILED: falha não recuperável
    TRANSFERRING --> TRANSFERRED_WITH_ERRORS: diagnóstico necessário
```

1. Raikō::Sei gera o manifesto e submete uma única operação S3 Batch por wave.
2. A tentativa, job, região, manifesto, resposta AWS e erros ficam persistidos.
3. O polling observa `x-amz-restore` apenas nos objetos ainda pendentes.
4. A expiração é a data retornada e observada no S3, nunca uma estimativa local.
5. Objetos disponíveis podem entrar progressivamente na lane, conforme política.

## 5. Cópia, multipart e integridade padrão

```mermaid
sequenceDiagram
    participant S as Raikō::Shin
    participant Q as PostgreSQL
    participant R as Raiju
    participant A as AWS S3
    participant O as OCI Object Storage

    S->>Q: Seleciona objeto por peso, expiração e capacidade
    S->>Q: Cria lease durável do micro-lote
    R->>Q: Assume lease e consulta checkpoint
    R->>A: GetObject após restore disponível
    alt objeto pequeno
        R->>R: Calcula SHA-256 durante o stream
        R->>O: PutObject com checksum
    else objeto grande
        R->>O: Cria multipart e consulta partes aceitas
        loop somente partes faltantes
            R->>R: Calcula SHA-256 da parte
            R->>O: UploadPart com checksum
            R->>Q: Persiste parte e checkpoint
        end
        R->>O: Commit multipart
    end
    O-->>R: Aceite nativo
    R->>Q: Persiste tamanho, SHA-256, proveniência e evidência
```

- O SHA-256 é calculado durante a leitura; ETag não é tratado como MD5 universal.
- O OCI valida checksum antes de aceitar o objeto ou cada parte multipart.
- Metadados compatíveis, tags e proveniência são preservados.
- Após reinício, o Raiju consulta partes aceitas e envia somente as faltantes.
- Leases expirados são reassumíveis; checkpoints evitam falso "concluído".

## 6. Validação, deep audit e fechamento

```mermaid
flowchart LR
    Copy[Evidência da cópia\nSHA-256 + aceite OCI] --> Standard[Integridade padrão]
    Standard --> Reconcile{Validate OCI destination\nsob demanda}
    Reconcile -->|chave, tamanho e proveniência| Valid[Destino reconciliado]
    Reconcile -->|divergência| Investigate[Diagnóstico e reprocessamento controlado]
    Standard --> AuditChoice{Deep audit solicitado?}
    AuditChoice -- não --> Close[Elegível ao fechamento]
    AuditChoice -- sim --> Kai[Raikō::Kai]
    Kai --> ReadOCI[Relê payload OCI completo]
    ReadOCI --> Compare[Compara SHA-256 linear]
    Compare --> AuditOK[Auditoria aprovada]
    Compare --> AuditFail[VERIFICATION_FAILED com evidência]
```

A reconciliação normal não relê payload e não chama AWS: compara chave, tamanho e
proveniência no destino. Deep audit é opcional e intensivo em I/O; requer
confirmação explícita e pode ser pausado/retomado sem bloquear restore ou cópia.

## 7. Recuperação e rastreabilidade

```mermaid
flowchart TD
    Failure[Erro, reinício ou timeout] --> Durable[(PostgreSQL)]
    Durable --> Lease{Lease expirou?}
    Lease -- sim --> Reclaim[Worker compatível reassume]
    Lease -- não --> Wait[Worker original continua]
    Reclaim --> Checkpoint{Há checkpoint?}
    Checkpoint -- multipart --> Resume[Consulta OCI e envia partes faltantes]
    Checkpoint -- restore aceito --> Poll[Continua polling, sem Batch duplicado]
    Checkpoint -- discovery --> Cursor[Retoma cursor confirmado]
    Resume --> Evidence[Atualiza evidência]
    Poll --> Evidence
    Cursor --> Evidence
    Evidence --> Alert[Console, histórico, métricas e relatório]
```

O RAIJIN preserva tarefas, tentativas AWS, jobs Batch, polling, decisões,
leases, checkpoints, checksums, erros e transições. Ele não remove
automaticamente objetos de S3 ou OCI; reprocessamento e deep audit são ações
explícitas e auditáveis.

## Checklist operacional

1. Validar Instance Principal, policies OCI e Secrets.
2. Cadastrar a conexão AWS e executar pré-check.
3. Criar source, selecionar destino autorizado e executar discovery.
4. Criar/aprovar waves e acompanhar decisões do Raikō.
5. Monitorar restores, expiração, backlog e Raijus.
6. Confirmar evidências e executar validação OCI ao final.
7. Usar deep audit apenas quando a releitura integral for justificada.
8. Emitir pacote de fechamento com as evidências consolidadas.

## Referências

- [Architecture](architecture.md)
- [Capabilities](capabilities.md)
- [AWS connections](aws-connections.md)
- [Deployment](deployment.md)
- [Validation test plan](validation-test-plan.md)
- [Recovery runbook](recovery-runbook.md)
