# Plano — impacto de atualização e rollout seletivo

## Objetivo

Dar visibilidade confiável do impacto de cada revisão antes de sua instalação
e, em uma segunda fase, permitir atualizar somente componentes isolados sem
interromper transferências que não dependam deles.

## Princípio de segurança

Uma classificação de arquivos não é autorização para um rollout parcial. A
Fase 1 informa o impacto, mas mantém backup e reinício controlado completos.
Somente a Fase 2 cria a separação técnica que torna uma atualização parcial
segura e verificável.

## Fase 1 — classificação e transparência

### Fluxo

```mermaid
sequenceDiagram
    participant A as ADMIN
    participant C as Console
    participant U as Agente root
    participant G as GitHub

    A->>C: Verificar atualizações
    C->>U: Pedido de verificação
    U->>G: fetch origin/main
    U->>U: diff revisão instalada..candidata
    U-->>C: SHA + componentes + impacto + arquivos
    A->>C: Confirma instalação
    C->>U: Pedido atômico da revisão exibida
    U->>U: Backup + reinício controlado completo
```

### Contrato do agente

O arquivo de estado sanitizado inclui:

- `classification`: `WEB_UI_ONLY`, `DOCUMENTATION_ONLY`, `FULL_PLATFORM` ou
  `UNKNOWN`;
- `components`: `WEB_UI`, `WORKERS`, `DATABASE_OR_API`, `HOST_RUNTIME` e/ou
  `DOCUMENTATION`;
- `transfer_impact`: `NONE`, `CONTROLLED_PAUSE` ou `UNKNOWN`;
- `installation_strategy`: nesta fase sempre `FULL_CONTROLLED_RESTART`;
- até 100 caminhos alterados, apenas para evidência administrativa.

### Regras conservadoras

| Alteração | Classificação | Impacto informado |
| --- | --- | --- |
| Apenas `app/static/` ou `images/` | `WEB_UI_ONLY` | Nenhuma lógica de transferência alterada. |
| Apenas documentação | `DOCUMENTATION_ONLY` | Nenhuma lógica de transferência alterada. |
| Código, scripts, imagem, dependências, Terraform ou combinação | `FULL_PLATFORM` | Pausa controlada; componentes e workers reiniciam. |

Mesmo nos dois primeiros casos, o instalador atual faz backup e reinício total.
Isso impede uma inferência incorreta de que o código web possa ser trocado em
produção sem uma fronteira de execução independente.

### Critérios de aceite

- somente o agente root calcula e grava o impacto;
- a console nunca escolhe arquivos, canal Git ou estratégia de instalação;
- o impacto aparece na página Settings e no modal de confirmação;
- todos os textos respeitam o idioma selecionado;
- um diff desconhecido é classificado como `FULL_PLATFORM`/`UNKNOWN`, nunca
  como seguro;
- a instalação continua exigindo fila drenada, backup e health check.

## Fase 2 — rollout realmente seletivo

### Estado de implementação

O primeiro recorte desta fase está implementado: `WEB_UI_ONLY`. Uma revisão
somente recebe a estratégia `WEB_ONLY_ROLLING` quando todos estes controles
são verdadeiros:

1. o diff de runtime contém exclusivamente `app/static/` e/ou `images/`;
   arquivos em `tests/` são evidência de validação e não são empacotados na
   imagem de runtime;
2. o `release-manifest.json` da própria revisão, lido pelo agente root,
   autoriza o contrato `web_ui` versão 1 e sua allowlist de caminhos;
3. a política root-owned `RAIJIN_UPDATE_SELECTIVE_WEB_ONLY=true` está ativa.

Nesse caso, o agente cria a imagem da revisão e substitui somente
`s3-oci-app`, aguardando seu `/healthz`. Os containers de Raikou e Raiju não
são parados, portanto transferências já em andamento continuam. A sessão web
é encerrada como parte da reinicialização da aplicação, e o operador entra
novamente após o health check.

