# Plano — payloads locais reais no Fujin

**Status:** PLANEJADO — implementação não iniciada
**Referência:** proposta de dataset local para validar o caminho de dados do Fujin sem AWS/OCI reais, registrada em 2026-09-02.
**Dependência externa:** a validação representativa de 100 TB lógicos exige capacidade física a ser solicitada oportunamente; as fases de produto não dependem dessa capacidade para começar.

## Objetivo

Permitir que o Fujin exponha, para uma execução `DATA` explicitamente configurada, bytes de arquivos existentes em um diretório local controlado. O catálogo, o relógio virtual, as regras de restore, expiração e os jobs continuam no PostgreSQL do Fujin. Assim, o Raijin exercita transferência, multipart, checksum e retomada com bytes reais, sem chamada à AWS ou à OCI.

O modo atual, que gera bytes determinísticos a partir do catálogo, permanece o padrão e não pode mudar de comportamento.

## Linha de base técnica

- `VirtualObject` já separa metadados e identidade lógica de conteúdo (`content_seed`, `content_object_id`, `source_sha256`).
- `SimulationEngine.read_range()` produz os bytes determinísticos para a faixa solicitada; os endpoints `/v1/cloud/source/read-range` e `/v1/cloud/destination/read-range` apenas os transmitem.
- O destino simulado hoje consome o upload e persiste evidência de tamanho/checksum; ele não guarda o payload recebido.
- Restore e expiração são predicados do catálogo. Portanto, um arquivo local pode continuar “arquivado” até a disponibilidade virtual, sem mover nem duplicar o arquivo no disco.
- O Fujin não é, hoje, um emulador genérico de toda a API S3: ele implementa o contrato versionado consumido pelos ports simulados do Raijin. O recurso deve preservar esse contrato.

## Decisões consolidadas

1. Expor três modelos de massa na criação da execução. O modo de payload continua registrado por objeto, mas o modelo explica ao operador como o catálogo inteiro será composto:

   - **Catálogo virtual** (`VIRTUAL`) — modelo atual: todos os objetos usam payload determinístico. É apropriado para escala lógica, planejamento e testes de controle; não exige arquivos no disco.
   - **Amostra real compartilhada** (`REPRESENTATIVE`) — o catálogo pode ter muitos objetos, mas eles referenciam, de forma declarada, um conjunto pequeno de arquivos reais. Exercita leitura, multipart, checksum e retry com I/O real sem exigir o volume lógico no disco.
   - **Execução híbrida** (`HYBRID`) — waves ou faixas de waves explicitamente selecionadas usam arquivos reais; as demais preservam payload determinístico. É o modelo recomendado para validar uma migração grande com uma amostra física representativa.

   No nível do objeto, `DETERMINISTIC` permanece o padrão atual e `LOCAL_FILE` identifica a referência a um arquivo do dataset local imutável.

2. O diretório não é uma entrada de caminho arbitrário fornecida pelo navegador ou pelo Raijin. O operador cadastra previamente um **dataset local** por configuração administrativa; a execução referencia seu identificador.

3. O Fujin só recebe um bind mount de leitura, por exemplo `/fujin-data`, no container do simulador. Nenhum caminho absoluto do host é armazenado nem devolvido pela API.

4. A primeira entrega cobre **fonte local real**. Persistir bytes de destino em filesystem é uma extensão opcional posterior; não será misturada ao objetivo de validar a leitura e transferência de uma fonte real.

5. Um dataset é transformado em snapshot no momento da importação/materialização. Arquivos alterados, removidos ou substituídos depois disso devem falhar de modo explícito, nunca serem lidos silenciosamente como se fossem o snapshot original.

### Acordos aprovados antes da implementação — 2026-09-03

