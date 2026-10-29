# Deploy e instalação do Raijin

Este é o procedimento canônico e único para provisionar, instalar, validar e
atualizar o RAIJIN em uma VM OCI. Uma instalação nova inicia um plano de
controle vazio: não importa PostgreSQL, catálogo Fujin, payloads ou filas de
outro host. Para recuperar uma instalação existente, consulte o
[runbook de recuperação](recovery-runbook.md).

Em uma topologia Fujin LOCAL já saudável, prefira a atualização mínima do
plano de controle. Depois do backup lógico e build da imagem alvo, execute:

```bash
sudo /opt/s3-oci-migration/release/scripts/update-fujin-local-raijin-runtime.sh \
  localhost/s3-oci-migration:<nova-release>
```

O atualizador recusa a troca se houver dispatcher de transferência em execução
ou item com lease ativo. Ele mantém PostgreSQL, Fujin, materializador, DNS e
gateway online; inicia uma aplicação candidata ao lado da atual, valida health,
schema e revisão Git, e somente então faz o handoff do alias privado e inicia
Raikou/Raiju. O gateway repete falhas transitórias durante essa troca e recarrega
seu DNS depois da retirada do app antigo. Ao fim, o script exige que app,
Raikō::Shin, Raikō::Sei, Raikō::Kō, Raikō::Kai e Raiju usem exatamente a imagem
alvo e registra se o Fujin permanece em outra release — ele não substitui
Fujin implicitamente. Se a candidata falhar antes do handoff, o runtime antigo
permanece online. Esta instalação única não executa rollback automático após o
handoff: a falha encerra o plano de controle para investigação explícita.
Polling
de restore em estado `READY` pode aguardar essa curta janela sem nova submissão
AWS/Fujin; stream ou multipart já admitido nunca deve ser interrompido.

O deploy padrão inicia PostgreSQL, API, Raikō::Shin, Raikō::Sei, Raikō::Kō,
Raikō::Kai e Raiju em `REAL`. Fujin LOCAL é
uma topologia opcional de pré-produção e só é ativada depois do aceite do
runtime normal.

## Pré-requisitos do cliente

- Subnet existente com saída HTTPS para AWS S3/STS, AWS Price List (`pricing.us-east-1.amazonaws.com`), OCI Vault/Object Storage, repositório Git aprovado, registry de imagens e PyPI na primeira construção.
- Acesso SSH à VM pela rede corporativa.
- Permissões para executar o stack no OCI Resource Manager e criar os recursos selecionados.
- Policy automática de backup do boot volume existente, ou autorização para criá-la/associá-la.

## OCI Resource Manager

> **Migração de stack existente:** a versão atual da stack não gerencia mais o
> Block Volume `*-fujin-payloads`. Antes de aplicar esta alteração em uma stack
> criada por versão anterior, confirme no plano Terraform a destruição do
> volume e preserve/mova qualquer payload Fujin que ainda precise ser mantido.
> Em uma instalação nova, nenhum recurso Fujin é criado.

1. Crie um Stack a partir de `terraform/orm` neste repositório.
   O formulário usa seletores OCI para compartment, availability domain,
   VCN, subnet, imagem, shape, chave SSH, Vault, Key, Secrets e policy de
   backup. Selecione primeiro o compartment e a VCN: a lista de subnets é
   filtrada pela VCN escolhida e o Terraform valida essa associação no plano.
2. Preencha o formulário. Use 8 OCPUs, 32 GB e boot volume de 500 GB como ponto de partida. A stack cria somente os recursos necessários ao Raijin; ela não cria, anexa ou formata volumes de payload do Fujin.
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

O bootstrap cria `/etc/s3-oci-migration/web-bind.env` com o padrão seguro:

```ini
WEB_BIND_HOST=127.0.0.1
WEB_BIND_PORT=1604
```

