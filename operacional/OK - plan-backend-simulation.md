# OK — Plano do backend simulado do RAIJIN

## Registro de implementação

- **Tempo total de implementação:** a telemetria de tempo ativo não era registrada nesta fase; portanto não há duração efetiva recuperável sem estimativa artificial.
- **Janela registrada de implementação:** 25/08/2026 a 27/08/2026, conforme os commits do backend isolado, console e validações.
- **Observação:** FUJIN permanece como backend isolado de validação; os workers e regras de domínio usados são os mesmos do fluxo operacional.

## Objetivo

Construir um gêmeo digital do processo de migração: simular AWS, OCI, restores, rede e falhas sem armazenar realmente 100 TB nem gerar custos de nuvem. O objetivo principal é comprovar se o scheduler, os workers, a fila durável, o polling adaptativo, a retomada multipart e o replanejamento reais do RAIJIN tomam decisões corretas quando a execução diverge da previsão.

O antigo `simulated-worker.py`, que avançava tarefas artificialmente, foi removido e não faz parte deste modelo.

## Status do plano

**BOOTSTRAP OPERACIONAL VALIDADO — FLUXO FIM A FIM E ESCALA LÓGICA VALIDADOS.** O backend isolado, os contratos, os buckets virtuais, o relógio, restore, transferência lógica, caminho de dados, multipart, auditoria, templates editáveis com snapshots imutáveis, console, relatório de evidências, timeline previsto/observado e lifecycle estão implementados. Os mesmos workers de produção completaram discovery, Batch restore, polling e transferência contra o simulador implantado na VM. Um ensaio reproduzível também materializou e listou 100 TB lógicos em 640 mil objetos sem payload. `REAL` continua sendo o modo padrão de uma nova instalação; o ambiente de validação está temporariamente em `SIMULATION`, com as operações reais congeladas de forma reversível.

Este documento é a fonte operacional da implementação. Mudanças futuras deverão preservar as decisões consolidadas ou registrar explicitamente a decisão substituta e seu impacto nos critérios de aceite.

## Diretriz de evolução distribuída

Esta implementação deverá respeitar o plano `operational/plan-distributed-control-plane-evolution.md`. O simulador continua sendo um backend externo simulado, nunca um worker, mas suas fronteiras devem preparar o RAIJIN para uma futura separação entre control plane central e Edge Agents remotos.

Desde a Fase 1, contratos e resultados deverão ser explícitos, serializáveis e versionados; integrações, relógio e storage deverão ser injetáveis; IDs de execução e correlação não poderão depender da VM; e nenhuma nova regra de domínio deverá exigir acesso direto ao PostgreSQL por um futuro agente remoto. Isso não implementa Kubernetes agora, apenas impede novas dependências incompatíveis com essa evolução.

## Decisões consolidadas

### Modos mutuamente exclusivos

O modo operacional será explícito e definido no início da execução:

- `RAIJIN_OPERATION_MODE=REAL`
- `RAIJIN_OPERATION_MODE=SIMULATION`

Simulation é diferente do Modo de laboratório. O Modo de laboratório ainda pode operar integrações reais e apenas flexibiliza proteções para testes controlados. Simulation é incapaz de chamar AWS ou OCI reais.

### Os mesmos workers nos dois modos

Não serão criados governance workers ou transfer workers alternativos. Os mesmos processos e handlers usados em produção executarão nos dois modos. Eles continuam responsáveis por leases, restore, polling, liberação, transferência, multipart, retries, checkpoints, estados, eventos e replanejamento.

O `raijin-simulator` não consome a fila durável e não altera diretamente objects, waves ou tasks. Ele representa exclusivamente o comportamento do ambiente externo.

### Modalidade imutável por cenário

Cada cenário será criado em uma única modalidade:

- `CONTROL`: valida escala lógica, scheduler, restore, polling, waves e replanejamento sem transportar o volume físico equivalente;
- `DATA`: valida o caminho efetivo de bytes, streaming, SHA-256, multipart, falhas e retomada.

A modalidade ficará imutável depois da criação da execução. Para testar o mesmo modelo em outra modalidade, o operador deverá clonar o cenário e iniciar uma nova execução. Resultados de `CONTROL` não serão apresentados como evidência de integridade do caminho de dados.

### Orçamento físico da simulação de dados

Execuções `DATA` terão orçamento físico padrão de 1 TB decimal (`1.000.000.000.000` bytes), configurável na console antes do início. Não haverá limite máximo imposto pelo produto.