| # | Decisão aprovada | Registro objetivo |
|---:|---|---|
| 1 | Escopo físico inicial | Somente fonte física local; destino simulado continua consumindo bytes e persistindo evidências. |
| 2 | Modelos de massa | `VIRTUAL`, `REPRESENTATIVE` e `HYBRID`, disponíveis somente em `DATA`. |
| 3 | Composição híbrida | Waves/faixas físicas são escolhidas explicitamente, de forma determinística e persistida no snapshot. |
| 4 | Amostra compartilhada | A associação objeto lógico → arquivo físico é determinística e reportada. |
| 5 | Integridade do dataset | Snapshot imutável; qualquer divergência de arquivo falha de forma auditável. |
| 6 | Posse do repositório | O repositório é criado, lido, versionado e removido exclusivamente pelo Fujin. |
| 7 | Origem do conteúdo | Primeira versão gera arquivos internamente; importação externa fica fora do escopo. |
| 8 | Quota e lifecycle | Dataset recebe quota congelada, retenção, quarentena e limpeza apenas sem referências. |
| 9 | Checksum | SHA-256 é calculado durante a geração e gravado no manifesto. |
| 10 | Restore | Existência física não implica disponibilidade: classe, restore e expiração continuam lógicos. |
| 11 | Perfil de massa | Histograma, prefixes, classes e multipart são versionados por perfil e seed. |
| 12 | Momento de geração | Dataset é gerado e validado antes da execução; geração não compete com a transferência. |
| 13 | Reuso | Datasets imutáveis são reutilizados por referência entre cenários e replays. |
| 14 | Volume | Repositório vive em volume persistente dedicado, separado de banco, logs e releases. |
| 15 | Relógio | Transferência física usa duração observada; relógio virtual não ultrapassa trabalho físico pendente. |
| 16 | Rede | Perfil de rede do Fujin limita o stream; disco e link são medidos separadamente. |
| 17 | Cache | Execuções identificam explicitamente `cold start` ou `warm cache`; Fujin não limpa cache do host. |
| 18 | Falhas | Corrupção/retry/falhas são injetados no stream/operação, nunca alterando arquivos persistidos. |
| 19 | Interface | Operador solicita ações de alto nível; não há path, browser, upload ou download direto de arquivos. |
| 20 | Geração | Geração, hashing e validação são jobs duráveis, retomáveis; só dataset `READY` pode ser usado. |
| 21 | Bytes | Conteúdo padrão tem alta entropia, não é sparse e ocupa o tamanho físico declarado. |
| 22 | Layout interno | Arquivos são shardados por dataset/hash; chave S3 permanece independente no catálogo. |
| 23 | Storage class | Perfil declara mistura de classes e tiers `BULK`/`STANDARD`; não pressupõe restore para todos os objetos. |
| 24 | Topologia | Prefixes/prioridades e amostra física são distribuídos pelo pipeline, não concentrados em uma wave. |
| 25 | Recursos | Limites de leitura, descritores, bloco, CPU de hash e taxa local são congelados por cenário. |
| 26 | Evidência | Relatório de fidelidade física é obrigatório e registra configuração, métricas e divergências. |
| 27 | Aprovação | Baseline versionada usa faixas; integridade e snapshot exigem zero divergência. |
| 28 | Recuperação | Dataset é recriável por manifesto, seed e gerador; backup de volume é complementar. |
| 29 | Importação externa | Não integra a primeira versão; futura importação será iniciativa controlada e separada. |
| 30 | Isolamento real | Volume só é montado no Fujin; `REAL` rejeita qualquer payload local. |
| 31 | Destino físico | Não haverá persistência física no destino por ora; eventual extensão terá volume independente. |

## Modelo de dados e migração

1. Adicionar uma migração de schema do simulador.

2. Criar `sim_payload_datasets` com, no mínimo:

   - `id`, `name` único, `mount_root`, `state` (`ACTIVE`, `RETIRED`);
   - política de inclusão/exclusão de paths;
   - data de criação, origem administrativa e versão do importador;
   - contagem, bytes e fingerprint do snapshot.

3. Adicionar a `VirtualObject` campos compatíveis com o legado:

   - `payload_kind` (`DETERMINISTIC` por default);
   - `payload_dataset_id` opcional;
   - `payload_relative_path` opcional;
   - `payload_size_bytes`, `payload_mtime_ns` e identificador de arquivo observados no snapshot;
   - `payload_sha256` opcional, preenchido por auditoria de importação ou calculado sob demanda e persistido como evidência.

4. Guardar somente caminho relativo normalizado em relação ao root do dataset. Proibir `..`, path absoluto, NUL e links simbólicos. Não expor `mount_root` nas respostas operacionais.

5. Manter `size_bytes` igual ao tamanho real para objetos `LOCAL_FILE`. Isso evita que `HEAD`, `Content-Length`, multipart e checksum tenham semântica ambígua.

6. Atualizar o relatório/snapshot de execução com o ID, fingerprint e versão do dataset. Clone/replay deve manter a referência ao snapshot ou rejeitar o clone se ele não existir mais.