O host aceita `127.0.0.1`, `0.0.0.0`, `::` ou um IP específico da VM; a porta
deve estar entre 1 e 65535. Após alterar o arquivo, aplique com
`sudo systemctl restart s3-oci-migration.service`. O processo no container
continua na porta interna `8080`; não a exponha diretamente. Um bind diferente
de loopback exige controles externos equivalentes, como NSG, firewall e proxy
reverso com autenticação.

### Autenticação local da console

O bootstrap também cria `/etc/s3-oci-migration/web-auth.env`. Nesta release o
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
sudo systemctl restart s3-oci-migration.service
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
sudo install -d -m 0755 /etc/s3-oci-migration
sudo vi /etc/s3-oci-migration/oci-runtime.json
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
    "console_bootstrap_password": "/etc/s3-oci-migration/bootstrap-console-password"
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
    "console_bootstrap_password": "/etc/s3-oci-migration/bootstrap-console-password"
  }
}
```

Após a primeira troca de senha do administrador, remova o arquivo local de
bootstrap e a referência `console_bootstrap_password`; ele não deve ser movido
para Vault nem reutilizado. O arquivo materializado correspondente em
`/etc/s3-oci-migration/secrets/` também deve ser removido antes de expor um
bind não-loopback.

```bash
sudo chmod 0600 /etc/s3-oci-migration/oci-runtime.json
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
  "postgres_password": "/etc/s3-oci-migration/bootstrap/postgres_password"
}
```

O valor do arquivo nunca é mostrado pela console, API ou logs. Quando Vault
estiver disponível, substitua o caminho pelo OCID e execute o procedimento de
adoção de Secrets abaixo.

### 3. Materializar uma release imutável

O bootstrap exige `/opt/s3-oci-migration/release`. A primeira construção usa
Podman no host; por isso exige acesso ao repositório, registries e PyPI. Um
artefato offline completo ainda não é um caminho de instalação suportado.

```bash
sudo install -d -m 0755 /opt/s3-oci-migration
sudo git clone '<REPOSITORY_URL>' /opt/s3-oci-migration/release
sudo git -C /opt/s3-oci-migration/release checkout --detach '<RELEASE_REF>'
sudo git -C /opt/s3-oci-migration/release rev-parse HEAD
```

Registre o hash retornado como evidência da instalação.

### 4. Bootstrap e validação técnica

```bash
sudo /opt/s3-oci-migration/release/scripts/bootstrap.sh
sudo systemctl enable --now s3-oci-migration.service