A console deverá estimar tempo e impacto de CPU, memória e rede local, advertir o operador quando o valor configurado for elevado e exigir confirmação explícita. O orçamento fica congelado durante a execução. Ele limita bytes efetivamente gerados e processados, não o tamanho lógico do cenário.

### Retenção e housekeeping

Cenários, execuções e evidências poderão ser excluídos manualmente. O housekeeping automático terá retenção padrão de 60 dias, configurável na console de simulação.

O prazo será contado a partir da entrada da execução em estado terminal. Depois de 60 dias, o registro passará de `ACTIVE` para `DEPRECATED`: ficará oculto para novas execuções, mas continuará disponível para reprodução, investigação e rollback.

Depois de mais 30 dias de quarentena, e somente quando não houver nenhuma referência, o registro passará para `PURGE_ELIGIBLE`. Uma nova verificação referencial será obrigatória imediatamente antes da transição final para `PURGED`. A purga automática será configurável e poderá exigir aprovação manual.

Durante a quarentena, um administrador poderá restaurar o registro para `ACTIVE`. Execuções ativas, templates e registros ainda referenciados nunca serão removidos. A exclusão deverá ser transacional e auditável; um tombstone mínimo de auditoria será preservado depois da purga. Backups deverão cobrir pelo menos todo o período entre `DEPRECATED` e `PURGED`.

### Contrato e gerador versionados

RAIJIN e `raijin-simulator` serão implantados e atualizados juntos e suportarão uma única versão ativa do contrato interno. Ambos executarão um handshake no startup e recusarão operação quando as versões forem incompatíveis, sem camada de retrocompatibilidade entre contratos.

O algoritmo de geração determinística de bytes terá versão própria persistida em cada cenário e objeto. Enquanto qualquer cenário ou evidência depender de uma versão antiga, sua implementação continuará disponível. Quando não houver mais referências, o housekeeping aplicará o mesmo ciclo `ACTIVE → DEPRECATED → PURGE_ELIGIBLE` e marcará a implementação como elegível para retirada em uma release posterior; código executável não será apagado em runtime.

### Templates e falhas imutáveis

Haverá templates editáveis para cenários conhecidos, como restore lento, liberação gradual, rede degradada e multipart interrompido. Ao iniciar uma execução, o RAIJIN copiará o template, suas configurações, seed e regras de falha para um snapshot customizado e imutável.

Alterações posteriores no template não afetarão execuções existentes. Cada falha concretizada será persistida com seed, objeto, parte, tentativa, chamada e momento virtual. Uma execução poderá ser reproduzida indefinidamente por clonagem desse snapshot até ser excluída manualmente ou pelo housekeeping.

## Arquitetura recomendada

Será criado um serviço `raijin-simulator`, executado como outro container/serviço na VM. Ele é um backend externo simulado, não um worker.

```text
Raijin UI
   │
   ├── PostgreSQL e fila durável
   │
   ├── Governance worker
   │       │
   │       └── AWS real ou simulador
   │
   ├── Transfer workers
   │       │
   │       └── AWS/OCI reais ou simulador
   │
   └── Raijin Simulator
           ├── relógio virtual
           ├── restore simulator
           ├── network simulator
           ├── OCI destination simulator
           └── fault/chaos engine
```

O ponto mais importante: o simulador não deveria simplesmente alterar o status das waves no banco. Isso pularia justamente a lógica que queremos testar.

O ideal é criar interfaces internas para AWS e OCI, com duas implementações:

- `RealCloudBackend`: usa boto3 e OCI SDK.
- `SimulatedCloudBackend`: responde como AWS e OCI, baseado no cenário configurado.

Assim, os mesmos workers do RAIJIN continuam executando o mesmo fluxo, tomando as mesmas decisões, calculando polling e replanejando. Apenas o ambiente externo é simulado.

## Isolamento dos dados

Será usado inicialmente um único container PostgreSQL com dois bancos lógicos e usuários separados:

```text
migration             → operação real
migration_simulation  → simulação
```

Isso separa inventários, sources, waves, filas, históricos e configurações, permite backup e limpeza independentes e evita o custo operacional de um segundo PostgreSQL. Um segundo container poderá ser avaliado futuramente se houver necessidade de isolamento físico ou testes de competição de recursos.

## Níveis de fidelidade

### Simulação de controle em escala

Usa bytes e tempo lógicos para validar centenas de terabytes em poucos minutos: scheduler, criação dinâmica de waves, Batch Operations, polling, liberação gradual, retenção, throughput, concorrência, fila, retries, replanejamento e timeline.

### Simulação do caminho de dados