## Abstração de payload

1. Introduzir no Fujin uma porta estreita, por exemplo `SourcePayloadReader`:

   - `stat(object) -> PayloadStat`;
   - `stream_range(object, offset, length) -> Iterator[bytes]`;
   - `fingerprint(object) -> PayloadFingerprint`.

2. Implementações:

   - `DeterministicPayloadReader`, adaptando `iter_deterministic_range` atual;
   - `LocalFilesystemPayloadReader`, com leitura em blocos, `seek` por offset e fechamento garantido do arquivo.

3. O `SimulationEngine` escolhe o reader pela linha de `VirtualObject`; os endpoints HTTP e os ports do Raijin continuam inalterados.

4. Não criar ainda uma interface ampla `put/copy/delete` se não houver um caso de uso real no destino. Quando o Fujin passar a persistir destino físico, criar uma porta separada (`DestinationPayloadStore`) e diretório de escrita próprio; nunca reutilizar o root de origem.

## Importação e materialização do dataset

1. Criar API administrativa autenticada para cadastrar, validar e importar um dataset. A API recebe o ID do dataset e filtros permitidos, não caminhos do host.

2. Percorrer o diretório com `os.scandir`/`Path` de forma incremental e em lotes, produzindo:

   - chave S3 a partir do path relativo POSIX;
   - tamanho, data de modificação, classe de storage e metadados opcionais;
   - referência ao dataset/arquivo para `LOCAL_FILE`.

3. Definir colisões de chave, arquivos vazios, permissões insuficientes e arquivos que mudam durante o scan como erros auditáveis de importação.

4. Oferecer os três modelos claros na interface administrativa:

   - **Catálogo virtual**: comportamento atual, adequado para milhões de objetos sem arquivos físicos;
   - **Amostra real compartilhada**: selecionar dataset e política determinística de associação dos objetos aos arquivos da amostra;
   - **Execução híbrida**: selecionar dataset e quais waves/faixas de waves terão payload físico.

5. Não apresentar “1 milhão de objetos usam 100 arquivos” como equivalente a um milhão de arquivos reais. No modelo de amostra compartilhada, a reutilização deve constar no relatório; tamanho e checksum de cada objeto lógico precisam ser compatíveis com o arquivo físico selecionado.

## Semântica de S3/Glacier simulada

1. `list_objects` e `head_object` usam o catálogo, como hoje.

2. `read_range` primeiro aplica exatamente as regras atuais de restore/expiração; apenas depois abre o arquivo local. Um objeto `DEEP_ARCHIVE` local continua indisponível enquanto `ARCHIVED` e volta a falhar ao expirar.

3. A leitura deve validar offset/length contra o snapshot e contra o `stat` atual antes de emitir bytes. Divergência de tamanho, mtime ou identidade deve produzir erro específico de snapshot inválido.

4. O checksum de origem para um arquivo real é SHA-256 do arquivo completo. Para evitar atrasar a primeira transferência, permitir cálculo streaming sob demanda, com exclusão mútua e persistência da evidência; disponibilizar também pré-cálculo administrativo.

5. Falhas injetadas (rede, corrupção, retry) continuam ocorrendo acima do reader, para funcionarem igualmente com payload determinístico e local.

## Segurança e operação

1. Montar o dataset no container do Fujin como `read-only`; rodar o processo com usuário sem escrita nesse mount.

2. Restringir roots aceitos a uma allowlist do deployment. Resolver e validar paths no momento do import e da leitura; recusar symlinks e qualquer escape do root.

3. Limitar quantidade de arquivos abertos, tamanho de bloco e concorrência de hashing para não exaurir descritores, cache ou disco da VM.

4. Registrar em auditoria: dataset, objeto lógico, path relativo mascarado quando necessário, fingerprint esperado/observado, leitor selecionado e falhas de snapshot.

5. Documentar backup, retenção e remoção: purgar cenário remove apenas catálogo/evidência, nunca arquivos do dataset; remover um dataset exige checar referências ativas.

## Interface e contratos

1. Estender handshake do simulador com capability nova, por exemplo `local-filesystem-source-payload-v1`.

2. Na tela Simulation, adicionar uma seção administrativa de datasets: estado do mount, root lógico, contagem, bytes, último scan, fingerprint e botão de importação/validação.

