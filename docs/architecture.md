# Arquitetura

Uma única VM Linux em OCI hospeda a aplicação, PostgreSQL, orquestrador, workers e interface web. A interface escuta exclusivamente em `127.0.0.1`; a operação remota é feita por túnel SSH.

O PostgreSQL é a fonte de verdade e a fila durável. As tarefas usam reserva transacional, lease e heartbeat. Após uma queda ou reboot, tarefas com lease expirado são retomadas de forma idempotente.

## Backend simulado planejado

O RAIJIN terá um modo `SIMULATION` mutuamente exclusivo com o modo `REAL`. Ele
usará os mesmos governance e transfer workers, substituindo somente as
integrações AWS e OCI por um backend externo simulado. Inventários, fila,
histórico e configurações ficarão em um banco lógico separado chamado
`migration_simulation`; credenciais e configurações das nuvens reais não serão
montadas nesse modo.

Cada execução será imutavelmente `CONTROL`, para validar grandes volumes de
forma lógica, ou `DATA`, para validar streaming, SHA-256, multipart e retomada
com bytes determinísticos gerados localmente. O destino virtual calculará
evidências sobre os bytes recebidos e os descartará imediatamente, mantendo no
banco somente catálogo, checksums, manifestos e histórico.

A troca de modo exigirá drenagem completa dos trabalhos. RAIJIN e simulador
usarão um único contrato interno versionado e deverão passar por handshake de
compatibilidade no startup. A capacidade permanece planejada e seu contrato
funcional está detalhado em [Capacidades e operação](capabilities.md).

## Princípios

- O encerramento do projeto é uma fronteira probatória própria. A aplicação
  revalida todos os gates em transação, congela um snapshot canônico e persiste
  os bytes exatos do PDF e do ZIP no PostgreSQL. Downloads posteriores nunca
  recalculam dados mutáveis. A unicidade `(project_id, revision)` serializa
  emissões concorrentes; toda revisão posterior referencia a anterior e exige
  justificativa. O manifesto cobre as evidências técnicas, seu SHA-256 é
  impresso no PDF e `checksums.sha256` cobre manifesto e documento. Secrets e
  configuração interna não entram no snapshot.

- A camada web possui um componente compartilhado para formatar toda duração
  operacional recebida em segundos. Ele é usado pelas consoles RAIJIN e FUJIN,
  incluindo cards, relatórios, filas, estimativas e tooltips, e mantém separado
  o tratamento de timestamps absolutos. O formato incremental omite unidades
  vazias e zeros residuais (`12:32:12`, não `0d 12:32:12`; `48h`, não
  `48h 00:00:00`) e usa meses fixos de 30 dias e anos fixos de 365 dias.

- O autoscaler valida coortes com 12 janelas de baseline e 12 janelas depois
  da estabilização do worker experimental. Um P95 operacional só substitui o
  alvo configurado após 180 medições independentes e próximas do contrato; o
  limite configurado permanece como teto físico.
- O reforecast persiste apenas deslocamentos de pelo menos 15 minutos ou 5%
  da duração da wave e coalesce sua narrativa em intervalos de uma hora.
  Previsões distinguem tempo de serviço exclusivo da wave de tempo de
  calendário observado na lane compartilhada.

