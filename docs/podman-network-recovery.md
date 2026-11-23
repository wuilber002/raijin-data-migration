# Recuperação do encaminhamento de porta Podman

## Sintoma

Depois de alterar o endpoint da console para HTTPS e um IP não-loopback, a VM
pode apresentar um listener em `0.0.0.0:1604`, mas uma conexão TLS não recebe
resposta. Os sinais característicos são:

```bash
sudo ss -ltnp | grep ':1604'
curl -vk --connect-timeout 5 https://127.0.0.1:1604/healthz
```

O primeiro mostra `conmon` em escuta e o segundo expira depois do
`Client hello`. Se o teste direto dentro do container funcionar, o problema é
o encaminhamento de porta da rede Podman, não o certificado, a aplicação ou
as regras OCI:

```bash
sudo podman exec raijin-app python3 -c \
"import ssl, urllib.request; ctx=ssl._create_unverified_context(); print(urllib.request.urlopen('https://127.0.0.1:8080/healthz', context=ctx, timeout=5).read().decode())"
```

## Prevenção

O processador de endpoint verifica agora o `/healthz` no bind publicado após
cada mudança. Se a verificação falhar, ele restaura a configuração anterior e
informa a falha na console. Ele não recria a rede automaticamente, pois isso
interromperia workers e conexões em andamento.

## Recuperação controlada

Execute este procedimento somente em uma janela aprovada e após drenar a fila.
Ele não remove PostgreSQL, dados persistentes, configurações ou Secrets, mas
reinicia todos os containers Raijin e encerra sessões web.

```bash
sudo systemctl stop raijin-data-migration.service
sudo podman network rm raijin-data-migration
sudo systemctl start raijin-data-migration.service
sudo systemctl is-active raijin-data-migration.service
curl -vk --connect-timeout 10 https://127.0.0.1:1604/healthz
```

Se o endpoint for interno, valide também pelo IP privado da VNIC e então de
uma estação autorizada. A porta externa é `1604`; nunca publique a porta
interna do container, `8080`.