3. Na criação/materialização de cenário `DATA`, permitir selecionar **Catálogo virtual**, **Amostra real compartilhada** ou **Execução híbrida**. Exibir para os dois últimos o tamanho físico da amostra, as waves físicas e lógicas e que AWS/OCI continuam isoladas, embora haja I/O local real.

4. Incluir no report de execução: tipo de payload, dataset/snapshot, bytes físicos lidos, checksum e qualquer divergência detectada.

5. Não expor a opção em `CONTROL`, pois esse modo existe para simulação lógica sem tráfego de payload.

## Fase 1 — fundação compatível e contratos versionados

**Marco:** o Fujin reconhece datasets e tipos de payload sem alterar qualquer cenário determinístico existente.

- [ ] Criar migração para dataset, referência física e fingerprint do snapshot em `VirtualObject`.
- [ ] Manter `DETERMINISTIC` como default compatível para todos os objetos e cenários legados.
- [ ] Registrar a capability `local-filesystem-source-payload-v1` no handshake versionado.
- [ ] Congelar no snapshot da execução o modelo de massa, dataset e versão do importador.
- [ ] Preparar configuração de allowlist e bind mount read-only, sem ainda permitir leitura pelo engine.

**Critérios de aceite**

- [ ] Cenários `CONTROL` e `DATA` determinísticos passam sem alteração de resultado.
- [ ] Uma execução sem dataset não cria referência a path local nem requer novo recurso externo.
- [ ] O handshake recusa combinação de versões incompatíveis.

## Fase 2 — leitura local segura e semântica de restore

**Marco:** um objeto `LOCAL_FILE` pode ser lido por faixa com os mesmos controles de restore e expiração do objeto virtual.

- [ ] Implementar `SourcePayloadReader`, `DeterministicPayloadReader` e `LocalFilesystemPayloadReader`.
- [ ] Validar path relativo, root permitido, ausência de symlink, identidade/tamanho/mtime do snapshot e limites de offset/length.
- [ ] Fazer `read_range` aplicar restore/expiração antes de abrir o arquivo local.
- [ ] Implementar SHA-256 streaming sob demanda, com persistência de evidência e controle de concorrência.
- [ ] Preservar a injeção de falhas acima do reader para os dois tipos de payload.

**Critérios de aceite**

- [ ] Range e `Content-Length` retornam exatamente os bytes esperados, inclusive em EOF e multipart.
- [ ] Arquivo local permanece indisponível em `ARCHIVED` e volta a falhar após expiração.
- [ ] Alteração, remoção, symlink ou escape de root falha de forma explícita e auditável.

## Fase 3 — importação e composição dos três modelos de massa

**Marco:** o operador compõe uma execução de forma reprodutível como Catálogo virtual, Amostra real compartilhada ou Execução híbrida.

- [ ] Criar cadastro administrativo de dataset sem aceitar paths do host pela interface ou pelo Raijin.
- [ ] Implementar scan incremental/idempotente, com chaves relativas POSIX, metadados e relatório de colisões/erros.
- [ ] Implementar **Catálogo virtual** (`VIRTUAL`) como comportamento atual.
- [ ] Implementar **Amostra real compartilhada** (`REPRESENTATIVE`) com associação determinística e evidência de reutilização.
- [ ] Implementar **Execução híbrida** (`HYBRID`) com seleção versionada de waves/faixas físicas e lógicas.
- [ ] Impedir incompatibilidade de tamanho/checksum entre objeto lógico e arquivo físico associado.

**Critérios de aceite**

- [ ] O mesmo template e dataset produzem a mesma composição ao clonar/reexecutar o cenário.
- [ ] O relatório diferencia bytes lógicos, bytes físicos únicos e bytes físicos efetivamente lidos.
- [ ] A reutilização representativa nunca é apresentada como arquivo físico único por objeto.

## Fase 4 — engine, interface e observabilidade

**Marco:** o modelo selecionado é visível e o resultado permite interpretar a fidelidade física da execução.

- [ ] Integrar a seleção do reader ao `SimulationEngine` sem mudar os ports HTTP usados pelo Raijin.
- [ ] Exibir datasets, fingerprint, mount lógico, estado de validação e último scan na console Simulation.
- [ ] Exibir os três modelos apenas para `DATA`; manter `CONTROL` estritamente lógico.
- [ ] Incluir no report tipo de payload, dataset/snapshot, arquivos por faixa, bytes físicos, checksum e divergências.
- [ ] Coletar taxa de leitura, uso de link, cache, falhas de snapshot e limites de recursos do host.