sudo systemctl is-active s3-oci-migration.service
curl --fail --silent http://127.0.0.1:1604/healthz
curl --fail --silent http://127.0.0.1:1604/api/runtime
sudo podman ps --format '{{.Names}} | {{.Status}}'
sudo systemctl list-timers 's3-oci-*' --all
```

O bootstrap lê os Secrets pelo Instance Principal, prepara PostgreSQL
persistente, rede Podman, API, os quatro papéis Raikō, Raiju, launchers e
timers. Em falha,
registre logs sem expor Secrets:

```bash
sudo journalctl -u s3-oci-migration.service -n 200 --no-pager
```

### Bootstrap temporário sem OCI Vault

Use este caminho apenas em host novo, quando seja necessário validar a
topologia local antes da liberação de Dynamic Group, policies e Secrets OCI.
Ele gera senhas aleatórias locais para PostgreSQL, protegidas em `0600`, e
permite testar a API, Raikō, Raiju, timers, banco e túnel SSH. Não cadastre
conexões AWS nem tente operações com buckets: estas continuam indisponíveis
até a configuração OCI definitiva.

O host deve conter o marcador
`/etc/s3-oci-migration/temporary-local-secrets`. Quando o Vault estiver
disponível, substitua apenas a referência de `postgres_password` no
`oci-runtime.json`: remova o respectivo `secret_file_paths` e informe o OCID
em `secret_ocids`. Mantenha o PostgreSQL em execução e reinicie o serviço:

```bash
sudo systemctl restart s3-oci-migration.service
sudo systemctl is-active s3-oci-migration.service
```

O bootstrap detecta o marcador e a mudança para Vault, troca a senha da role
principal no PostgreSQL em execução e então remove o marcador temporário. A
Secret
`simulation_postgres_password` só é necessária em uma instalação que inicie
explicitamente em `SIMULATION`. Não apague
os arquivos locais nem sobrescreva uma senha antes dessa conversão.

O utilitário `scripts/adopt-vault-secrets.sh` permanece disponível somente
para diagnóstico ou uma adoção manual excepcional; não é necessário no fluxo
normal.

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

### 6. Fujin LOCAL opcional

Fujin LOCAL mantém o Raijin em `REAL` e fornece endpoints privados compatíveis
com AWS/OCI. Ele é uma instalação separada e não é provisionado pela stack
`terraform/orm`. Antes de ativá-lo, provisione e monte externamente o volume em
`/var/lib/s3-oci-migration/fujin-payloads`, gere `oci-runtime-local.json` e
execute o [runbook de aceite Fujin LOCAL](../operacional/runbook-fujin-local-acceptance.md).

Na topologia LOCAL, `fujin-local-materializer` é o único serviço com escrita
no volume de payloads: ele cria datasets solicitados na console Fujin e só os
publica após manifesto e SHA-256. O serviço `fujin-local` que expõe S3 monta o
mesmo volume em somente leitura. Não adicione esse volume aos containers do
Raijin nem ao modo `SIMULATION`.

Ao atualizar uma base Fujin criada antes da versão 0.8.9, a primeira migração
cria índices compostos na tabela de auditoria (`bucket/object_key`, data e id).
Em históricos com milhões de eventos essa construção pode consumir I/O e
retardar temporariamente as APIs Fujin; execute a atualização sem Deep Audit
ativo e aguarde o health check concluir. Os payloads e eventos não são
reescritos, e as inicializações seguintes apenas confirmam os índices.

`s3-oci-start-fujin-local-runtime` é uma transição de topologia: faça drain e
parada controlada do runtime normal antes de executá-lo. Nunca faça essa troca
durante transferência ativa.

Registre também a topologia como decisão durável do host. O arquivo abaixo é
independente de `operation-mode`: `LOCAL` seleciona a topologia privada e o
Raijin continua sendo iniciado em `REAL` dentro dela.

```bash
printf 'LOCAL\n' | sudo tee /etc/s3-oci-migration/deployment-profile
```

O bootstrap usa esse perfil para reconstruir Fujin, DNS, materializador,
Raijin, workers e gateway após um reboot. Instalações sem o arquivo preservam
compatibilidade e assumem `STANDARD`. Valores diferentes de `STANDARD` e
`LOCAL` interrompem o bootstrap, em vez de iniciar uma topologia inesperada.
Uma topologia já saudável só é reutilizada quando seus containers próprios
também correspondem à imagem imutável da release ativa; caso contrário, o
bootstrap converge o conjunto inteiro para a revisão aprovada.

### 7. Atualizar uma instalação existente

Atualização não é instalação nova. Em janela operacional, preserve PostgreSQL
e `/var/lib/s3-oci-migration`, prepare a release em diretório separado, valide
a imagem e faça drain antes da ativação. Esta instalação única não mantém
rollback automático. Não use `s3-oci-stop-runtime` durante cópias: ele remove
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

Os parâmetros operacionais são persistidos no PostgreSQL. Cinco containers ficam separados da API: **Raikō::Shin** assume planejamento e reconciliação global; **Raikō::Sei**, restores Batch e polling; **Raikō::Kō**, discovery; **Raikō::Kai**, auditorias; e o **Raiju**, somente cópia e retomada multipart. Todos usam leases na mesma fila PostgreSQL, com responsabilidades de tarefa disjuntas. Em `REAL`, só operam após habilitação explícita. Em `SIMULATION`, os mesmos workers usam exclusivamente os contratos HTTP do backend simulado; não existe mais um worker artificial que avança estados.

### Execução local por Compose

Os perfis são mutuamente exclusivos e expõem a console somente em
`127.0.0.1:1604`:

```bash
docker compose --profile real up -d
docker compose --profile simulation up -d
docker compose --profile local up -d
```

The About page reports the semantic release and the exact build revision. CI
or a manual release should inject the Git commit while building, for example:

```bash
RAIJIN_SERVICE_VERSION=0.8.11 RAIJIN_BUILD_REVISION="$(git rev-parse --short HEAD)" docker compose build
```

Without build metadata the revision is shown as `development`, so an operator
can distinguish an unversioned local image from a traceable release.

Na VM, o bootstrap lê a versão semântica do arquivo `VERSION` da release e
deriva a revisão do commit Git ou do nome do diretório imutável. A imagem é
endereçada por essa revisão; se ainda não existir, é construída uma única vez
sem cache. Assim, a identidade exibida no About é preservada depois de reboot
e o cache do builder não pode reaproveitar metadados de outra release.

Não ative os dois perfis juntos. Em um diretório PostgreSQL novo, o init cria
`migration_simulation` e o usuário dedicado usando o Secret
`simulation_postgres_password`. Em um volume antigo, crie esse banco/usuário
antes de iniciar o perfil, ou prefira o bootstrap da VM, que faz isso de forma
idempotente. O ambiente de produção troca o modo por `raijin-mode`, depois de
um drain comprovado da fila, e nunca executa os dois runtimes ao mesmo tempo.

O perfil `local` não cria um modo adicional no Raijin: API e workers seguem
em `REAL`. Ele inicia o Fujin como provedor privado, com os dados em rede
Docker interna e as duas interfaces no mesmo túnel SSH:

```text
http://127.0.0.1:1604/raijin/
http://127.0.0.1:1604/fujin/
```

A console administrativa LOCAL não usa token próprio. O gateway publica-a
somente em `127.0.0.1`; o acesso é protegido pela chave e pelo túnel SSH que
expõe a porta local. Não há Secret Fujin adicional, e nada é entregue ao
Raijin.

Na VM Oracle Linux, o bootstrap também instala o launcher equivalente ao
perfil Compose. Depois de drenar a execução corrente, faça uma parada
controlada, gere o perfil OCI LOCAL e execute
`sudo /usr/local/sbin/s3-oci-start-fujin-local-runtime`. O launcher recusa
substituir containers ativos e recria o PostgreSQL durável somente quando ele
foi removido pela parada controlada.
Ele sobe Raijin em `REAL`, os workers, Fujin, DNS privado e o gateway em
loopback; não existe modo LOCAL no Raijin.
Antes do primeiro reboot, persista `LOCAL` em
`/etc/s3-oci-migration/deployment-profile`; o arquivo
`/etc/s3-oci-migration/operation-mode` não representa essa escolha.

A console Fujin fornece o pacote de Secret sintético no formato normal de uma
conexão AWS. Cadastre-o no Vault sem alterar o schema e crie uma conexão AWS
normal no Raijin. Para a conexão, use os endpoints HTTPS privados e a CA
`/etc/fujin-local-ca/fujin-local.crt`: `sts.<região>.fujin.internal`,
`vpce-fujin-local.s3.<região>.fujin.internal` e
`control.vpce-fujin-local.s3.<região>.fujin.internal`. O DNS interno resolve
também o hostname virtual de cada bucket. APIs de dados não possuem porta
publicada; somente a UI fica em loopback por meio do gateway.

O perfil de runtime OCI é igualmente genérico: use
`https://oci.<região>.fujin.internal`, o namespace configurado no bucket OCI
LOCAL e a mesma CA privada. Esse endpoint não pertence à Secret AWS e não
introduz um modo Fujin/LOCAL no Raijin. Gere-o a partir do perfil REAL com
`/usr/local/sbin/configure-fujin-local-oci-runtime`; o arquivo derivado é
montado exclusivamente nos containers do perfil Compose `local`.