Usa payload determinístico gerado sob demanda pelo backend AWS simulado para percorrer streaming, SHA-256, multipart, falha, retomada de partes, commit e reconciliação reais. Nenhum arquivo precisa ser baixado da Internet ou da AWS.

O fluxo será:

```text
AWS simulado
  gera bytes determinísticos por objeto e offset
          │
          ▼
transfer worker real do RAIJIN
  faz streaming, SHA-256, multipart, checkpoints e retries
          │
          ▼
OCI simulado
  recebe e valida cada chunk/parte, atualiza as evidências e descarta os bytes
          │
          ▼
PostgreSQL de simulação
  persiste somente catálogo, checksums, manifestos, estados e histórico
```

O gerador deve aceitar leitura por faixa (`offset` e `length`) com memória limitada, permitindo reiniciar uma parte multipart sem regenerar ou manter o objeto inteiro em disco. O conteúdo será definido por uma seed, pela identidade e pela versão do objeto, tornando cada byte reproduzível.

O destino simulado deve calcular os checksums sobre os bytes efetivamente recebidos. Ele não pode simplesmente copiar ou confiar no checksum informado pelo backend AWS, pois isso esconderia erros de streaming, corrupção, ordenação ou retomada. Cada chunk deve ser consumido e descartado imediatamente; nenhum payload será gravado em PostgreSQL ou no filesystem.

Para cada objeto, o banco de simulação manterá apenas:

- bucket virtual, chave, versão, tamanho lógico, classe, data, metadata e tags;
- seed ou descritor determinístico do conteúdo;
- SHA-256 observado na origem, no worker e no recebimento do destino;
- número, tamanho e SHA-256 de cada parte multipart recebida;
- hash do manifesto ordenado das partes, estado do upload e evidência do commit;
- timestamps, checkpoints, retries, falhas e corrupção determinística injetada.

Há uma limitação criptográfica importante: o SHA-256 linear de um objeto não pode ser reconstruído apenas a partir dos SHA-256 de suas partes. Portanto, na retomada multipart a garantia normal será formada pela comparação independente de cada parte, pela ordem e completude do manifesto, pelo tamanho final e pelo SHA-256 integral calculado pelo worker. Quando uma auditoria profunda for solicitada, o simulador regenerará deterministicamente o stream para recalcular o SHA-256 integral sem armazenar o payload.

As consultas `List`, `Head` e validações do bucket OCI virtual serão respondidas pelo catálogo persistido. Assim, o RAIJIN poderá executar reconciliação e auditoria posteriormente como faria contra o OCI, sem ocupar espaço com os objetos simulados.

Os dois níveis usam os mesmos workers. A simulação lógica de 100 TB não afirma processar fisicamente 100 TB; a fidelidade do caminho de bytes será comprovada separadamente em volume menor.

## Source lógico de 100 TB

Não precisamos criar nenhum arquivo físico. O simulador pode materializar apenas o inventário:

- chave;
- tamanho lógico;
- storage class;
- ETag e checksum fictícios;
- data de modificação;
- tempo previsto de restore;
- perfil de transferência;
- possibilidade de falha.

Com base na proporção do cenário de 1,5 PB e 9,6 milhões de arquivos, um source de 100 TB teria aproximadamente 640 mil objetos. Essa quantidade já seria uma boa prova de volume para PostgreSQL, criação de waves e interface.

Também podemos criar distribuições mais realistas:

- 60% de arquivos pequenos;
- 25% médios;
- 10% grandes;
- 5% muito grandes;
- alguns objetos acima do tamanho normal de uma wave;
- diretórios/prefixos com prioridades diferentes.

O “tamanho de 100 TB” seria lógico, ocupando apenas os registros do inventário, não 100 TB em disco.

## Relógio virtual

Esse é um componente essencial. Não faz sentido esperar 48 horas em cada simulação.

Poderíamos configurar, por exemplo:

- 1 hora simulada = 1 segundo real;
- 24 horas simuladas = 24 segundos;
- 48 horas simuladas = 48 segundos.

O relógio do sistema operacional não seria alterado. O simulador manteria seu próprio tempo virtual, preservindo separadamente:

- horário real de execução;
- horário simulado do cenário;
- fator de aceleração.

Isso permite observar dias ou semanas de operação em poucos minutos.

## O que poderia ser simulado

### Restore

- Restore curto, médio ou longo.
- Arquivos liberados todos juntos.
- Liberação gradual.
- Pequenos grupos liberados ao longo do tempo.
- Batch Job aceito, rejeitado ou parcialmente aceito.
- Restore que nunca conclui.
- Objeto individual com falha.
- Expiração da cópia restaurada antes da transferência.
- BULK e STANDARD com distribuições diferentes.
- Mudança inesperada no tempo de disponibilidade.

