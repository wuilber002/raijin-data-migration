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

## Alteração controlada de endpoint

Uma mudança de IP, porta ou transporte da console é uma operação de
manutenção de infraestrutura — não é um simples reload. Antes de aceitar a
solicitação, a console mostra o trabalho ativo (transferências, tarefas e
discoveries) e informa que a sessão será encerrada. A confirmação é sempre
obrigatória; quando há trabalho ativo, o administrador também precisa digitar
a frase exibida pela interface.

Depois da confirmação, o agente do host executa, nesta ordem:

1. salva a configuração e o certificado anteriores;
2. grava o novo endpoint;
3. interrompe todos os containers Raijin;
4. remove e recria a rede Podman exclusiva `raijin-data-migration`;
5. inicia novamente o runtime e valida `/healthz` no endpoint publicado;
6. se houver falha, restaura configuração e certificado anteriores, recria a
   rede mais uma vez e valida o endpoint anterior.

Durante esse intervalo, a console e os workers ficam indisponíveis. A fila,
leases e checkpoints são persistentes: o runtime retoma o trabalho durável
após voltar saudável. Planeje a alteração fora de uma janela crítica sempre
que possível e reconecte-se usando o novo endereço ao final.

## Recuperação controlada

Execute este procedimento somente se a recuperação automática falhar, em uma
janela aprovada e, preferencialmente, após drenar a fila.
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