- Uma onda tem no máximo 10 TB.
- Ondas podem ser criadas uma a uma, automaticamente para toda a origem ou automaticamente para um prefixo S3. A seleção é determinística por chave S3; a prévia informa objetos, bytes, estimativa de ondas e objetos acima do tamanho alvo.
- Um objeto maior que o alvo não bloqueia o planejamento: ele recebe uma onda exclusiva sinalizada no histórico. A criação automática é limitada a 10.000 ondas por ação como proteção operacional.
- Uma onda só pode ser excluída antes de uma tarefa ser assumida; a exclusão devolve seus objetos a `DISCOVERED`. Depois de restore, polling, transferência ou verificação iniciados, os dados são preservados para auditoria.
- A transferência é uma lane contínua, durável e orientada a objeto. Uma wave continua sendo a fronteira de restore, custo, manifesto e auditoria, mas não reserva com exclusividade os Raiju: objetos restaurados de waves distintas podem compartilhar a lane da mesma source. O scheduler inicia no piso de cinco Raijus e reinicia com, no máximo, o coorte produtivo conservador de oito; só experimenta outro slot após 12 janelas novas de 20 s abaixo de 90% do limite agregado. Com 90% ou mais, conserva o coorte produtivo e não adiciona pressão somente para perseguir os últimos pontos percentuais. Cada experimento exige ganho marginal robusto. Uma experiência rejeitada volta ao último coorte aprovado e bloqueia novas sondagens por seis horas; depois disso, somente 12 amostras independentes ainda abaixo de 90% autorizam uma única nova prova serial. A console separa o limite configurado do teto efetivo P95 observado nas seis horas recentes. Host, memória e pool PostgreSQL impõem teto de admissão. Arquivos já em cópia não são interrompidos.
- A origem é lida uma única vez por objeto e enviada em streaming para OCI Object Storage. `GetObject` fornece simultaneamente conteúdo e metadados, evitando uma chamada `HeadObject` adicional por arquivo. A consulta de tags pode ser desabilitada em Configurações quando não for requisito de migração, eliminando também `GetObjectTagging`.
- SHA-256 é calculado durante a leitura do S3. Para objetos pequenos, o valor é enviado ao `PutObject` e validado pelo OCI antes da aceitação. Para objetos grandes, cada parte multipart recebe SHA-256 próprio e o OCI valida todas as partes antes do commit. O tamanho-base da parte é configurável na console (64 MiB por padrão) e é gravado no checkpoint do objeto; para respeitar o máximo OCI de 10.000 partes, a plataforma o aumenta automaticamente em objetos muito grandes. A evidência nativa de entrega fica no PostgreSQL sem reler o destino.
- A reconciliação OCI sob demanda lista o destino paginado e compara chaves e tamanhos com o discovery persistido. Nos itens equivalentes, faz `HeadObject` somente no OCI para comparar a proveniência imutável gravada na cópia: ETag e data de última modificação da versão S3. Uma divergência reabre apenas os objetos e ondas afetados; não relê payload nem chama AWS.
- A onda recebe o estado **CONCLUÍDO** somente quando todos os seus objetos foram transferidos e possuem evidência criptográfica de aceitação pelo OCI. Após uma auditoria profunda sem divergências, ela passa para **CONCLUÍDO (AUDITADO)** (`VERIFIED` internamente).
- `VERIFY_WAVE` é uma **auditoria profunda** excepcional: ela relê integralmente o OCI e compara o SHA-256 linear calculado na origem. A criação exige confirmação explícita, o progresso por objeto é persistido e um heartbeat independente renova o lease durante toda a releitura. Enquanto a tarefa estiver `READY` ou `RUNNING`, a wave permanece `VERIFICATION_QUEUED` mesmo que a reconciliação da lane confirme que a transferência terminou. O resultado terminal permanece visível no histórico e uma wave integralmente auditada preserva o estado `VERIFIED` nas reconciliações posteriores da lane.
- O Status mostra taxa atual de 15 segundos, throughput concluído, e arquivos transferidos por minuto/hora, todos calculados a partir de uma janela de até cinco minutos. Para restores, mantém o total acumulado de objetos arquivados solicitados e disponíveis. Objetos STANDARD não entram nas métricas de restore.
- As medições independentes da lane persistem, no mesmo instante, throughput
  agregado e quantidade de Raijus ativos. O endpoint histórico consolida uma
  única série limitada: prioriza essas medições e completa apenas o período
  legado com bytes e concorrência reconstruídos dos segmentos duráveis. Cada
  ponto carrega sua proveniência. O Resultado final desenha throughput em Mbps
  e workers nos mesmos intervalos; trechos medidos são sólidos e reconstruídos
  são tracejados. Para não inventar picos pela sobreposição retrospectiva de
  segmentos, somente a reconstrução é limitada ao contrato congelado; uma
  medição direta pode comprovar valor superior. O mesmo limite congelado impede
  que uma alteração posterior nas configurações reescreva o histórico.