### Alterar o modo de operação por API local

A troca de modo não é exposta na interface web. Ela é uma operação
administrativa executada somente na própria VM, pela API local publicada em
`127.0.0.1:1604`. O endpoint solicita ao host um reinício controlado e recusa
a operação enquanto houver tarefas ou *discoveries* em estado `READY` ou
`RUNNING`.

Primeiro, consulte o modo atual:

```bash
curl --fail --silent http://127.0.0.1:1604/api/runtime
```

Para solicitar a mudança para o runtime que acessa AWS e OCI reais:

```bash
curl --fail --silent --show-error \
  --request POST http://127.0.0.1:1604/api/runtime/mode \
  --header 'Content-Type: application/json' \
  --data '{"target_mode":"REAL","confirmed":true}'
```

Para solicitar a mudança para o runtime isolado, que não chama AWS nem OCI:

```bash
curl --fail --silent --show-error \
  --request POST http://127.0.0.1:1604/api/runtime/mode \
  --header 'Content-Type: application/json' \
  --data '{"target_mode":"SIMULATION","confirmed":true}'
```

Uma resposta `202` confirma somente que o host aceitou a solicitação. Aguarde
o reinício e consulte `/healthz` até receber `"status":"ok"` e o
`operation_mode` solicitado:

```bash
until curl --fail --silent http://127.0.0.1:1604/healthz; do sleep 5; done
```