**Critérios de aceite**

- [ ] O operador consegue identificar, antes do início, quais waves transferirão bytes reais.
- [ ] Nenhum caminho absoluto do host é exposto na API, UI, eventos ou relatórios.
- [ ] O relatório torna impossível confundir os 100 TB lógicos com volume físico efetivamente lido.

## Fase 5 — validação fim a fim e hardening

**Marco:** o caminho de dados real é comprovado em amostra pequena, com segurança e retomada.

- [ ] Executar dataset conhecido de 20–100 GB com restore BULK/STANDARD, range, multipart, pause/resume, retry e expiração.
- [ ] Exercitar auditoria SHA-256 e verificar as evidências de origem, worker e destino simulado.
- [ ] Testar reinício, clone/replay, concorrência, alteração de arquivo durante leitura e exaustão controlada de recursos.
- [ ] Adicionar testes de path traversal, permissões, symlink, arquivos especiais e limite de descritores.
- [ ] Documentar que purge de cenário remove catálogo/evidência, nunca os arquivos físicos do dataset.

**Critérios de aceite**

- [ ] A suíte Fujin/Raijin permanece verde e cobre payload determinístico e local.
- [ ] Falhas de snapshot são diagnosticáveis sem leitura fora do dataset permitido.
- [ ] Nenhuma credencial AWS/OCI é necessária no modo Simulation.

## Fase 6 — preparação e execução representativa de 100 TB

**Marco:** quando os recursos forem disponibilizados, o ensaio híbrido é executado com uma amostra física suficiente para produzir evidência operacional útil.

- [ ] Preparar manifesto versionado, gerador determinístico, template `HYBRID`, runbook e dashboard antes de solicitar capacidade.
- [ ] Solicitar volume dedicado de 10 TB úteis (mínimo 5 TB), espaço auxiliar, telemetria de host/link e janela sem carga concorrente.
- [ ] Executar smoke físico de 20–100 GB e ensaio operacional de 1 TB antes da validação representativa.
- [ ] Executar 100 TB lógicos com 5–10 TB físicos únicos, distribuindo waves físicas pelo pipeline virtual.
- [ ] Registrar resultado, limitações, throughput, ociosidade e relação entre bytes lógicos/físicos.

**Critérios de aceite**

- [ ] Dataset, snapshot, mount read-only, histograma, telemetria e suíte de regressão são validados antes do ensaio de 5–10 TB.
- [ ] A interpretação do resultado identifica claramente a capacidade de disco, rede e host usada.
- [ ] A fase integral de 100 TB físicos só é proposta se houver origem e destino físicos independentes com essa capacidade.

## Sequência recomendada

1. Fase 1 — estabelece compatibilidade, contrato e isolamento.
2. Fase 2 — torna o acesso físico seguro antes de expô-lo ao operador.
3. Fase 3 — implementa os modelos de massa reproduzíveis.
4. Fase 4 — integra ao fluxo e torna a fidelidade observável.
5. Fase 5 — comprova o produto em dataset pequeno.
6. Fase 6 — usa a capacidade solicitada para a validação representativa.

## Preparação para o teste de alta fidelidade

O produto deve ser implementado e testado primeiro com datasets pequenos. A execução representativa de uma source lógica de 100 TB fica planejada para quando houver capacidade de armazenamento suficiente; ela não depende de criar um bucket AWS de 100 TB.

### Perfil alvo: source lógica de 100 TB

| Aspecto | Alvo |
|---|---|
| Catálogo lógico | 100 TB, com distribuição de objetos, prefixes e storage classes inspirada na source a ser migrada |
| Dataset físico único | 5–10 TB de arquivos locais únicos; 10 TB é o alvo recomendado |
| Modelo Fujin | `HYBRID`: waves físicas distribuídas ao longo do pipeline, não concentradas no início |
| Origem física | volume local dedicado, montado somente leitura no simulador |
| Destino | evidência simulada atual na primeira etapa; persistência física de destino é extensão separada |
| Nuvem pública | nenhuma chamada AWS/OCI no modo Simulation |

### Distribuição inicial do dataset físico

Esta distribuição é uma base de capacidade, não uma verdade universal. Antes do teste, ela deve ser recalibrada com o histograma do inventário real ou esperado.