- Durante o polling de restore, o worker persiste o instante em que cada objeto ficou disponível e a data de expiração da cópia temporária retornada pelo S3 (`Restore`/`RestoreStatus`). Esses dados alimentam a fila, o relatório e a própria lista de waves: após a conclusão, a coluna **Restore** mostra a duração entre a solicitação e a disponibilidade de todos os objetos; enquanto houver objetos pendentes, mostra `Restore em andamento`. Isso permite medir o tempo real de restore e a primeira expiração iminente sem chamadas AWS adicionais. A expiração representa somente a cópia temporária em S3 Standard; o objeto arquivado original permanece preservado.
- A VM executa dois workers reais isolados pela mesma fila durável: **governança** (discovery, Batch Operations, polling, agendamento e auditoria profunda) e **transferência** (cópia e retomada multipart). Cada papel só reivindica seus tipos de tarefa; uma cópia longa não posterga o polling de restore.
- A política de liberação pertence à wave: `AFTER_ALL_RESTORED` mantém o comportamento conservador e só libera a cópia quando todos os objetos estiverem disponíveis; `AS_OBJECTS_AVAILABLE` libera cada objeto assim que o polling identifica sua disponibilidade. Waves dinâmicas usam obrigatoriamente `AS_OBJECTS_AVAILABLE`; uma wave pode permanecer `RESTORING` enquanto seus objetos disponíveis são transferidos.
- Quando existem waves criadas pelo planejador `DYNAMIC`, a tela **Queue** oferece o **Inventário de bordo**. Ele constrói uma linha do tempo local com as fases fila, restore e transferência, distinguindo janelas previstas de tempos efetivamente observados. Cada criação dinâmica gera uma execução persistente de pipeline, com versão do planejador, parâmetros, estratégia, amostras históricas e vínculo imutável a todas as suas waves. Após a conclusão, esse registro deixa de depender da fila: fica disponível na própria origem em **Histórico de bordo**, incluindo a linha do tempo e os estados observados da execução. As consultas leem somente PostgreSQL, sem chamadas AWS ou OCI.
- Após a evidência individual de aceitação do Batch, o polling de disponibilidade evita chamadas agressivas. Sem histórico, preserva a cadência pública do tier: **2 horas**, **1 hora** após metade da janela e **30 minutos** no último quarto. Quando o Raijin possui previsão própria de primeira disponibilidade, usa checkpoints de no máximo **12 horas** no trecho inicial e faz o último intervalo terminar exatamente no início da guarda conservadora de até seis horas antes da previsão. Na guarda passa para uma hora e, próximo da previsão, trinta minutos. O algoritmo usa somente observações do Raijin e o contrato público AWS; nunca consulta datas internas do Fujin. Após disponibilidade parcial, `AS_OBJECTS_AVAILABLE` mantém 5, 10 ou 30 minutos conforme o volume pendente. A evidência Batch é idempotente: depois que o relatório de conclusão foi importado, o worker não volta a chamar `DescribeJob` nem a reler o relatório a cada polling.
- A **criação dinâmica** não congela todas as waves do inventário. Ela calcula a janela útil de cópia a partir da retenção solicitada, descontando uma reserva operacional para retries, oscilações e interrupções recuperáveis. Em seguida, empacota cada próxima wave com previsões por objeto: P75 da própria source por faixa de tamanho (`até 1 MiB`, `até 16 MiB`, `até 256 MiB`, grande e multipart) quando há pelo menos cinco amostras; sem histórico, usa overhead por objeto, tamanho, workers, throughput e partes multipart. Volume e quantidade de objetos são consequências desses limites de tempo, não entradas do operador. Medições com falha ou duração ausente não entram no aprendizado.
- O agendador dinâmico é obrigatório para esse modo e mantém somente um horizonte durável configurável de waves materializadas (três por padrão). Ele preserva a última wave desse horizonte sem submissão Batch; assim, no padrão, duas podem estar elegíveis para restore e uma permanece replanejável. Cada ciclo de governança cria a próxima wave apenas quando abre espaço no horizonte, já usando as medições observadas nas anteriores; portanto tamanho, quantidade e horários das futuras waves são recalculados progressivamente. Uma wave não submetida que já alcançou sua elegibilidade preserva esse instante histórico; a espera por slot aparece separadamente como projeção. Uma wave posterior bloqueada apenas pelo teto máximo de estoque somente pode ultrapassar anteriores se o estoque projetado cair abaixo do mínimo operacional; preenchimento opcional até o alvo respeita a ordem. A ultrapassagem e sua contenção registram estoque, limiar e waves envolvidas, sem reescrever datas planejadas. Ciclos sem mudança material são idempotentes. O deadline seguro é monotônico e cada violação gera uma única evidência durável. Jobs aceitos, restores e transferências nunca são reescritos. A observabilidade expõe tanto risco de expiração quanto waves que perderam o deadline de submissão.
- Cada conexão AWS possui limites persistentes de requisições por segundo para discovery e polling, além da concorrência máxima do polling. Isso permite adequar a plataforma aos limites e acordos operacionais de cada conta sem reduzir a segurança dos checkpoints.
- A **criação dinâmica** usa obrigatoriamente o agendamento antecipado: a primeira janela usa somente o limite de serviço do tier (48 h para BULK ou 12 h para STANDARD), e a reserva operacional antecipa a submissão das waves seguintes em relação ao início previsto de sua cópia. O **horizonte de restores** limita quantas waves dinâmicas podem estar materializadas e com restore liberado em paralelo (padrão: três). Isso evita acumular cópias temporárias antes da necessidade e deixa o histórico refinar apenas waves ainda não criadas.
- A fila de transferência no Status lista a onda ativa, seus workers, os bytes e arquivos concluídos e o tempo acumulado de cópia; as ondas restantes aparecem em ordem de processamento.
- Auditorias profundas aparecem separadamente no Status, com progresso de releitura, taxa, estimativa restante e divergências. A fila apresenta primeiro a wave `RUNNING`, permanentemente expandida; depois as tarefas `READY` em ordem de enfileiramento; e, por fim, resultados terminais pela conclusão mais recente. Waves aguardando ou concluídas ficam recolhidas por padrão e podem ser abertas sem perder esse estado durante as atualizações automáticas. A identidade compacta usa projeto, número e nome da wave e status.
- Uma source é considerada ativamente transferindo quando a lane possui itens `LEASED` por uma tarefa `TRANSFER_CONTINUOUS`. Um objeto que permaneça em `TRANSFERRING` após falha, pausa ou retry não mantém indevidamente a source no quadro de atividade: leases expirados são recuperados e itens pendentes retornam à fila durável.
- Ao concluir uma wave, a console exibe sua duração operacional de cópia: do primeiro arquivo iniciado ao último arquivo concluído, incluindo eventuais interrupções e retomadas.
- O bloco **Atividade de migração** é independente da saúde da VM. Sua atualização automática pode ser desativada ou configurada entre 5 segundos e 5 minutos; essa preferência fica persistida no PostgreSQL da plataforma.
- O mesmo bloco mostra CPU e memória da VM. A CPU é uma média host-wide entre as execuções do timer de estado (normalmente um minuto); a memória usa `MemAvailable` do Linux para calcular a parcela efetivamente ocupada. O snapshot expira após três minutos: dados antigos deixam de ser apresentados como estado atual, e todo deploy reinstala, reinicia e valida o timer de coleta.
- Uma origem recebe a marca **Concluído** quando discovery e transferência terminarem e todos os objetos tiverem evidência de entrega validada pelo OCI; `VERIFIED` identifica adicionalmente objetos que passaram por auditoria profunda.
- Se a validação explícita do destino OCI detectar objeto ausente ou tamanho divergente, os objetos afetados voltam para `WAVE_ASSIGNED`, suas ondas para `READY_FOR_RESTORE` e a origem deixa de ser concluída. Nenhum restore ou retransferência é iniciado automaticamente; o operador usa **Reprocessar** quando decidir corrigir a divergência.
- Discovery usa somente `ListObjectsV2` e campos retornados pelo S3; não faz restore nem leitura de conteúdo. Até dez páginas (no máximo 10.000 objetos) são persistidas em uma transação junto com o `ContinuationToken`, total de páginas e objetos inseridos. Isso limita memória e commits do PostgreSQL; após uma interrupção, a source retoma do último checkpoint confirmado e pode reler, no máximo, nove páginas ainda não confirmadas. A duração persistida é tempo de execução acumulado, sem somar espera na fila. Uma falha de AWS pode ser retomada pelo operador sem relistar páginas confirmadas.
- Cada discovery remoto possui um `DiscoveryJob` independente das tarefas de wave. O job possui lease, tentativas, erro e conclusão; a tela Queue lê apenas o PostgreSQL para acompanhá-lo. A listagem tem teto de dez chamadas de API por segundo e backoff exponencial para `SlowDown`/throttling. A lista de objetos da console usa cursor `(object_key, id)`, não `OFFSET`; assim navegar por inventários grandes não obriga o banco a percorrer as páginas anteriores.
- Chamadas AWS são minimizadas. Restore usa S3 Batch Operations por onda; depois da aceitação comprovada pelo relatório da Batch, o polling consulta somente os objetos arquivados ainda pendentes da própria wave com `HeadObject`, em lotes concorrentes limitados. A execução possui teto explícito de 10 consultas por segundo e 10 consultas simultâneas, além dos retries do SDK. Isso evita varrer o prefixo inteiro da source e não produz leitura de payload. O timestamp `restored_at` é sempre a hora em que o Raijin observou disponibilidade; a data de expiração retornada pela AWS é guardada separadamente e nunca é usada para inferir a hora real de restore. Para fontes sem histórico, a previsão dinâmica usa 1,25 s de overhead por objeto como premissa conservadora; após cinco transferências na mesma faixa de tamanho, passa a usar P75 observado da própria origem.
- Sem previsão aprendida, a cadência de disponibilidade começa em 2 horas, passa para 1 hora na metade da janela pública do tier e para 30 minutos no último quarto. Com previsão própria, o Raijin reduz consultas no trecho inicial e inicia uma guarda conservadora antes do primeiro arquivo previsto. Depois do primeiro objeto disponível, `AS_OBJECTS_AVAILABLE` usa 5 minutos até 5.000 objetos pendentes, 10 minutos até 50.000 e 30 minutos acima disso; `AFTER_ALL_RESTORED` preserva 30 minutos. Por wave, o Raijin persiste quantidade/duração de consultas `HeadObject`, throttles observados e a medição do último ciclo; esses dados aparecem na fila e no relatório.
- Cada wave e cada source possuem uma estimativa de custo sob demanda. Ela calcula jobs/tarefas Batch, manifests, requests de discovery/polling/leitura, retrieval por classe e tier, retenção temporária, saída AWS, operações multipart OCI e armazenamento mensal. A plataforma coleta as AWS Price Lists públicas regionais de Amazon S3 e AWS Data Transfer sem usar credenciais, por padrão a cada sete dias e também sob comando manual; a saída AWS→OCI usa apenas a entrada regional `AWS Outbound` → `External`. Os valores mostrados ao operador preservam a unidade publicada no Price List (GB decimal, 1.000 requests e 1.000.000 de objetos Batch); conversões para GiB e unidade são internas ao cálculo e não alteram o valor apresentado. Para cada campo, uma tarifa contratual da conexão substitui a tarifa pública; campos OCI permanecem configuráveis por conexão. Uma tarifa ausente torna o componente e o total correspondente explicitamente não estimados, em vez de assumir preço zero. No modo Simulation a mesma estimativa AWS usa o catálogo público regional e as unidades/counters virtuais, sem credenciais ou chamadas operacionais às contas cloud.
- O manifesto CSV gerado para Batch Operations usa estritamente os campos AWS `Bucket`, `Key` e, quando necessário, `VersionId`; as chaves são URL-encoded antes de serem gravadas.
- Os clientes AWS têm timeout explícito de conexão (10 segundos), leitura (120 segundos) e até quatro tentativas padrão do SDK. Depois disso, a tarefa durável entra em retry e preserva o checkpoint multipart OCI; uma conexão de rede travada não deve ocupar indefinidamente o único worker real.
- A chave do S3 é preservada no OCI. Metadados e tags são preservados no destino quando compatíveis e sempre no manifesto imutável da migração.