Não execute a troca por navegador, por máquina remota ou durante uma
migração. Quando a API retornar `409`, conclua, pause ou recupere as tarefas
informadas antes de repetir a chamada.

O painel de saúde também mostra o estado do serviço systemd da plataforma, dos containers PostgreSQL e aplicação, do timer de backup lógico e do timer que atualiza esse estado. O host gera um pequeno JSON em `/run/s3-oci-migration` a cada minuto; o container web apenas o lê, sem acesso ao socket Podman, systemd ou privilégios de host. O JSON deixa de ser aceito depois de três minutos, para que CPU, memória, serviços e backup congelados não pareçam atuais. O atualizador controlado reinstala o helper, reinicia o timer e exige um snapshot novo antes de declarar sucesso.

Depois de qualquer atualização na VM, valide explicitamente o agendamento e a atualidade do snapshot:

```bash
sudo systemctl show s3-oci-platform-status.timer \
  -p ActiveState -p NextElapseUSecRealtime -p NextElapseUSecMonotonic
curl -fsS http://127.0.0.1:1604/raijin/api/platform/status
```

O timer deve estar ativo e possuir uma próxima execução; a API deve retornar
`available: true`, `stale: false` e `age_seconds` inferior a 180.

Embora o boot volume seja provisionado com 500 GB, a imagem OCI pode iniciar com a partição LVM ainda no tamanho original. No primeiro boot, o cloud-init expande a partição e o PV e aloca todos os extents livres do volume group ao filesystem raiz. Assim, o Raijin instalado no boot volume utiliza praticamente toda a capacidade disponível. A rotina é idempotente e não reduz nem altera o filesystem em execuções posteriores.

O bloco **Observabilidade operacional** acompanha, sem chamar AWS ou OCI: tarefas falhas e em retry, leases vencidos, checkpoints multipart pendentes de retomada, transferências sem progresso há mais de dez minutos, falhas persistidas nas últimas 24 horas, risco previsto de expiração de cópias restauradas e espaço livre do volume persistente. Para um coletor local compatível, `http://127.0.0.1:1604/metrics` expõe essas métricas no formato Prometheus (`raijin_failed_tasks`, `raijin_retrying_tasks`, `raijin_stale_task_leases`, `raijin_active_multipart_checkpoints`, `raijin_stalled_transfers`, `raijin_failures_last_24h`, `raijin_restore_expiry_risk_waves` e `raijin_disk_free_bytes`); mantenha-o atrás do mesmo túnel SSH ou de um agente local, nunca em uma porta pública.