### Rede e transferência

- Throughput constante.
- Redução progressiva de banda.
- Oscilações periódicas.
- Queda total durante determinado período.
- Latência alta para arquivos pequenos.
- Reinício de worker.
- Falha durante multipart.
- Retomada de upload multipart.
- Erros transitórios e throttling.
- Recuperação gradual da banda.

Um perfil poderia ser assim:

```text
00h–04h: 1.100 Mbps
04h–07h: 400 Mbps
07h–08h: link indisponível
08h–14h: 750 Mbps com oscilação de ±20%
14h+:    1.100 Mbps
```

O Raijin precisaria perceber a diferença entre previsão e desempenho real e recalcular as próximas janelas.

### OCI

- Upload aceito.
- Parte multipart rejeitada.
- Timeout durante upload.
- Objeto já existente.
- Objeto divergente no destino.
- Falha de checksum.
- Indisponibilidade temporária do bucket.

## Cenários prontos

Eu criaria inicialmente estes perfis:

| Cenário | Restore | Rede | Finalidade |
|---|---:|---|---|
| Ideal | 30h, pouca variação | 1.100 Mbps estável | Validar o fluxo esperado |
| Restore rápido | 8–12h | estável | Validar antecipação excessiva |
| Restore lento | 45–48h | estável | Validar limite do BULK |
| Liberação gradual | 24–48h por grupos | estável | Testar transferência antecipada |
| Rede degradada | normal | 200–700 Mbps | Testar replanejamento |
| Rede oscilante | normal | variação e quedas | Testar adaptação |
| Multipart interrompido | normal | queda durante arquivo grande | Testar retomada |
| Falhas parciais | alguns objetos falham | estável | Testar retry e diagnóstico |
| Retenção insuficiente | restore normal | transferência lenta | Testar risco de expiração |
| Chaos controlado | aleatório com seed | variável | Testar resiliência geral |

Cada execução deve aceitar uma `seed`, permitindo reproduzir exatamente a mesma sequência de eventos.

## Administração centralizada

A interface poderia ter uma área exclusiva de simulação contendo:

- criação de cenário;
- source lógico e distribuição de arquivos;
- escala do relógio;
- perfil de restore;
- perfil de rede;
- falhas programadas;
- botão iniciar, pausar, avançar tempo e encerrar;
- comparação entre planejamento original e execução;
- timeline prevista versus observada;
- decisões de replanejamento tomadas pelo Raijin;
- custo lógico estimado, sem custo real.

Tudo deve ser persistido no banco `migration_simulation`. Se a VM reiniciar, o cenário volta pausado no último checkpoint e exige retomada explícita. Isso evita avanço virtual inesperado e preserva a reprodutibilidade.

## Proteções necessárias

Não será reutilizada a antiga flag de simulation worker. A separação será explícita:

- conexão do tipo `SIMULATED`;
- source marcado como simulado;
- nenhuma Secret AWS associada;
- backend simulado incapaz de chamar AWS ou OCI;
- banner permanente de simulação;
- eventos e relatórios identificados como `SIMULATED`;
- proibição de misturar waves reais e simuladas na mesma source;
- possibilidade de apagar completamente uma execução simulada.
- nenhuma Secret AWS montada no modo Simulation;
- nenhuma configuração OCI runtime montada no modo Simulation;
- `RealCloudBackend` impossível de instanciar no modo Simulation;
- interface real ocultada enquanto o banco e backend simulados estiverem ativos.

Isso torna impossível uma simulação chamar a AWS acidentalmente.

## Troca controlada de modo

A troca não poderá ocorrer a quente durante processamento. O comando planejado é:

```bash
sudo raijin-mode simulation
sudo raijin-mode real
sudo raijin-mode status
```

Fluxo obrigatório:

1. Colocar a plataforma em `DRAINING` e bloquear novos claims e agendamentos.
2. Verificar transfer, multipart, restore, polling, discovery, deep audit e tasks `READY` ou `RUNNING`.
3. Recusar a troca com diagnóstico explícito se houver processamento ativo.
4. Parar os mesmos governance e transfer workers.
5. Alterar modo efetivo, banco e backend.
6. Montar somente as dependências permitidas no modo escolhido.
7. Reiniciar aplicação e os mesmos workers.
8. Validar banco, serviços e modo antes de liberar a interface.

A interface poderá iniciar esse procedimento controlado, mas não receberá acesso genérico ao socket do Podman ou ao systemd.

## Bootstrap da simulação

O bootstrap idempotente deverá preparar:

- banco e usuário de `migration_simulation`;
- schema e migrations;
- conexão AWS lógica `SIMULATED`, sem Secret;
- bucket S3 lógico;
- destino OCI lógico, sem OCID;
- cenários e perfis iniciais;
- relógio virtual e persistência;
- container `raijin-simulator`;
- barreiras contra credenciais e integrações reais.

## Plano de implementação

### Fase 0 — remover o modelo legado

- [x] Remover `scripts/simulated-worker.py`.
- [x] Remover serviço systemd, cartão de saúde, configuração visual e endpoint que avançava tasks artificialmente.
- [x] Registrar este plano como substituto oficial do modelo antigo.
- [x] Remover a coluna legada `simulation_enabled` por migration explícita depois que o novo modo estiver disponível.

### Fase 1 — fundação e isolamento

- [x] Introduzir `RAIJIN_OPERATION_MODE` validado no startup.
- [x] Criar interfaces mínimas `RealCloudBackend` e `SimulatedCloudBackend` na fronteira das integrações.
- [x] Versionar o contrato interno e bloquear startup quando RAIJIN e simulador forem incompatíveis.
- [x] Manter os mesmos handlers e workers em ambos os modos.
- [x] Criar banco, usuário, migrations e backup de `migration_simulation`.
- [x] Criar bootstrap idempotente e barreiras contra recursos reais.
- [x] Exibir modo efetivo e banner permanente na UI.

### Fase 2 — troca segura de modo

- [x] Implementar `DRAINING` e bloqueio de claims/agendamentos.
- [x] Auditar operações ativas antes da troca.
- [x] Criar `raijin-mode real|simulation|status`.
- [x] Recusar troca ativa com contagem de bloqueios.
- [x] Reiniciar aplicação e os mesmos workers com banco/backend corretos.

### Fase 3 — inventário e recursos sintéticos

- [x] Criar conexão e destino do tipo `SIMULATED`.
- [x] Tornar `CONTROL` ou `DATA` imutável por execução e permitir clonagem entre modalidades.
- [x] Criar gerador determinístico de inventário por distribuição.
- [x] Versionar o gerador determinístico e persistir a versão usada por cenário e objeto.
- [x] Suportar 100 TB lógicos e aproximadamente 640 mil objetos.
- [x] Gerar prefixos, storage classes, checksums e objetos extremos.

### Fase 4 — relógio e restore

- [x] Implementar relógio virtual persistente e aceleração.
- [x] Fazer o scheduler dinâmico criar, replanejar e liberar waves pelo relógio virtual da execução.
- [x] Manter leases e retries da fila no relógio real e exibir os dois relógios alinhados no banner.
- [x] Pausar automaticamente após reinicialização.
- [x] Modelar Batch Operations, aceite e evidências.
- [x] Modelar restore conjunto, gradual, parcial, falho e expirado.
- [x] Executar o polling adaptativo real contra o simulador.

### Fase 5 — transferência lógica

- [x] Modelar throughput, latência e concorrência.
- [x] Simular redução, oscilação, indisponibilidade e recuperação de banda.
- [x] Registrar progresso lógico e checkpoints pelos workers reais.
- [x] Validar replanejamento das próximas waves, inclusive usando duração lógica observada em perfis de rede simulados.

### Fase 6 — caminho de dados e resiliência

- [x] Aplicar orçamento físico padrão de 1 TB decimal, configurável e congelado no início da execução.
- [x] Exibir limite inferior ideal de duração a partir do orçamento físico e throughput, com alerta de que CPU, hashing, checkpoints, retries e falhas aumentam o tempo real; exigir confirmação explícita a partir de 1 TB.
- [x] Produzir payload determinístico por objeto, versão e faixa, sem arquivo físico e com memória limitada.
- [x] Transportar o stream apenas pela rede local entre os backends simulados e os workers reais.
- [x] Calcular independentemente SHA-256 na origem simulada, no worker e sobre os bytes recebidos pelo destino simulado.
- [x] Consumir e descartar imediatamente os bytes no destino, proibindo persistência do payload no banco ou filesystem.
- [x] Persistir catálogo do bucket virtual, evidências, checkpoints e resultados de validação.
- [x] Simular multipart, falha de parte, retomada e commit, registrando checksum de cada parte e manifesto ordenado.
- [x] Implementar `List`, `Head` e validação sobre o bucket OCI virtual.
- [x] Regenerar o stream determinístico para auditoria profunda e SHA-256 integral sob demanda.
- [x] Simular timeout, corrupção e falhas de origem/destino.
- [x] Persistir perfis de corrupção/falha determinísticos para reproduzir exatamente o cenário.
- [x] Criar testes que falhem se qualquer payload for persistido ou se o destino aceitar checksum sem ler os bytes.
- [x] Garantir reprodutibilidade pela seed, inclusive em execução clonada.