## Dimensionamento inicial

Para o caso inicial de 600 TB, ondas de 10 TB e rota de 1,2 Gbps:

| Recurso | Recomendação |
| --- | --- |
| Shape | VM.Standard.E5.Flex, ou flex x86 equivalente disponível |
| CPU | 8 OCPUs em produção; 2 OCPUs na validação inicial de 220 MB |
| Memória | 32 GB em produção; 8 GB na validação inicial de 220 MB |
| Boot volume | 500 GB |
| Raijus iniciais | 5 |

Em 1,2 Gbps, 10 TB levam cerca de 18,5 h no limite teórico; planeje 22–30 h. A retenção padrão de restore deve ser 4 dias.

O tamanho mínimo de laboratório é 2 OCPUs/8 GB. Ele suporta PostgreSQL, a interface e poucos workers para validar o fluxo, mas não é indicado para ondas de 10 TB nem para usar todo o link de 1,2 Gbps.

## Recuperação

PostgreSQL, backups lógicos locais, WAL, logs e releases residem no boot volume persistente. Uma policy automática de backup do boot volume deve ser associada à VM, com retenção padrão de 35 dias para cobrir a quarentena do simulador. Backup local acelera restauração, mas o backup do volume protege contra perda da VM ou do disco.

O `user_data` do cloud-init é intencionalmente ignorado em atualizações Terraform: ele só executa no primeiro boot. Uma atualização de release nunca pode substituir uma VM que contém o banco de controle.
