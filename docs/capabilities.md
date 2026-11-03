# Capacidades do [RAIJIN](https://en.wikipedia.org/wiki/Raijin)

Este é o inventário vivo dos dois programas que compõem a plataforma. Toda
entrega que acrescente, remova ou altere um fluxo operacional deve atualizar
este documento no mesmo commit.

O inventário descreve somente comportamento implementado e validado. Planos
futuros permanecem em `operacional/` e não devem ser promovidos a capacidade
até terem código, testes e evidência operacional. A revisão de uma mudança de
produto deve atualizar esta página, o guia de deploy quando houver impacto no
host/runtime e o runbook de recuperação quando houver impacto em dados ou
retomada.

## [RAIJIN](https://en.wikipedia.org/wiki/Raijin) — plano de controle de migração

<img src="../images/raijin-oracle-about.png" alt="Logo do RAIJIN" width="280">

O RAIJIN é o programa que inventaria fontes, planeja waves, governa restores,
coordena workers, transfere objetos, registra evidências e apresenta a console
operacional. Ele opera com integrações reais ou, quando explicitamente iniciado
no modo isolado, delega as integrações antigas ao SEPARADO.

### O que o RAIJIN faz

### Fontes, conexões e inventário

- Cadastra múltiplas conexões AWS, inclusive para contas diferentes, usando
  Secrets OCI com JSON versionado e um rótulo local imutável.
- Vincula várias fontes S3 a uma conexão AWS; cada conexão usa seu bucket de
  controle e prefixos gerados pelo RAIJIN para não misturar manifestos.
- Permite vários prefixes independentes em uma única source, mas impede que
  fontes ativas do mesmo bucket tenham escopos iguais ou sobrepostos. A regra
  usa a semântica literal do S3 (`app/` também cobre `app/images/`) e evita
  discovery, restore e transferência duplicados. Sources desativadas não
  bloqueiam um novo cadastro.
- Desativa uma source com histórico sem apagar suas evidências. A desativação
  cancela trabalho pendente, mantém a source fora dos schedulers e bloqueia
  ações mutáveis, mas ela continua no combobox do projeto para consulta de
  inventário, waves, eventos e relatórios. O nome recebe o marcador `⏸️`; a
  tag à direita continua exibindo o status global real da migração, sem
  confundir ciclo de vida com progresso operacional. Registros que versões
  anteriores chamavam de arquivados são apresentados automaticamente nesse
  mesmo padrão.
