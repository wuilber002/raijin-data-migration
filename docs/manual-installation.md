# Instalação manual do Raijin

O instalador manual cria uma instalação limpa de **Raijin Data Migration** sem
Terraform. Ele instala apenas a topologia de produção: PostgreSQL, API,
Raikō::Shin, Raikō::Sei, Raikō::Kō, Raikō::Kai e Raiju. Fujin é um produto
separado e nunca é iniciado, atualizado ou parado por este procedimento.

## Pré-requisitos

- Oracle Linux ou host compatível com `systemd`, `podman`, `git`, `python3` e
  `curl`;
- um checkout Git do Raijin disponível no host;
- um arquivo root-readable, não vazio, contendo somente a senha do PostgreSQL.

## Instalação

Execute a partir do checkout, como `root` (ou via `sudo`):

```bash
sudo scripts/install-raijin.sh \
  --postgres-password-file /root/secrets/raijin-postgres-password
```

O script clona a revisão atual em
`/opt/raijin-data-migration/release`, grava a referência local do segredo em
`/etc/raijin-data-migration/oci-runtime.json`, cria os dados em
`/var/lib/raijin-data-migration` e ativa
`raijin-data-migration.service`. A console fica restrita a
`http://127.0.0.1:1604` por padrão.

Para substituir uma instalação existente, a remoção explícita é obrigatória:

```bash
sudo scripts/install-raijin.sh \
  --clean \
  --postgres-password-file /root/secrets/raijin-postgres-password
```

`--clean` remove exclusivamente diretórios, containers e unidades systemd
com o namespace `raijin-data-migration`; isso inclui o banco local e seus
backups. Preserve-os antes de usar essa opção.

Depois da instalação, configure conexões AWS e OCI pela console. Para usar um
Fujin de laboratório, cadastre seus endpoints privados como conexões AWS/OCI
normais; não há perfil, volume nem processo Fujin dentro da instalação Raijin.
