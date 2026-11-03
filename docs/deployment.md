# Deploy e instalação do Raijin

Este guia descreve uma instalação limpa e única do Raijin para migrações AWS S3 → OCI Object Storage. O runtime opera sempre contra os provedores configurados; não existem perfis alternativos, bancos auxiliares ou serviços de emulação nesta instalação. Para recuperar uma instalação existente, consulte o [runbook de recuperação](recovery-runbook.md).

## Pré-requisitos do cliente

- Subnet existente com saída HTTPS para AWS S3/STS, AWS Price List (`pricing.us-east-1.amazonaws.com`), OCI Vault/Object Storage, repositório Git aprovado, registry de imagens e PyPI na primeira construção.
- Acesso SSH à VM pela rede corporativa.
- Permissões para executar o stack no OCI Resource Manager e criar os recursos selecionados.
- Policy automática de backup do boot volume existente, ou autorização para criá-la/associá-la.

## OCI Resource Manager

> **Migração de stack existente:** a versão atual da stack não gerencia mais o
> Block Volume `*-separado-payloads`. Antes de aplicar esta alteração em uma stack
> criada por versão anterior, confirme no plano Terraform a destruição do
> volume e preserve/mova qualquer payload separado que ainda precise ser mantido.
> Em uma instalação nova, nenhum recurso separado é criado.

1. Crie um Stack a partir de `terraform/orm` neste repositório.
   O formulário usa seletores OCI para compartment, availability domain,
   VCN, subnet, imagem, shape, chave SSH, Vault, Key, Secrets e policy de
   backup. Selecione primeiro o compartment e a VCN: a lista de subnets é
   filtrada pela VCN escolhida e o Terraform valida essa associação no plano.
2. Preencha o formulário. Use 8 OCPUs, 32 GB e boot volume de 500 GB como ponto de partida. A stack cria somente os recursos necessários ao Raijin; ela não cria, anexa ou formata volumes de payload do separado.
   A VM aceita administração SSH exclusivamente por chave pública/privada: senha, teclado interativo e login direto de root são desabilitados pelo cloud-init e reforçados pelo bootstrap. A porta 8080 nunca deve ser liberada; ela é publicada apenas em `127.0.0.1` na VM. O cliente pode manter a regra de SSH sem restrição de CIDR conforme sua política, desde que preserve a proteção da chave privada.
3. Escolha criar Vault/Key ou informar os OCIDs de recursos existentes. O stack pode criar os Secrets de plataforma e um template JSON inicial de conexão AWS; quando esses recursos são externos, o cliente deve fornecer o Secret de senha PostgreSQL e as policies correspondentes.
4. Se criar policy, informe os buckets OCI de destino em `destination_buckets_json`. Agrupe buckets no mesmo compartment sempre que possível.
5. Aplique o stack. Por padrão, ele cria e associa uma policy de backup incremental diário do boot volume, com retenção de 35 dias. É possível informar uma policy existente em vez disso.
6. Para conexões AWS, crie ou atualize um único Secret JSON seguindo [Conexões AWS](aws-connections.md). Em **Configurações → Conexões AWS**, atualize os Secrets, cadastre a conexão e execute seu pré-check.
7. Confirme que a policy automática de backup está associada ao boot volume.

Depois do deploy, abra **Configurações → Inventário de buckets OCI** e use **Atualizar buckets OCI**. A consulta ocorre somente sob demanda via OCI Resource Search no tenancy e o resultado é persistido no PostgreSQL. O cadastro de origem aceita apenas um bucket presente nesse cache; a policy da Dynamic Group continua sendo a autorização efetiva para escrita.

O PostgreSQL é iniciado com `--shm-size=512m`. Esse limite evita que consultas de consolidação do Resultado final e da timeline esgotem o `/dev/shm` padrão de containers em sources com muitos segmentos de transferência.