### Fase 7 — interface, observabilidade e relatórios

- [x] Criar console minimalista de cenários.
- [x] Criar templates editáveis e snapshots imutáveis por execução.
- [x] Permitir clonagem e reprodução exata de uma execução pelo snapshot e pela seed.
- [x] Configurar retenção do housekeeping, com padrão de 60 dias.
- [x] Implementar housekeeping diário, quarentena padrão de 30 dias e lifecycle `ACTIVE → DEPRECATED → PURGE_ELIGIBLE → PURGED`.
- [x] Permitir restauração administrativa durante a quarentena e exigir confirmação manual antes da purga física.
- [x] Exigir validação cruzada no control plane: source arquivada, execução terminal e nenhuma task/discovery ativa antes da purga.
- [x] Preservar resumo da execução e tombstone SHA-256 depois de remover catálogo e evidências volumosas.
- [x] Exibir relógio real e virtual.
- [x] Exibir relatório agregado por execução com orçamento físico, operações, falhas injetadas, restore jobs e multipart.
- [x] Exibir previsto versus observado e decisões persistidas do scheduler.
- [x] Integrar timeline e inventário de bordo à console de simulação.
- [x] Marcar eventos e relatórios como `SIMULATED`.

### Fase 8 — validação

- [x] Testar primeiro um cenário pequeno por contrato HTTP e caminho de dados.
- [x] Testar o fluxo completo usando os mesmos workers: discovery, manifesto Batch, evidência individual, polling, transferência e integridade no destino descartável.
- [x] Executar todos os cenários predefinidos com seeds registradas.
- [x] Executar cenário lógico de 100 TB e aproximadamente 640 mil objetos.
- [x] Confirmar por guardas automatizadas que credenciais/configuração real são recusadas em Simulation.
- [x] Validar exclusão manual e housekeeping sem atingir execução ativa, template ou registro referenciado.
- [x] Validar rollback de `DEPRECATED` para `ACTIVE`, tombstone e cobertura de backup durante a quarentena: os bancos real e simulado possuem dump diário e backup do boot volume com retenção padrão de 35 dias.
- [x] Validar que algoritmo legado só se torna removível quando sua última referência desaparecer.
- [x] Documentar critérios de aprovação e aprendizados.

### Evidência de escala registrada

O comando reproduzível `scripts/validate-simulation-scale.py` foi executado com
640.000 objetos e 100.000.000.000.000 bytes lógicos. O catálogo foi
materializado em 48,658 segundos e listado em 640 páginas de 1.000 objetos em
36,471 segundos. O banco SQLite temporário ocupou 422.469.632 bytes e foi
removido automaticamente ao final. Nenhum payload de objeto foi criado ou
persistido. Este ensaio comprova a escala do catálogo e da paginação; os
cenários `DATA` continuam sendo a evidência separada do caminho físico de bytes.

O comando `scripts/validate-dynamic-planner-scale.py` validou o control plane
com o mesmo volume: inseriu 640.000 registros em 41,083 segundos, criou 10
waves dinâmicas e atribuiu cada objeto exatamente uma vez em 39,000 segundos.
O total atribuído permaneceu em 100.000.000.000.000 bytes e o SQLite temporário
ocupou 246.104.064 bytes. O planejador manteve apenas limites escalares e fez a
atribuição por paginação de chave e atualizações em lote; o banco temporário foi
removido ao final.

O comando `scripts/validate-simulation-templates.py` executa os onze templates
predefinidos com seeds registradas e imutáveis. A matriz percorre inventário,
restore, relógio virtual, disponibilidade e transferência; nos cenários
`DATA`, percorre streaming, multipart, retry, checksum e descarte. Os perfis de
falha precisam produzir evidência persistida para o comando ser aprovado. A
execução registrada concluiu os onze templates; o perfil de falha parcial
aceitou 99 de 100 objetos e os demais perfis concluíram seus caminhos esperados.

### Aprendizados da primeira validação

- Decisões probabilísticas não podem depender do UUID do banco. Restore,
  jitter, ETag lógico e falhas agora usam a identidade determinística do
  objeto, mantendo o replay idêntico entre catálogos clonados.
- A expiração da cópia restaurada precisa ser parte do contrato do backend.
  `Head`, leitura e transferência recusam o objeto expirado, e uma nova
  solicitação de restore volta a ser aceita.