Alertas recomendados para a operação do cliente: qualquer `raijin_failed_tasks > 0`; `raijin_stale_task_leases > 0` por mais de um ciclo de lease; `raijin_stalled_transfers > 0` por mais de 15 minutos; ou volume livre abaixo da margem de operação definida pelo cliente. Os eventos e erros detalhados permanecem no histórico persistente da console e nos logs do serviço, sem incluir valores de Secrets.

O cartão **Credenciais e integrações** no Status e o botão **Executar pré-check OCI** em Configurações usam a identidade dinâmica da VM para ler a versão atual de cada Secret e listar no máximo um objeto em cada bucket OCI já cadastrado. Quando todas as credenciais AWS estão preenchidas, o pré-check também executa `GetCallerIdentity` e `AssumeRole` na role de migração; ele não lista, restaura, baixa nem cobra operações de S3. Valores de Secret nunca entram na resposta, nos logs ou na tela.

- **Vermelho** (`PLACEHOLDER`): o valor ainda é o texto instrutivo criado pelo Terraform, ou há uma configuração ausente.
- **Amarelo** (`CONFIGURED`): o valor foi preenchido, porém não existe uma validação segura sem executar uma operação real. A role de Batch Operations só será validada ao criar o primeiro job Batch.
- **Verde** (`VALIDATED` ou `READY`): credencial/integracão testada com sucesso. As duas Secrets da credencial AWS e o ARN da role de migração ficam verdes após STS e `AssumeRole`; namespace e bucket OCI ficam verdes após a leitura autorizada.

A configuração de runtime com os OCIDs é criada pelo cloud-init e montada somente-leitura no container.

### Secret `postgres_password`

O Terraform gera uma senha aleatória de 48 caracteres para o usuário local `migration`, persiste-a no OCI Vault e a VM a lê com sua identidade dinâmica antes de inicializar o PostgreSQL. Não é uma credencial AWS, não é exibida na interface e não pode ser reutilizada. O arquivo local materializado tem permissão `0600` e apenas permite que a VM volte a iniciar sem depender de uma consulta ao Vault a cada reboot. Não altere a versão no Vault diretamente: a rotação deve atualizar coordenadamente o Vault, o PostgreSQL e o arquivo local com `scripts/sync-postgres-password-from-vault.sh`.

Como o valor gerado pelo provider `random` fica no state do Terraform, o state do OCI Resource Manager deve permanecer restrito aos operadores autorizados do stack.

O botão **Discovery** permite escolher entre duas modalidades. O discovery remoto produtivo usa somente `ListObjectsV2` paginado: registra chave, tamanho, ETag, classe de armazenamento e última modificação sem restaurar, baixar, fazer `HeadObject` ou listar tags. Metadados e tags são lidos somente no momento da cópia de cada objeto já restaurado. Para mais de **1 milhão de objetos**, prefira o [S3 Inventory](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-inventory.html) para reduzir chamadas à API, custo e carga operacional desnecessária. Esse é um limite operacional conservador do Raijin, não uma limitação formal da AWS; `ListObjectsV2` retorna no máximo 1.000 chaves por chamada. Consulte também a [referência ListObjectsV2](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html). A alternativa **Usar arquivo de inventário** importa um CSV UTF-8 (ou `.csv.gz`) diretamente para a origem, em lotes no servidor e sem chamar a AWS. O arquivo deve conter cabeçalho e as colunas `object_key`/`Key` e `size_bytes`/`Size`; também aceita `ETag`, `StorageClass`, `LastModifiedDate`, `VersionId`, `metadata_json` e `tags_json`. Após a primeira carga, use **Executar re-discovery** (vermelho): informe uma justificativa com mais de 10 caracteres e escolha novamente API remota, arquivo ou `manifest.json`. A operação adiciona chaves novas e atualiza somente registros ainda sem wave; qualquer alteração em objeto já associado a wave é registrada como evidência separada, sem reescrever o histórico de restore ou transferência. Quando a origem anterior foi arquivo e o re-discovery usa API, a console mostra um aviso de possíveis diferenças de momento entre as fontes. A tag na origem identifica o último método aplicado. O S3 Inventory pode emitir CSV compactado diariamente ou semanalmente, mas a primeira entrega pode levar até 48 horas. As ações da console apenas registram ou enfileiram trabalho durável; não causam chamadas AWS pelo navegador.