O schema aditivo cria `project_closure_reports` no startup. Antes de publicar
uma release que introduza essa tabela, execute o backup PostgreSQL normal. PDF
e ZIP finais são persistidos no banco para preservar os bytes emitidos; inclua
essa tabela no dimensionamento e na política de retenção dos backups. O pacote
não é removido quando projeto ou source são desativados.

Uma origem com apenas cadastro, discovery, inventário ou ondas ainda não executadas pode ser excluída definitivamente, removendo também esses dados de preview. Depois que um worker assumir qualquer onda, a interface disponibiliza somente **Arquivar**: ela pausa ondas não concluídas, remove a origem da lista diária e mantém todo o histórico para auditoria.

## Instalação em uma nova VM

Conclua antes o [OCI Setup](oci-setup.md), incluindo VM, Instance Principal,
Dynamic Group, policies, buckets OCI, Vault, Secrets e backup do boot volume.
Para uma origem AWS real, conclua também [AWS Setup](aws-setup.md) ou o roteiro
equivalente por [AWS CLI](aws-cli-setup.md). A conectividade OCI–AWS, rotas,
DNS e firewall do caminho de dados são pré-requisitos do cliente.

Registre estes valores antes de acessar o host:

| Código | Finalidade |
|---|---|
| `<LINUX_USER>` / `<VM_HOST>` | Usuário Linux com chave SSH e IP/nome administrativo da VM. |
| `<REPOSITORY_URL>` / `<RELEASE_REF>` | Repositório aprovado e tag ou commit imutável aprovado. |
| `<OBJECT_STORAGE_NAMESPACE>` | Namespace Object Storage do tenancy. |
| `<SECRETS_COMPARTMENT_OCID>` | Compartment dos Secrets da plataforma. |
| `<DESTINATION_COMPARTMENT_OCID>` | Compartment dos buckets OCI autorizados. |
| `<POSTGRES_SECRET_OCID>` | Secret `postgres_password`. |

### 1. Preparar o host

Conecte-se com a chave SSH aprovada e instale as dependências de bootstrap:

```bash
ssh <LINUX_USER>@<VM_HOST>
sudo dnf install -y git podman
git --version
podman --version
```

Não abra TCP/1604 no NSG, security list ou firewall. Por padrão, a interface é
publicada somente em `127.0.0.1:1604` e será acessada pelo túnel SSH.

### Bind da console web

O bootstrap cria `/etc/raijin-data-migration/web-bind.env` com o padrão seguro:

```ini
WEB_BIND_HOST=127.0.0.1
WEB_BIND_PORT=1604
```

O host aceita `127.0.0.1`, `0.0.0.0`, `::` ou um IP específico da VM; a porta
deve estar entre 1 e 65535. Após alterar o arquivo, aplique com
`sudo systemctl restart raijin-data-migration.service`. O processo no container
continua na porta interna `8080`; não a exponha diretamente. Um bind diferente
de loopback exige controles externos equivalentes, como NSG, firewall e proxy
reverso com autenticação.

### Autenticação local da console

O bootstrap também cria `/etc/raijin-data-migration/web-auth.env`. Nesta release o
valor padrão é compatível com instalações existentes e **não ativa** login:

```ini
RAIJIN_WEB_AUTH_MODE=disabled
RAIJIN_WEB_EXTERNAL_HTTPS=false
RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS=
RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES=30
RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES=720
RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME=admin
```

Para ativar login local pela primeira vez, crie `console_bootstrap_password`
**somente** em `secret_file_paths` de `oci-runtime.json`, apontando para um
arquivo local root-owned `0600`. Altere somente `RAIJIN_WEB_AUTH_MODE=local` e
valide antes do restart:

```bash
sudo /usr/local/sbin/raijin-console-auth-preflight
sudo systemctl restart raijin-data-migration.service
```