- Validadores de catálogo também precisam provar paginação completa. A matriz
  falha quando a quantidade listada difere da quantidade materializada.
- A quarentena reversível só é operacionalmente segura quando a retenção de
  backup é maior que ela; por isso a configuração padrão passou a 35 dias.

## Critérios mínimos de aceite

- os mesmos workers de produção executam toda a máquina de estados;
- o simulador nunca altera diretamente tasks, waves ou objects;
- Simulation não recebe credenciais ou configuração OCI real;
- não é possível trocar de modo durante processamento ativo;
- dados reais e simulados nunca aparecem na mesma consulta;
- reinício continua deterministicamente do checkpoint;
- a seed reproduz a mesma sequência de eventos;
- o cenário de 100 TB não exige payload físico equivalente;
- multipart, hash e retomada são testados separadamente com bytes reais menores;
- o destino calcula evidências a partir dos bytes efetivamente recebidos e descarta cada chunk;
- PostgreSQL e filesystem não armazenam payloads simulados;
- List, Head, reconciliação e auditoria funcionam sobre o bucket virtual persistido;
- a cadeia de evidências distingue SHA-256 integral de checksums de partes multipart;
- nenhuma chamada real AWS ou OCI ocorre durante a simulação.

## Resultado esperado

É plenamente viável e vale muito a pena. A ordem que eu adotaria seria:

1. Criar as interfaces `RealCloudBackend` e `SimulatedCloudBackend`.
2. Implementar inventário sintético e source simulado.
3. Implementar relógio virtual e eventos agendados.
4. Simular restore e liberação gradual.
5. Simular banda, concorrência e transferência.
6. Adicionar falhas, retries e multipart interrompido.
7. Criar console de cenários e comparação previsto × realizado.
8. Executar o cenário lógico de 100 TB.

O primeiro cenário de 100 TB deveria ter aproximadamente 640 mil objetos, 10 a 20 waves planejadas e relógio acelerado. Depois poderíamos escalar para os 9,6 milhões de objetos do cenário completo de 1,5 PB.

Essa abordagem permitiria validar não somente “se o Raijin funciona”, mas principalmente se ele toma boas decisões quando as condições reais deixam de seguir o planejamento.

## Evidência de implantação na VM — 25/08/2026

- OCI Resource Manager aplicado sem recriar a VM ou destruir volumes.
- Secret e senha do PostgreSQL de simulação criadas no Vault; Secrets AWS
  legadas foram preservadas e permanecem fora do runtime do RAIJIN.
- Retenção do backup automático do boot volume atualizada para 35 dias.
- Release ativa: `eebd7db`; ambiente de validação temporariamente em modo
  `SIMULATION`.
- Aplicação, PostgreSQL, simulador, governance worker e transfer worker
  saudáveis.
- Banco `migration_simulation` e role `migration_simulation` validados de forma
  isolada; Secret local protegida com modo `0400` e propriedade do UID/GID 70
  usado por `postgres:16-alpine`.
- Backup lógico validado para `migration` e `migration_simulation`; timers de
  backup, status e troca de modo ativos.
- Antes da troca, foram criados dumps lógicos dos bancos real e simulado em
  `/var/lib/s3-oci-migration/backups/` e um snapshot reversível das quatro tasks
  reais em `/var/lib/s3-oci-migration/operator-freezes/real-to-simulation-20260825/`.
  As waves reais foram pausadas sem cancelar, concluir ou mover as tasks entre
  bancos. O arquivo `unfreeze.sql` restaura exatamente os estados operacionais
  anteriores quando o retorno a `REAL` for autorizado.
- A troca `REAL → SIMULATION → REAL → SIMULATION` foi validada. Em cada passagem,
  aplicação e workers utilizaram somente o banco e o backend correspondentes ao
  modo efetivo.
- Suíte final: 177 testes aprovados. Restam somente avisos de depreciação do
  FastAPI `on_event` e da pilha WebSocket, sem falha funcional.

### Aprendizado do primeiro bootstrap

O primeiro bootstrap parou de forma fail-closed porque o processo PostgreSQL
não conseguia ler a Secret de simulação montada com propriedade exclusiva de
`root`. O rollback automático restaurou a release anterior sem perda de dados.
A correção mantém o arquivo em `0400`, mas atribui sua propriedade ao UID/GID
70 do PostgreSQL Alpine. Um teste de contrato impede regressão. A revisão final
também passou a auditar a fila simulada com o role `migration_simulation`, para
garantir que o retorno a `REAL` use as mesmas fronteiras de isolamento.