- Congela para cada objeto/revisão a chave de destino OCI resolvida no
  discovery. A rota padrão permanece compatível (`chave OCI = chave S3`), mas
  a transferência, multipart, validação e auditoria usam a chave persistida,
  não uma configuração de source recalculada durante retry. A API permite
  cadastrar explicitamente um projeto de migração e associar uma source ainda
  sem inventário ou wave, com prefixo OCI não vazio e sem colisão de rota no
  mesmo bucket, inclusive com fontes de outro projeto ou fontes legadas
  ativas. A criação de source exige um projeto ativo tanto na API quanto na
  interface; sem essa seleção o controle permanece desativado. Sources
  históricas também podem ser vinculadas administrativamente a um projeto sem
  reescrever bucket, prefixo, `destination_object_key`, waves ou evidências; o
  vínculo apenas completa o contexto de projeto da source e da fila durável.
  Na console, o projeto selecionado é o contexto de navegação da área de
  sources: o combobox lista somente as sources vinculadas a ele e fica
  indisponível enquanto nenhum projeto estiver ativo. A troca de projeto
  também remove da tela qualquer source que não pertença ao novo contexto. Na
  fila operacional, o seletor de projeto e a ação **Waves timeline** formam um
  único grupo alinhado à direita, com a timeline imediatamente à direita do
  seletor. A seleção também é persistida no parâmetro `project` da URL: links
  compartilhados e recarregamentos restauram o mesmo contexto, enquanto uma
  seleção inexistente ou arquivada é descartada com segurança.
  Projeto, métricas agregadas e controles de source ocupam um único card; o
  resumo não repete uma lista estática das sources, pois o próprio combobox
  filtrado é a referência operacional do vínculo ativo. A exportação CSV
  consolidada do projeto fica junto da consulta de objetos, dentro do modal
  aberto pela ação **Objetos** da source selecionada. O resumo diferencia o
  inventário agregado do progresso entregue: arquivos transferidos sobre o
  total descoberto e bytes transferidos sobre o tamanho total descoberto,
  acompanhados de ajuda contextual sobre origem e abrangência das métricas.
  Os valores principais de inventário e entrega usam branco e escala ampliada
  para leitura rápida; o custo acumulado também usa branco, preservando
  sua escala própria para evitar estouro horizontal. O card de inventário tem
  largura prioritária e seus valores não quebram linha.
  O mesmo resumo mostra as quantidades agregadas de sources e waves, apresenta
  o estado em texto amplo sobre um card com cor semântica, sem usar vermelho
  para lifecycle, e oferece uma matriz explicativa de todos os estados na
  tooltip. Essa ajuda usa uma camada própria, imune à normalização visual dos
  cards operacionais, e é reconstruída no carregamento, na interação e na
  troca de idioma, com uma tag colorida e descrição alinhada para cada estado.
  Inventário e entregues dividem internamente arquivos e volume com
  valores grandes, separador visual e unidade comum para comparação direta; o
  inventário também informa o tempo agregado de discovery em seu rodapé, sem
  repetir essa duração abaixo dos cards. O card de entregues apresenta ainda
  o percentual concluído de arquivos e de volume como primeiro valor, acima
  da quantidade entregue e do respectivo total descoberto.
  Estado, sources, waves e custo mantêm seu valor principal centralizado nos
  dois eixos, independentemente de cabeçalho ou rodapé; o tempo de discovery
  fica centralizado no rodapé do inventário. O custo one-time acumulado de
  todas as waves de todas as sources do projeto é formatado em USD com duas
  casas decimais. Os seis cards têm altura uniforme, distribuem-se por toda a
  largura útil sem espaços reservados e reorganizam-se responsivamente em três,
  duas ou uma coluna.
  A associação pode ser desfeita apenas antes dessa fronteira operacional; a
  rota histórica permanece imutável. O namespace OCI continua pertencendo ao
  runtime/tenancy, não ao projeto. Cada projeto possui resumo consolidado,
  inventário CSV e custos calculados como soma explícita das waves, mantendo
  o drill-down de source, bucket e região. As APIs preservam as operações de
  pausar ou retomar todas as waves ativas de um projeto, mas esses controles,
  a timeline consolidada e os grupos de waves não são exibidos no painel de
  projeto. O arquivamento exige ausência de trabalho ativo e preserva toda a
  evidência. A conclusão consolidada não depende apenas
  de waves terminais: cada source precisa ter todos os objetos atuais entregues
  com integridade OCI aceita (ou verificação profunda concluída). Divergência
  de destino, falha, integridade pendente ou auditoria profunda em fila deixam
  o projeto como `COMPLETED_WITH_ATTENTION`, com os bloqueios discriminados por
  source.
  Um projeto cujas sources ainda estão apenas cadastradas permanece em
  `CONFIGURED`: a ausência esperada de inventário antes do primeiro discovery
  não é tratada como conclusão com ressalvas. `COMPLETED_WITH_ATTENTION` fica
  reservado para pendências de uma execução que já cruzou a fronteira
  operacional.
- Descobre objetos por API S3 paginada, com checkpoint, retomada, limitação de
  requisições por conexão e acompanhamento em fila durável.
- Importa CSV/GZIP ou `manifest.json` do S3 Inventory para evitar chamadas de
  API em inventários grandes.
- Executa re-discovery controlado, com justificativa obrigatória, sem apagar
  inventário ou evidências de migração existentes.
- Identifica objetos novos e alterações de tamanho, ETag, versão ou última
  modificação quando esses campos estiverem disponíveis no inventário.
