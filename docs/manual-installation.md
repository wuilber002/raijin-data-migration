# Instalação manual do Raijin

O instalador automático cria uma instalação limpa de **Raijin Data Migration** sem
Terraform. Ele instala apenas a topologia de produção: PostgreSQL, API,
Raikō::Shin, Raikō::Sei, Raikō::Kō, Raikō::Kai e Raiju. separado é um produto
separado e nunca é iniciado, atualizado ou parado por este procedimento.

## Pré-requisitos

- Oracle Linux/RHEL ou Debian/Ubuntu com `systemd`;
- um checkout Git do Raijin disponível no host;

## Instalação

Execute a partir do checkout, como `root` (ou via `sudo`):

```bash
sudo scripts/install-raijin.sh
```

O checkout usado para executar o instalador pode ficar em `/tmp` e ser
removido após o término. O release instalado sempre configura o remoto de
atualização como `https://github.com/wuilber002/raijin-data-migration.git`,
não como o caminho local do checkout. Para uma distribuição espelhada, informe
explicitamente o remoto HTTPS canônico:

```bash
sudo scripts/install-raijin.sh \
  --update-repository 'https://github.example.com/organizacao/raijin-data-migration.git'
```

O repositório configurado precisa estar acessível sem interação pelo usuário
`root`, pois o verificador de atualização é executado por systemd. Para o
repositório público oficial, basta DNS e saída HTTPS para GitHub.

Para uma instalação já preparada para OCI, passe o arquivo de metadados de
runtime (ele contém OCIDs, namespace, Dynamic Group e buckets esperados, mas
**nunca** valores de Secrets):

```bash
sudo scripts/install-raijin.sh \
  --oci-runtime-config /root/raijin-oci-runtime.json
```

O script clona a revisão atual em
`/opt/raijin-data-migration/release`, grava a referência local do segredo em
`/etc/raijin-data-migration/oci-runtime.json`, cria os dados em
`/var/lib/raijin-data-migration` e ativa
`raijin-data-migration.service`. A console fica restrita a
`http://127.0.0.1:1604` por padrão.

O procedimento completo do instalador é: instala dependências, copia a revisão
imutável, gera e protege a senha do PostgreSQL, gera a senha temporária forte
do administrador, grava a configuração, executa o bootstrap, cria/ativa os
serviços e timers, aguarda o health check local e executa a pré-validação IAM.
Não há passo manual de bootstrap ou de inicialização de containers depois dele.

Em uma instalação limpa, o instalador gera senhas aleatórias fortes para o
PostgreSQL e para o primeiro administrador. Ambas ficam em arquivos de
propriedade de `root`, com permissão `0600`; a senha do PostgreSQL nunca é
mostrada. A senha temporária do administrador é exibida somente no término
bem-sucedido do instalador. Entre pelo túnel SSH como `admin`, troque-a e crie
o seu usuário administrativo. A plataforma então remove a senha temporária.

Para fornecer arquivos de segredo já existentes, use
`--postgres-password-file` e/ou `--console-bootstrap-password-file`; esses
arquivos não são impressos pelo instalador.

Em Oracle Linux/RHEL e Debian/Ubuntu, `podman`, `git`, `python3` e `curl` são
instalados automaticamente quando estiverem ausentes.

Ao final de uma instalação iniciada, o instalador sempre grava e exibe o
relatório sem segredos em `/var/lib/raijin-data-migration/oci-iam-preflight.json`.
Ele separa permissões efetivamente liberadas/bloqueadas (Instance Principal,
Vault e buckets OCI) das declarações de Dynamic Group e policy. A inspeção de
IAM é opcional por desenho: `UNKNOWN` significa que a VM não pode listar IAM,
não que a policy esteja ausente. O relatório continua exibindo os statements
necessários para criação ou correção.

Para executar somente essa validação em uma instalação já em funcionamento,
sem reinstalar, reiniciar ou alterar a VM:

```bash
sudo scripts/install-raijin.sh --iam-only
```

Esse modo retorna código `0` quando as permissões efetivas necessárias estão
liberadas e `3` quando há bloqueio ou configuração pendente; ele ainda imprime
o relatório completo nos dois casos.

O mesmo relatório está em **Configurações → OCI → Validar IAM OCI**.

Para substituir uma instalação existente, a remoção explícita é obrigatória:

```bash
sudo scripts/install-raijin.sh --clean
```

`--clean` remove exclusivamente diretórios, containers e unidades systemd
com o namespace `raijin-data-migration`; isso inclui o banco local e seus
backups. Preserve-os antes de usar essa opção.

Depois da instalação, configure conexões AWS e OCI pela console. Para usar um
separado de operação, cadastre seus endpoints privados como conexões AWS/OCI
normais; não há perfil, volume nem processo separado dentro da instalação Raijin.