O bootstrap também recebeu um trap fail-closed na release `33c0231`. Qualquer
falha agora para e remove os containers parcialmente iniciados, inclusive o
PostgreSQL com restart policy, mas preserva integralmente o volume persistente.
Isso evita que o unit do systemd permaneça em `deactivating` e permite retry ou
rollback sem intervenção manual. A atualização foi instalada sem reiniciar o
runtime real e a suíte permaneceu com 176 testes aprovados.

A homologação controlada congelou quatro tasks reais: uma transferência que já
estava pausada e três pollings de restore. Todas continuam `READY`, porém suas
waves estão `PAUSED`, portanto não são elegíveis para claim e não bloqueiam a
troca de modo. Nenhuma task real foi cancelada ou marcada artificialmente como
concluída.

### Validação funcional do bootstrap na VM

O primeiro cenário funcional revelou três diferenças entre testes locais e a
implantação real: o `ExecStop` não encerrava o PostgreSQL com restart policy; a
migration executada como arquivo não encontrava o package `app`; e a senha do
banco simulado preservava quebra de linha durante o bootstrap. As releases
`a74e848` e `49fe285` corrigiram esses pontos e adicionaram testes de contrato.

O primeiro caminho de transferência também revelou que a evidência lógica usa
o prefixo `logical:` seguido de 64 caracteres hexadecimais, excedendo o antigo
`VARCHAR(64)`. A migration de schema 3 ampliou o campo para `VARCHAR(128)` na
release `eebd7db`; a migration e seu teste foram executados com sucesso na VM.

O cenário `bootstrap-validation-complete-20260825` comprovou o fluxo implantado:

- 10 objetos e 10 MiB lógicos descobertos;
- uma wave dinâmica criada e colocada na fila;
- 10 solicitações de restore aceitas e um job concluído;
- primeiro e último objeto observados como disponíveis após 5 segundos reais;
- 10 transferências lógicas processadas pelos workers reais;
- execução terminal `SUCCEEDED`, sem falhas injetadas e sem payload persistido;
- relatório com 10 operações `RESTORE`, 10 `LOGICAL_TRANSFER` e evidência final
  do bucket virtual de destino.

Um cenário separado acelerou tanto o relógio que sua cópia temporária expirou
antes do polling seguinte. O comportamento foi corretamente preservado como
evidência de perda de janela, demonstrando que retenção, expiração e relógio
virtual não são ignorados pelo worker. Essa wave foi mantida no banco de
simulação como `PAUSED`, sem task executável, para preservar a evidência sem
consumir polling nem bloquear uma futura troca de modo.

Os dumps manuais que antecederam a homologação foram restringidos a modo
`0600`. O ambiente encerrou a validação em `SIMULATION`, com healthcheck
positivo, contrato interno versão 1 e nenhuma task simulada executável.

### Console operacional unificada

A experiência de operação foi consolidada depois da primeira homologação. Em
`SIMULATION`, a rota principal volta a servir a mesma console diária do RAIJIN:
**Status**, **Queue**, **Migrations** e **Settings** consultam o banco isolado e
acionam os mesmos workers de governança e transferência, agora ligados ao
backend virtual. Discovery, estratégia, criação de waves, queue e reports não
são duplicados na console técnica.

O botão **Simulation**, localizado entre **Migrations** e a engrenagem, abre a
rota `/simulation`; ele usa texto vermelho quando inativo e fundo vermelho com
texto branco quando selecionado. Essa página administra somente o backend: cenários imutáveis,
templates, fidelidade `CONTROL`/`DATA`, orçamento físico, relógio virtual,
injeção de falhas, evidência, replay e housekeeping. Um banner vermelho
permanente identifica o modo em todas as páginas.

Como defesa em profundidade, o runtime simulado recusa endpoints exclusivos de
AWS/OCI reais — Secrets, conexões, buckets, readiness e preços — e também o
cadastro/edição estrutural de sources reais. APIs operacionais permanecem
disponíveis. A rota `/simulation` responde somente no modo simulado; em `REAL`,
ela retorna `404` e seu botão não é exibido.

A interface unificada foi entregue na release `fe9d335` e implantada na VM em
25/08/2026, preservando o modo `SIMULATION`, os três cenários existentes e os
backups/bloqueios do banco real. A suíte fechou com 179 testes aprovados. Na VM,
`/`, `/simulation`, sources, settings, observabilidade, tasks, events, summary,
waves e inventário responderam corretamente; endpoints de conexão AWS
continuaram bloqueados com `503`, e nenhum container simulado recebeu variáveis
de credencial AWS ou configuração OCI.