- Preserva a origem do discovery: API remota, S3 Inventory ou arquivo enviado.

### Waves, restore e transferência

- Cria waves manualmente por volume, em massa por limite de tamanho ou por
  prefixo; uma wave nunca excede 10 TB.
- Cria waves dinâmicas de forma adaptativa: a retenção define a janela útil de
  cópia, a reserva operacional protege a expiração e cada próxima wave é
  empacotada com previsão por objeto e histórico real de transferência.
- Submete restores arquivados por S3 Batch Operations, com manifesto e relatório
  de conclusão persistidos no bucket de controle.
- Registra tentativa, aceite AWS, Batch job, polling, disponibilidade parcial e
  disponibilidade completa do restore.
- Depois da evidência Batch, consulta individualmente com `HeadObject` somente
  os objetos arquivados ainda pendentes. O cabeçalho `x-amz-restore` é a fonte
  de verdade para `ongoing-request` e para a expiração individual da cópia
  temporária; não usa SQS, EventBridge nem polling por listagem ampla.
- Persiste `restore_expires_at` por objeto. A expiração nunca é inferida pela
  hora estimada de restore: ela vem da resposta observada do S3 e alimenta a
  priorização, o risco de expiração e o relatório da wave.
- Importa a evidência individual do completion report e apresenta no relatório
  da wave o código HTTP/AWS, a quantidade afetada, chaves de exemplo, causa e
  ação recomendada. `RestoreAlreadyInProgress` é reconhecido como aceite
  equivalente, sem criar um restore duplicado.
- Cada wave define sua política de liberação: iniciar a cópia após todos os
  objetos restaurados ou liberar cada objeto assim que sua disponibilidade é
  observada. Waves dinâmicas usam obrigatoriamente a liberação imediata.
- Opera uma **fila contínua de transferência** por source: a wave mantém as
  fronteiras de restore, custo e auditoria, mas não monopoliza os Raiju. Um
  objeto disponível de outra wave pode ser copiado assim que se torna mais
  urgente ou necessário para manter a lane ocupada.
- Quando há sources de projetos distintos, a **admissão da lane física é
  global**: o Raikou escolhe a próxima source por risco de expiração,
  prioridade, elegibilidade e espera, registra os candidatos e concede todo o
  orçamento de rede a um único dispatcher ativo. Ao surgir trabalho em outra
  source, o dispatcher atual conclui apenas os objetos já admitidos e devolve
  a decisão ao coordenador; nenhum stream ou multipart é interrompido. Os
  slots de restore também respeitam o teto global do runtime, sem misturar
  manifestos, Batch Jobs ou polling de waves.
- Em empate de prioridade e expiração, o coordenador usa a última seleção
  durável de cada projeto para favorecer o que recebeu a lane há mais tempo.
  Essa fairness nunca supera risco de expiração ou prioridade e não interrompe
  um objeto/multipart já admitido.
- O operador configura globalmente o estoque mínimo, alvo e máximo da lane
  (padrões de 3h, 6h e 24h), os lotes normais (100 objetos ou 1 GiB) e os
  micro-lotes críticos (20 objetos ou 256 MiB). O Raikou usa esses limites
  para antecipar restores sem abrir janelas temporárias em excesso.
- Uma wave pode permanecer em **RESTORING** enquanto seus objetos disponíveis
  são drenados. Não existe limiar percentual de liberação: o Raikou usa o
  estoque real de trabalho com reserva mínima de 3 h, alvo de 6 h e máximo de
  24 h para alimentar a lane sem antecipar cópias restauradas sem necessidade.
- O scheduler mantém inicialmente dois restores concorrentes e uma terceira
  wave futura replanejável; com histórico suficiente, pode ampliar restores
  até o teto global configurado de quatro. Um slot de restore é liberado assim
  que a wave fica 100% disponível, mesmo que seus objetos ainda estejam na lane.
