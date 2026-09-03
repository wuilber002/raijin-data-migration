# Plano — payloads locais reais no Fujin

## Objetivo

Permitir que o Fujin exponha, para uma execução `DATA` explicitamente configurada, bytes de arquivos existentes em um diretório local controlado. O catálogo, o relógio virtual, as regras de restore, expiração e os jobs continuam no PostgreSQL do Fujin. Assim, o Raijin exercita transferência, multipart, checksum e retomada com bytes reais, sem chamada à AWS ou à OCI.

O modo atual, que gera bytes determinísticos a partir do catálogo, permanece o padrão e não pode mudar de comportamento.

## Situação atual confirmada

- `VirtualObject` já separa metadados e identidade lógica de conteúdo (`content_seed`, `content_object_id`, `source_sha256`).
- `SimulationEngine.read_range()` produz os bytes determinísticos para a faixa solicitada; os endpoints `/v1/cloud/source/read-range` e `/v1/cloud/destination/read-range` apenas os transmitem.
- O destino simulado hoje consome o upload e persiste evidência de tamanho/checksum; ele não guarda o payload recebido.
- Restore e expiração são predicados do catálogo. Portanto, um arquivo local pode continuar “arquivado” até a disponibilidade virtual, sem mover nem duplicar o arquivo no disco.
- O Fujin não é, hoje, um emulador genérico de toda a API S3: ele implementa o contrato versionado consumido pelos ports simulados do Raijin. O recurso deve preservar esse contrato.

## Decisões de desenho

1. Expor três modelos de massa na criação da execução. O modo de payload continua registrado por objeto, mas o modelo explica ao operador como o catálogo inteiro será composto:

   - **Catálogo virtual** (`VIRTUAL`) — modelo atual: todos os objetos usam payload determinístico. É apropriado para escala lógica, planejamento e testes de controle; não exige arquivos no disco.
   - **Amostra real compartilhada** (`REPRESENTATIVE`) — o catálogo pode ter muitos objetos, mas eles referenciam, de forma declarada, um conjunto pequeno de arquivos reais. Exercita leitura, multipart, checksum e retry com I/O real sem exigir o volume lógico no disco.
   - **Execução híbrida** (`HYBRID`) — waves ou faixas de waves explicitamente selecionadas usam arquivos reais; as demais preservam payload determinístico. É o modelo recomendado para validar uma migração grande com uma amostra física representativa.

   No nível do objeto, `DETERMINISTIC` permanece o padrão atual e `LOCAL_FILE` identifica a referência a um arquivo do dataset local imutável.

2. O diretório não é uma entrada de caminho arbitrário fornecida pelo navegador ou pelo Raijin. O operador cadastra previamente um **dataset local** por configuração administrativa; a execução referencia seu identificador.

3. O Fujin só recebe um bind mount de leitura, por exemplo `/fujin-data`, no container do simulador. Nenhum caminho absoluto do host é armazenado nem devolvido pela API.

4. A primeira entrega cobre **fonte local real**. Persistir bytes de destino em filesystem é uma extensão opcional posterior; não será misturada ao objetivo de validar a leitura e transferência de uma fonte real.

5. Um dataset é transformado em snapshot no momento da importação/materialização. Arquivos alterados, removidos ou substituídos depois disso devem falhar de modo explícito, nunca serem lidos silenciosamente como se fossem o snapshot original.

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

## Sequência de implementação

1. **Fundação** — migração, modelos, capability, configuração de mount somente leitura e contratos de erro; sem alterar `read_range` ainda.
2. **Reader local** — `SourcePayloadReader`, validação de paths/snapshot e testes unitários de ranges, EOF, checksum e corrupção.
3. **Importador e composição** — cadastro administrativo, scan incremental, criação de objetos `LOCAL_FILE`, associação representativa determinística, seleção de waves híbridas, relatórios de erro e idempotência.
4. **Integração do engine** — seleção do reader após a regra de restore; preservar reader determinístico em Catálogo virtual e nas waves lógicas do modo híbrido.
5. **Observabilidade/UI** — dataset/snapshot na Simulation, métricas de I/O e evidências no relatório.
6. **E2E** — dataset pequeno com arquivos conhecidos, restore BULK/STANDARD, transferência normal e multipart, pause/resume, retry, expiração e auditoria SHA-256.
7. **Hardening** — testes de path traversal/symlink/alteração durante leitura, carga concorrente, reinício e clone/replay.
8. **Extensão opcional** — somente se houver demanda: destino físico local com root separado e evidência de escrita, sem mudar a semântica da fonte.

## Critérios de aceite

- Cenários existentes `CONTROL` e `DATA` determinísticos continuam produzindo os mesmos resultados e passam na suíte atual.
- Um arquivo real só é acessível após o restore virtual e fica indisponível depois da expiração.
- Leitura de faixa retorna exatamente os bytes e `Content-Length` solicitados, inclusive em multipart e retomada.
- Alteração, remoção, symlink ou escape de root após o snapshot falha de forma explícita, auditável e sem leitura fora do dataset.
- Nenhuma credencial AWS/OCI é necessária; o simulador continua isolado.
- O relatório permite provar qual dataset e qual snapshot abasteceram a execução.