Também está implementado o recorte `CONTROLLER_ONLY`: somente mudanças no
entrypoint isolado `app/controller_worker.py`, acompanhadas opcionalmente de
testes, podem substituir `s3-oci-raikou-shin`. O novo controller precisa
publicar seu heartbeat após iniciar; ele recebe SIGTERM apenas entre ciclos
transacionais de planejamento. Restores e transferências já despachadas não
são interrompidos. Em falha, a imagem e a revisão anteriores do controller
são restauradas.

Qualquer ausência, erro de manifesto, caminho fora da allowlist, alteração de
API/banco/código compartilhado de worker/runtime ou falha de health mantém o
caminho seguro `FULL_CONTROLLED_RESTART`. Além de web e controller, os
entrypoints isolados de restore, discovery, auditoria e transferência podem
ser substituídos seletivamente quando a alteração for limitada estritamente ao
arquivo de entrada daquele consumer. Banco e lógica compartilhada continuam
pendentes dos contratos e testes indicados abaixo.

Os entrypoints e heartbeats desses quatro consumers são isolados por papel.
Os orquestradores de restore, discovery, auditoria e transferência foram extraídos para
`app/restore_execution.py`, `app/discovery_execution.py` e
`app/audit_execution.py` e `app/transfer_execution.py`; após a primeira instalação integral dessas
extrações, alterações limitadas ao respectivo arquivo podem usar seu rollout
seletivo. Os utilitários, protocolo durável e demais lógicas continuam em
`app.real_worker.py`; uma modificação neles segue sendo classificada como
atualização integral até as extrações equivalentes e os contratos específicos
de cada papel estarem concluídos.

### Arquitetura-alvo

```mermaid
flowchart LR
    G[Revisão aprovada] --> M[Manifesto assinado de componentes]
    M --> A[Agente root de rollout]
    A --> W[raijin-web<br/>UI + API]
    A --> C[raijin-controller]
    A --> R[raijin-restore-workers]
    A --> T[raiju-transfer-workers]
    A --> D[(PostgreSQL)]

    W -. rollout web .-> W
    C -. rollout controller .-> C
    R -. rollout restore .-> R
    T -. rollout transfer .-> T
```

### Pré-requisitos obrigatórios

1. Separar a imagem/processo web/API dos processos de worker.
2. Definir contratos versionados entre API, controller, workers e esquema do
   banco; compatibilidade deve ser bidirecional durante rollout.
3. Garantir que workers fazem heartbeats, checkpoint e retomada idempotente.
4. Adotar migrações de banco expansivas/compatíveis antes de qualquer remoção
   de coluna, índice ou semântica antiga.
5. Publicar um manifesto imutável por release, assinado/allowlisted pelo
   agente root, declarando componentes e requisitos de schema.
6. Implementar health checks específicos por componente e rollback por
   componente, não apenas pelo serviço monolítico.
7. Banco produtivo usa revisões explícitas e append-only: a versão 1 é o
   baseline atual; uma revisão futura só pode expandir o schema. Remoções e
   renomeações exigem uma release posterior após a aplicação N/N+1 não usar o
   campo antigo.

### Política de rollout proposta

| Manifesto | Ação | Transferências |
| --- | --- | --- |
| `web` somente | Troca `raijin-web` com health check | Continuam sem interrupção. |
| `controller` | Drena decisões novas, troca controller | Transferências já despachadas continuam. |
| `restore-worker` | Drena worker, troca pool | Transferências continuam; restores aguardam. |
| `transfer-worker` | Checkpoint, substituição gradual de Raijus | Retomam de checkpoint, sem perda. |
| `database` | Janela controlada conforme compatibilidade | Política definida pelo manifesto. |
| `host/runtime` | Atualização completa | Pausa controlada. |

### Validação antes de habilitar

- teste E2E com transferências em curso durante rollout `web`;
- teste de troca gradual de Raijus com multipart e checkpoint persistido;
- compatibilidade de API e banco nas versões N/N+1 e rollback N+1/N;
- injeção de falha durante cada etapa e comprovação de rollback;
- auditoria do manifesto, componente alterado, operador, health checks e
  resultado do rollout.

## Decisão de liberação

Fase 1 pode ser habilitada imediatamente e não reduz os controles existentes.
A Fase 2 só deve ser implementada quando os pré-requisitos de isolamento,
compatibilidade e testes acima forem aceitos como contrato arquitetural.