- O Raikou prioriza objetos já legíveis por expiração, duração prevista,
  viabilidade dentro da janela, tamanho e proteção contra starvation. Lotes
  normais têm até 100 objetos ou 1 GiB; urgências críticas usam micro-lotes de
  até 20 objetos ou 256 MiB. Em urgência crítica, o Raikou reserva o próximo
  slot seguro para o item crítico e o Raiju selecionado conclui o **objeto
  atual** antes do handoff; nunca há interrupção de streaming ou de multipart
  em andamento. Reserva, sucessor, motivo e execução do handoff são duráveis
  e auditáveis. Cada lote de despacho, prioridade, capacidade Raiju e intervalo
  executado também ficam persistidos. A cada vaga Raiju liberada, a prioridade
  e a capacidade são recalculadas e a parcela livre do limite de throughput é
  distribuída sem interromper I/O em curso. A admissão, a atualização de
  prioridade, o claim e a recuperação de leases usam páginas delimitadas, para
  que uma source com milhões de objetos não seja carregada integralmente em
  memória. Somente waves sem submissão AWS podem ser
  reempacotadas ou ter horários alterados; Batch Jobs aceitos permanecem como
  evidência e não são recriados automaticamente.
- A transferência inicia no piso de cinco **Raijus** e, após restart ou nova
  lane, limita o bootstrap ao menor coorte produtivo conhecido (oito por
  padrão). O autoscaler usa taxa **agregada** em janelas de 20 s: só testa mais
  um Raiju depois de 12 amostras abaixo de 90% do alvo, espera um minuto de
  acomodação e exige outras 12 janelas para validar ganho sustentado. O ruído
  robusto é calculado dentro de cada coorte, sem confundir a mudança de nível
  entre baseline e experimento com jitter. Em 90% ou mais a lane cumpre a meta
  operacional: mantém os streams produtivos, mas não adiciona pressão apenas
  para perseguir os últimos pontos percentuais do limite. Tetos
  de host, memória e pool PostgreSQL são limites de admissão, não metas.
  Trocas parciais de objetos contam somente bytes do coorte comparável; uma
  troca integral renova a baseline sem fabricar taxa. A UI distingue o horário
  da última amostra real do horário da última atualização do controlador e
  mostra separadamente o limite configurado e o teto efetivo P95 das seis
  horas recentes. Esse teto só governa decisões após ao menos 180 medições e
  quando já comprova 85% do contrato; uma lane degradada não pode redefinir
  baixa utilização como sucesso. Uma experiência sem ganho volta ao último
  coorte aprovado; depois de seis horas, 12 amostras novas ainda abaixo de 90% autorizam uma
  única rechecagem serial, evitando tanto bloqueio eterno quanto crescimento
  oscilante.
- O reforecast das waves futuras usa a capacidade histórica da lane. Uma taxa
  degradada recente só substitui essa referência após confirmação em duas
  janelas independentes de bytes agregados. Valores repetidos apenas para
  telemetria de um despacho não são nova evidência e não movem o calendário.
  Essa contenção não atrasa prioridades e retries por expiração, que continuam
  decididos diretamente pela fila viva. Uma wave dinâmica ainda não submetida
  nunca conserva um início de transferência impossível: o plano a reposiciona
  para, no mínimo, a janela pública do tier somada à margem de segurança a
  partir da nova decisão; a submissão AWS continua sendo uma tarefa durável e
  separada, governada por slots e pelo estoque da lane.
- O reforecast de calendário persiste somente deslocamentos de pelo menos 15
  minutos ou 5% da duração prevista, o que for maior. Eventos repetidos são
  coalescidos por uma hora; deadlines monotônicos, submissões AWS e evidências
  observadas continuam imutáveis.
- APIs, timeline e relatórios distinguem o tempo de serviço exclusivo previsto
  para a wave (`predicted_transfer_service_seconds`) do tempo de calendário
  observado enquanto ela compartilha a lane
  (`transfer_calendar_elapsed_seconds`). A capacidade aprendida continua sendo
  source-wide e usa a união de segmentos, sem somar trabalho paralelo.
