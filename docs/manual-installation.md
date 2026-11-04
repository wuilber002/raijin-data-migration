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

O script clona a revisão atual em
`/opt/raijin-data-migration/release`, grava a referência local do segredo em
`/etc/raijin-data-migration/oci-runtime.json`, cria os dados em
`/var/lib/raijin-data-migration` e ativa
`raijin-data-migration.service`. A console fica restrita a
`http://127.0.0.1:1604` por padrão.

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