O discovery remoto é um **job durável** próprio, visível em **Queue → Fila de discovery** com estado, lease, tentativa, erro, páginas e objetos do último checkpoint. Ele persiste no máximo dez páginas por transação e limita a listagem a dez chamadas de API por segundo; se a AWS responder `SlowDown` após a tentativa interna do SDK, aplica espera exponencial e repete o mesmo cursor, sem pular chaves. Para uma base existente com milhões de objetos, execute uma vez, em janela operacional, `sudo /opt/s3-oci-migration/release/scripts/create-discovery-indexes.sh`. O script usa `CREATE INDEX CONCURRENTLY`, portanto não bloqueia leituras/escritas normais, mas consome I/O enquanto estiver em execução.

Para S3 Inventory grande, escolha **Usar arquivo de inventário** e informe o URI `s3://.../manifest.json`. O Raijin enfileira a importação e lê o manifesto e todos os shards CSV/GZIP diretamente pelo worker, sem transferir dezenas de GB pelo navegador ou pelo túnel SSH. O checkpoint contém índice do shard e número de linhas confirmado; uma retomada relê somente o shard atual até o último lote confirmado. A migration role da conexão deve ter `s3:GetObject` no bucket/prefixo de entrega do S3 Inventory, além das permissões da source. O manifesto precisa declarar `sourceBucket` igual ao bucket da source e incluir o schema `Key, Size`.

Em caso de desligamento, reinicie `s3-oci-migration.service`. PostgreSQL mantém inventário, fila, leases e evidências; tarefas com lease expirado são reassumidas pelo worker. Para uploads grandes, o `upload_id` multipart OCI e as partes já aceitas ficam no PostgreSQL: após reinício, o worker consulta essas partes e envia somente as faltantes. Discovery persiste, de forma atômica, o inventário e o checkpoint a cada até dez páginas S3; após uma interrupção, retoma sem relistar páginas confirmadas e pode repetir no máximo nove páginas ainda não confirmadas. O backup lógico diário é complementar ao backup de volume OCI; siga o [runbook de recuperação](recovery-runbook.md) para testar ou executar uma restauração controlada.

## Componentes instalados e retenção de backup

O procedimento de instalação de release está na seção
[Materializar uma release imutável](#3-materializar-uma-release-imutável).
O bootstrap constrói a imagem com Podman no host; portanto, a primeira
instalação exige acesso aos registries e dependências declarados acima.

Na Oracle Linux, o bootstrap utiliza Podman nativo e registra `s3-oci-migration.service` no systemd. Os containers `s3-oci-postgres` e `s3-oci-app` usam volumes persistentes no boot volume. A API é publicada em `127.0.0.1:1604` por padrão e pode ser ajustada em `web-bind.env`.

O timer `s3-oci-backup-postgres.timer` executa diariamente às 02:15 UTC um `pg_dump` dos bancos real e simulado e conserva 35 dias por padrão. Esse prazo cobre a quarentena padrão de 30 dias do simulador. Ele pode ser ampliado com `RAIJIN_LOGICAL_BACKUP_RETENTION_DAYS` no serviço systemd, mas nunca reduzido abaixo de 30 dias. Isso complementa, mas não substitui, a policy automática de backup do boot volume.