O primeiro início cria somente o usuário bootstrap como `ADMIN`, com senha
Argon2id, e exige troca de senha no primeiro login. Enquanto essa troca não
terminar, o Raijin força o bind para `127.0.0.1`, ignorando temporariamente
`web-bind.env`. Depois, invalide e remova o arquivo local e sua referência em
`oci-runtime.json`; só então um bind configurado fora de loopback poderá ser
usado, ainda exigindo `RAIJIN_WEB_EXTERNAL_HTTPS=true` e os CIDRs exatos do
proxy reverso confiável. Nunca publique `0.0.0.0` diretamente.

O rollback é explícito: mantenha o serviço em bind privado/loopback, mude
`RAIJIN_WEB_AUTH_MODE=disabled` e reinicie. As tabelas de usuários, sessões e
auditoria são preservadas; reativar `local` reutiliza as mesmas contas. Após
qualquer restart ou restore PostgreSQL, as sessões anteriores são revogadas e
cada pessoa precisa efetuar login novamente.

Recuperação de acesso é exclusiva do host e exige arquivo de senha root-owned
`0600`; a senha nunca entra em argumento ou log:

```bash
sudo install -o root -g root -m 0600 /dev/null /root/raijin-console-reset-password
sudoedit /root/raijin-console-reset-password
sudo RAIJIN_CONSOLE_ADMIN_PASSWORD_FILE=/root/raijin-console-reset-password \
  /usr/local/sbin/raijin-console-admin reset admin --confirm
```

A recuperação revoga as sessões do usuário afetado e registra um evento de
auditoria. A matriz de autorização efetiva está em
`docs/web-console-authentication-route-matrix.md`.

### 2. Criar a configuração de runtime OCI

O arquivo contém referências de Secret (OCIDs ou caminhos locais protegidos) e
metadados; nunca valores de senha, access key ou outro conteúdo de Secret:

```bash
sudo install -d -m 0755 /etc/raijin-data-migration
sudo vi /etc/raijin-data-migration/oci-runtime.json
```

Substitua todos os valores entre `<...>` e proteja o arquivo:

```json
{
  "object_storage_namespace": "<OBJECT_STORAGE_NAMESPACE>",
  "object_storage_endpoint_url": "",
  "object_storage_ca_bundle_path": "",
  "destination_compartment_names": {
    "<DESTINATION_COMPARTMENT_OCID>": "<DESTINATION_COMPARTMENT_NAME>"
  },
  "secret_ocids": {"postgres_password": "<POSTGRES_SECRET_OCID>"},
  "secret_file_paths": {
    "console_bootstrap_password": "/etc/raijin-data-migration/bootstrap-console-password"
  },
  "secrets_compartment_ocid": "<SECRETS_COMPARTMENT_OCID>",
  "secret_compartment_ocids": ["<SECRETS_COMPARTMENT_OCID>"]
}
```

Cada nome de Secret deve estar em exatamente uma das duas seções. O bootstrap
inicial da console sempre usa um caminho absoluto root-owned `0600` em
`secret_file_paths`:

```json
{
  "secret_ocids": {"postgres_password": "<POSTGRES_SECRET_OCID>"},
  "secret_file_paths": {
    "console_bootstrap_password": "/etc/raijin-data-migration/bootstrap-console-password"
  }
}
```

Após a primeira troca de senha do administrador, remova o arquivo local de
bootstrap e a referência `console_bootstrap_password`; ele não deve ser movido
para Vault nem reutilizado. O arquivo materializado correspondente em
`/etc/raijin-data-migration/secrets/` também deve ser removido antes de expor um
bind não-loopback.

```bash
sudo chmod 0600 /etc/raijin-data-migration/oci-runtime.json
```

Deixe endpoint e CA vazios para OCI público. Em OCI privado, informe a URL
HTTPS e o bundle da CA interna. Para Secrets em compartments adicionais,
inclua cada OCID em `secret_compartment_ocids` e confirme as policies OCI.

Para cada Secret, configure exatamente uma origem: `secret_ocids` (OCI Vault)
ou `secret_file_paths` (fallback local). O fallback local é indicado apenas
antes da liberação do Vault: use um caminho absoluto para arquivo regular do
host, pertencente a `root`, com modo `0600` ou mais restritivo. Exemplo:

```json
"secret_ocids": {},
"secret_file_paths": {
  "postgres_password": "/etc/raijin-data-migration/bootstrap/postgres_password"
}
```

O valor do arquivo nunca é mostrado pela console, API ou logs. Quando Vault
estiver disponível, substitua o caminho pelo OCID e execute o procedimento de
adoção de Secrets abaixo.

### 3. Materializar uma release imutável

O bootstrap exige `/opt/raijin-data-migration/release`. A primeira construção usa
Podman no host; por isso exige acesso ao repositório, registries e PyPI. Um
artefato offline completo ainda não é um caminho de instalação suportado.

```bash
sudo install -d -m 0755 /opt/raijin-data-migration
sudo git clone '<REPOSITORY_URL>' /opt/raijin-data-migration/release
sudo git -C /opt/raijin-data-migration/release checkout --detach '<RELEASE_REF>'
sudo git -C /opt/raijin-data-migration/release rev-parse HEAD
```

Registre o hash retornado como evidência da instalação.

### 4. Bootstrap e validação técnica

```bash
sudo /opt/raijin-data-migration/release/scripts/bootstrap.sh
sudo systemctl enable --now raijin-data-migration.service

sudo systemctl is-active raijin-data-migration.service
curl --fail --silent http://127.0.0.1:1604/healthz
curl --fail --silent http://127.0.0.1:1604/api/runtime
sudo podman ps --format '{{.Names}} | {{.Status}}'
sudo systemctl list-timers 'raijin-*' --all
```

O bootstrap lê os Secrets pelo Instance Principal, prepara PostgreSQL
persistente, rede Podman, API, os quatro papéis Raikō, Raiju, launchers e
timers. Em falha,
registre logs sem expor Secrets:

```bash
sudo journalctl -u raijin-data-migration.service -n 200 --no-pager
```

### 5. Aceite funcional inicial

Abra o túnel na estação administrativa:

```bash
ssh -N -L 1604:127.0.0.1:1604 <LINUX_USER>@<VM_HOST>
```

Abra `http://127.0.0.1:1604`. Em **Configurações**, atualize o inventário de
buckets OCI, cadastre a conexão AWS por Secret e execute o pré-check. Faça
discovery de uma source de teste e valide eventos, fila e observabilidade. O
pré-check não restaura, lista nem baixa objetos AWS.

Se o bucket não aparecer ou o pré-check falhar, confirme Dynamic Group, policy
e compartment corretos, propagação IAM, nome exato do bucket e os OCIDs do
arquivo `oci-runtime.json`.

### 7. Atualizar uma instalação existente

Atualização não é instalação nova. Em janela operacional, preserve PostgreSQL
e `/var/lib/raijin-data-migration`, prepare a release em diretório separado, valide
a imagem e faça drain antes da ativação. Esta instalação única não mantém
rollback automático. Não use `raijin-stop-runtime` durante cópias: ele remove
a topologia ativa. Em caso de falha ou restauração de backup, siga o
[runbook de recuperação](recovery-runbook.md).

## Acesso local à interface

Na estação administrativa, crie um túnel SSH:

```bash
ssh -N -L 1604:127.0.0.1:1604 <usuario>@<ip-ou-hostname-da-vm>
```

Depois, acesse `http://127.0.0.1:1604`. A porta da aplicação não deve ser liberada no NSG/security list.

### Operação da console

A console é o plano de controle local e persiste suas operações no PostgreSQL da VM. Ela oferece:

- cadastro de conexões AWS reutilizáveis e seleção de uma conexão, origem S3 e bucket OCI de destino;
- totais e amostra paginada do inventário que foi descoberto;
- criação manual de uma onda, criação automática por tamanho, criação automática restrita a um prefixo S3 e criação dinâmica por duração prevista, todas de no máximo 10 TB, com tier e duração de restore;
- prévia local antes da criação automática, com objetos, bytes, estimativa de ondas e alerta para objetos acima do tamanho alvo;
- download do manifesto CSV da onda, já com as chaves codificadas para S3 Batch Operations;
- relatório de objetos, bytes, estados, tarefas, tentativas e erros por onda;
- pausa, retomada, reprocessamento e exclusão controlada de ondas ainda não executadas; e
- saúde do banco/fila e espaço livre do volume, além de recuperação de tarefas cujo lease expirou após interrupção; e
- histórico operacional persistente para ações administrativas e de fila.

Os formulários e indicadores principais possuem ícones `i` de ajuda contextual. Eles descrevem limites, impacto operacional e, quando aplicável, impactos de custo e prazo de restore. A ajuda está disponível por mouse e teclado.

A navegação separa claramente os dois contextos: **Status** contém apenas saúde global, observabilidade e prontidão de integrações; **Queue** é a console de acompanhamento da migração, com atividade, fila durável de transferência, workers e auditorias profundas. A atualização automática configurável atua na tela Queue.

Os parâmetros operacionais são persistidos no PostgreSQL. Cinco containers ficam separados da API: **Raikō::Shin** assume planejamento e reconciliação global; **Raikō::Sei**, restores Batch e polling; **Raikō::Kō**, discovery; **Raikō::Kai**, auditorias; e o **Raiju**, somente cópia e retomada multipart. Todos usam leases na mesma fila PostgreSQL, com responsabilidades de tarefa disjuntas.

### Execução local por Compose

Para desenvolvimento local, inicie exclusivamente os componentes do Raijin:

```bash
docker compose up -d
```

A console fica disponível somente no endpoint configurado para o host. A imagem deve receber `RAIJIN_SERVICE_VERSION` e `RAIJIN_BUILD_REVISION` durante o build para que a tela About mostre uma revisão rastreável.


### Secret `postgres_password`

O Terraform gera uma senha aleatória de 48 caracteres para o usuário local `migration`, persiste-a no OCI Vault e a VM a lê com sua identidade dinâmica antes de inicializar o PostgreSQL. Não é uma credencial AWS, não é exibida na interface e não pode ser reutilizada. O arquivo local materializado tem permissão `0600` e apenas permite que a VM volte a iniciar sem depender de uma consulta ao Vault a cada reboot. Não altere a versão no Vault diretamente: a rotação deve atualizar coordenadamente o Vault, o PostgreSQL e o arquivo local com `scripts/sync-postgres-password-from-vault.sh`.

Como o valor gerado pelo provider `random` fica no state do Terraform, o state do OCI Resource Manager deve permanecer restrito aos operadores autorizados do stack.

O botão **Discovery** permite escolher entre duas modalidades. O discovery remoto produtivo usa somente `ListObjectsV2` paginado: registra chave, tamanho, ETag, classe de armazenamento e última modificação sem restaurar, baixar, fazer `HeadObject` ou listar tags. Metadados e tags são lidos somente no momento da cópia de cada objeto já restaurado. Para mais de **1 milhão de objetos**, prefira o [S3 Inventory](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-inventory.html) para reduzir chamadas à API, custo e carga operacional desnecessária. Esse é um limite operacional conservador do Raijin, não uma limitação formal da AWS; `ListObjectsV2` retorna no máximo 1.000 chaves por chamada. Consulte também a [referência ListObjectsV2](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html). A alternativa **Usar arquivo de inventário** importa um CSV UTF-8 (ou `.csv.gz`) diretamente para a origem, em lotes no servidor e sem chamar a AWS. O arquivo deve conter cabeçalho e as colunas `object_key`/`Key` e `size_bytes`/`Size`; também aceita `ETag`, `StorageClass`, `LastModifiedDate`, `VersionId`, `metadata_json` e `tags_json`. Após a primeira carga, use **Executar re-discovery** (vermelho): informe uma justificativa com mais de 10 caracteres e escolha novamente API remota, arquivo ou `manifest.json`. A operação adiciona chaves novas e atualiza somente registros ainda sem wave; qualquer alteração em objeto já associado a wave é registrada como evidência separada, sem reescrever o histórico de restore ou transferência. Quando a origem anterior foi arquivo e o re-discovery usa API, a console mostra um aviso de possíveis diferenças de momento entre as fontes. A tag na origem identifica o último método aplicado. O S3 Inventory pode emitir CSV compactado diariamente ou semanalmente, mas a primeira entrega pode levar até 48 horas. As ações da console apenas registram ou enfileiram trabalho durável; não causam chamadas AWS pelo navegador.

