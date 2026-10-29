# Operação — autenticação local da console

## Ativação controlada

1. Faça o backup PostgreSQL normal e confirme que o arquivo pode ser lido.
2. Deixe o bind em `127.0.0.1` ou em rede privada. Para proxy externo, defina
   HTTPS e somente os CIDRs do proxy em `web-auth.env`.
3. Em `oci-runtime.json`, configure exatamente uma referência para
   `console_bootstrap_password`: `secret_ocids` (Vault) ou `secret_file_paths`
   (arquivo root-owned `0600`).
4. Em `/etc/s3-oci-migration/web-auth.env`, configure
   `RAIJIN_WEB_AUTH_MODE=local` e o usuário bootstrap em letras minúsculas.
5. Materialize a referência e valide sem escrever usuários:

   ```bash
   sudo /opt/s3-oci-migration/release/scripts/fetch-oci-secret.py \
     --runtime-config /etc/s3-oci-migration/oci-runtime.json \
     --secret-name console_bootstrap_password \
     --output /etc/s3-oci-migration/secrets/console_bootstrap_password
   sudo /usr/local/sbin/raijin-console-auth-preflight
   ```

6. Reinicie `sudo systemctl restart s3-oci-migration.service`. Entre com o
   administrador bootstrap, troque a senha obrigatória e crie
   contas individuais `ADMIN`, `OPERATOR` e `VIEWER`.
   Em **Settings → Console access**, mantenha a política de reutilização em
   `3` (padrão), salvo uma exigência formal diferente. A política sempre
   bloqueia a senha atual e também a quantidade configurada de senhas
   anteriores (0–12); somente hashes Argon2id dessas senhas anteriores são
   mantidos.
7. Confirme que uma janela anônima recebe `401` da API e que um `VIEWER` não
   consegue executar uma mutação. Registre o aceite.

## Perfil individual

O botão **Meu perfil** está disponível para `ADMIN`, `OPERATOR` e `VIEWER`.
Ele permite alterar o nome de exibição, e-mail e a própria senha, sem expor a
área administrativa. A troca de senha exige a senha atual, aplica a política
de histórico e revoga as demais sessões do usuário.

## Host via Bastion

O fluxo é idêntico. Mantenha `WEB_BIND_HOST=127.0.0.1` e acesse a console por
túnel SSH/Bastion; não há necessidade de proxy nem de `Secure` cookie nesse
caso. Health e métricas permanecem no mesmo bind local.

## Recuperação e rollback

Para resetar uma conta, crie uma senha temporária em arquivo root-owned `0600`
e execute `raijin-console-admin reset <usuario> --confirm`. O reset revoga as
sessões do alvo e força nova troca de senha.

Para desligar login sem remover evidência, configure
`RAIJIN_WEB_AUTH_MODE=disabled` e reinicie o serviço. Nenhuma tabela é apagada.
O retorno a `local` reutiliza as contas existentes; o arquivo bootstrap nunca
substitui um usuário já criado.

## Backup e restore

`console_users`, `console_sessions`, tentativas e auditoria pertencem ao mesmo
banco PostgreSQL dos dados de migração e entram no backup normal. Na partida
após qualquer restart ou restore, todas as sessões ativas são revogadas
(`service_restart`); usuários precisam autenticar novamente.