- Cada wave dinâmica também persiste o seu **último prazo seguro de submissão
  AWS**, calculado pela janela pública completa do tier mais a margem
  operacional. Esse prazo só pode avançar (nunca ser postergado por um
  reforecast). Quando vence e a primeira disponibilidade projetada deixaria a
  lane abaixo do mínimo saudável, a liberação da wave prevalece sobre o teto
  heurístico de estoque; se todos os slots físicos estiverem ocupados, o
  Raikou registra explicitamente o risco de continuidade em vez de ocultar o
  atraso. Cada violação gera uma evidência única e também aparece no card de
  observabilidade, nos detalhes sob demanda e na métrica Prometheus
  `raijin_restore_submission_deadline_missed_waves`. Essa regra usa somente o
  contrato AWS conhecido pelo Raijin, nunca tempos internos do separado.
- A tarefa durável da lane contínua pode manter uma wave como âncora histórica,
  mas é reancorada automaticamente para a próxima wave com backlog quando a
  anterior conclui. Assim a console não mostra trabalho vivo em uma wave
  concluída e a cópia de outra wave da mesma source nunca é interrompida.
- O **Raikō** é dividido em quatro processos duráveis e independentes:
  **Raikō::Shin** (Controller) serializa planejamento, liberação e
  reconciliação global; **Raikō::Sei** (Restore) submete Batch Operations e
  executa polling; **Raikō::Kō** (Discovery) executa descobertas com checkpoint;
  e **Raikō::Kai** (Audit) executa auditorias profundas. Eles compartilham a
  fila PostgreSQL, mas cada papel só assume sua responsabilidade. Portanto uma
  auditoria longa não bloqueia submissão nem polling de restore. O **Raiju** é
  o worker operacional de transferência e retomada multipart.
- Copia S3 para OCI preservando chave, tamanho, metadados compatíveis e tags
  registradas localmente.
- Retoma uploads multipart interrompidos usando checkpoints persistidos de
  `upload_id` e partes já aceitas pelo OCI.
- A validação técnica multi-source inclui rotas com a mesma key original,
  reutilização de conexão entre regiões, teto global de restores, vencedor
  único da lane, fairness durável e recuperação do lifecycle após reabertura
  do banco. A rota OCI imutável é resolvida antes da persistência em todos os
  produtores iniciais de inventário: listagem remota, manifesto S3, importação
  API e upload CSV/CSV.GZ; inserções em lote não dependem de default do ORM.
- Releases da VM usam imagem imutável identificada pelo hash do build. O
  rollout e o bootstrap conferem a revisão reportada pela API, evitando que
  cache de construção ou uma tag reaproveitada mascare código antigo.

## Referências relacionadas

- A fila de Deep Audit prioriza visualmente a wave em processamento e mantém seus indicadores sempre abertos. As waves aguardando e os resultados concluídos permanecem compactos e expansíveis, ordenados respectivamente pela posição da fila e pela conclusão mais recente; cada linha identifica o projeto e a wave sem depender do nome da source.
- O projeto selecionado também define o escopo de leitura da tela **Queue**: filas de restore/transferência, Deep Audit e discovery, além das tarefas e atividades recentes, exibem somente waves e sources pertencentes ao projeto. A seleção é um filtro operacional de leitura; a lane física e seus schedulers continuam globais.
- O readiness usa o mesmo projeto selecionado e valida somente suas sources ativas, conexões AWS referenciadas e buckets OCI de destino. Sources desativadas ou pertencentes a outro projeto não geram falso alerta no contexto atual.
- A auditoria separado continua estritamente sob demanda. A interface pagina com uma linha sentinela, sem executar `COUNT(*)` integral a cada página; índices compostos por bucket/objeto, data e id sustentam buscas temporais sobre históricos grandes.

- [Arquitetura](architecture.md)
- [Conexões AWS](aws-connections.md)
- [Estimativas de custo](cost-estimates.md)
- [Deploy e instalação](deployment.md)
- [Pacote de encerramento](project-closure-package.md)
- [Recuperação](recovery-runbook.md)
- [Plano de validação](validation-test-plan.md)