O discovery remoto é um **job durável** próprio, visível em **Queue → Fila de discovery** com estado, lease, tentativa, erro, páginas e objetos do último checkpoint. Ele persiste no máximo dez páginas por transação e limita a listagem a dez chamadas de API por segundo; se a AWS responder `SlowDown` após a tentativa interna do SDK, aplica espera exponencial e repete o mesmo cursor, sem pular chaves. Para uma base existente com milhões de objetos, execute uma vez, em janela operacional, `sudo /opt/raijin-data-migration/release/scripts/create-discovery-indexes.sh`. O script usa `CREATE INDEX CONCURRENTLY`, portanto não bloqueia leituras/escritas normais, mas consome I/O enquanto estiver em execução.

Para S3 Inventory grande, escolha **Usar arquivo de inventário** e informe o URI `s3://.../manifest.json`. O Raijin enfileira a importação e lê o manifesto e todos os shards CSV/GZIP diretamente pelo worker, sem transferir dezenas de GB pelo navegador ou pelo túnel SSH. O checkpoint contém índice do shard e número de linhas confirmado; uma retomada relê somente o shard atual até o último lote confirmado. A migration role da conexão deve ter `s3:GetObject` no bucket/prefixo de entrega do S3 Inventory, além das permissões da source. O manifesto precisa declarar `sourceBucket` igual ao bucket da source e incluir o schema `Key, Size`.

Em caso de desligamento, reinicie `raijin-data-migration.service`. PostgreSQL mantém inventário, fila, leases e evidências; tarefas com lease expirado são reassumidas pelo worker. Para uploads grandes, o `upload_id` multipart OCI e as partes já aceitas ficam no PostgreSQL: após reinício, o worker consulta essas partes e envia somente as faltantes. Discovery persiste, de forma atômica, o inventário e o checkpoint a cada até dez páginas S3; após uma interrupção, retoma sem relistar páginas confirmadas e pode repetir no máximo nove páginas ainda não confirmadas. O backup lógico diário é complementar ao backup de volume OCI; siga o [runbook de recuperação](recovery-runbook.md) para testar ou executar uma restauração controlada.

## Componentes instalados e retenção de backup

O procedimento de instalação de release está na seção
[Materializar uma release imutável](#3-materializar-uma-release-imutável).
O bootstrap constrói a imagem com Podman no host; portanto, a primeira
instalação exige acesso aos registries e dependências declarados acima.

Na Oracle Linux, o bootstrap utiliza Podman nativo e registra `raijin-data-migration.service` no systemd. Os containers `raijin-postgres` e `raijin-app` usam volumes persistentes no boot volume. A API é publicada em `127.0.0.1:1604` por padrão e pode ser ajustada em `web-bind.env`.

O timer `raijin-backup-postgres.timer` executa diariamente às 02:15 UTC um `pg_dump` dos bancos real e antigo e conserva 35 dias por padrão. Esse prazo cobre a quarentena padrão de 30 dias do ambiente antigo. Ele pode ser ampliado com `RAIJIN_LOGICAL_BACKUP_RETENTION_DAYS` no serviço systemd, mas nunca reduzido abaixo de 30 dias. Isso complementa, mas não substitui, a policy automática de backup do boot volume.