| Faixa de tamanho | Quantidade de referência | Volume aproximado | Finalidade |
|---|---:|---:|---|
| 1 KB–10 MB | 100.000 | 200 GB | metadata, arquivos pequenos, throughput de operações |
| 10 MB–1 GB | 20.000 | 2 TB | streaming, checksum, concorrência comum |
| 1–20 GB | 800 | 5 TB | multipart, retry e retomada |
| 20–100 GB | 50 | 3 TB | transferências longas e pressão sustentada |

O total de referência é próximo de 10 TB. Se só 5 TB estiverem disponíveis, preservar todas as faixas e reduzir a quantidade proporcionalmente; não substituir o conjunto por poucos arquivos gigantes repetidos.

### Recursos a solicitar no momento oportuno

1. Volume de bloco dedicado de **10 TB úteis** (mínimo aceitável: 5 TB), com IOPS/throughput conhecidos e monitorados.
2. Espaço adicional de 15–20% para staging controlado, hashes temporários, logs e crescimento do filesystem. O mount entregue ao Fujin continua estritamente somente leitura.
3. VM ou host de teste com CPU, memória e rede documentadas; o teste mede a combinação host + volume + link, não somente o Fujin.
4. Janela operacional sem outras cargas intensivas no mesmo volume/link.
5. Dataset sintético ou anonimizado com distribuição aprovada. Nenhum dado de produção deve ser copiado sem revisão de privacidade e retenção.
6. Se a intenção futura for validar escrita física de destino, um segundo volume independente, com capacidade equivalente à amostra física, e uma extensão específica do Fujin para persistir o destino.

### Artefatos que devem existir antes de solicitar os recursos

1. Manifesto versionado do dataset: contagem, tamanhos, histogramas, prefixes, classe de storage, seed, hash por arquivo e política de retenção.
2. Gerador determinístico de dataset capaz de criar a distribuição aprovada em lotes, retomar após interrupção e verificar hashes sem carregar arquivos inteiros na memória.
3. Template `HYBRID` versionado, com regra determinística de quais waves usam `LOCAL_FILE` e quais usam `DETERMINISTIC`.
4. Runbook de provisionamento: formatação/mount do volume, permissões, bind mount read-only no container, cadastro do dataset, importação, validação e limpeza.
5. Dashboard/report com: bytes lógicos, bytes físicos únicos, bytes físicos efetivamente lidos, arquivos por faixa, taxa de leitura, uso do link, cache e falhas de snapshot.
6. Plano de rollback e limpeza que nunca apague o dataset físico por meio da operação de purge do cenário.

### Fases de execução quando a capacidade existir

1. **Smoke físico (20–100 GB):** validar mount, importação, restore, range, checksum, multipart e expiração.
2. **Ensaio operacional (1 TB):** validar concorrência, queue, Raikou, pause/resume, retry e relatório sob carga prolongada.
3. **Validação representativa (5–10 TB):** executar o perfil híbrido de 100 TB lógico, com waves físicas distribuídas pelo calendário virtual.
4. **Opcional — sustentação integral:** somente quando houver 100 TB físicos únicos e destino físico: medir cópia completa, desgaste de I/O e comportamento de longa duração.

### Go / no-go para a validação representativa

Só iniciar a fase de 5–10 TB se: o snapshot do dataset estiver íntegro; o volume possuir espaço livre previsto; o mount read-only tiver sido validado; o histograma estiver aprovado; a suíte de regressão do Fujin/Raijin estiver verde; e métricas de host/link estiverem sendo coletadas. Qualquer divergência de snapshot, erro de isolamento ou falta de telemetria bloqueia o teste, pois invalidaria sua interpretação.

## Registro de acompanhamento

| Fase | Estado | Evidência / commit | Observações |
|---|---|---|---|
| 1 — Fundação | Pendente | — | Não iniciar sem migração, compatibilidade e contrato versionado. |
| 2 — Reader seguro | Pendente | — | Depende da configuração read-only e da validação de snapshot. |
| 3 — Modelos de massa | Pendente | — | Implementa Virtual, Representativo e Híbrido. |
| 4 — Interface e observabilidade | Pendente | — | Depende da composição persistida no catálogo. |
| 5 — E2E e hardening | Pendente | — | Pode usar datasets pequenos já disponíveis. |
| 6 — Ensaio representativo | Aguardando recursos | — | Requer volume dedicado de 5–10 TB e telemetria do ambiente. |
