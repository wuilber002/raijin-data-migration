# Matriz de autorização — console web do Raijin

**Estado:** baseline P0. Esta matriz descreve a política a ser aplicada em P3;
o release de compatibilidade permanece em `RAIJIN_WEB_AUTH_MODE=disabled`.

| Superfície | Rotas | Política final | Observações |
| --- | --- | --- | --- |
| Health local | `/healthz`, `/metrics` | Sem cookie, somente bind/rede local | Exclusivamente systemd e monitoramento local; nunca publicar pelo proxy. |
| Readiness cloud | `/api/readiness` | `ADMIN` | Executa validações de credenciais e conectividade; não é healthcheck público. |
| Login | `/login`, `/api/auth/login` | Pública com rate-limit | Sem redirecionamento para origem externa; respostas genéricas. |
| Sessão | `/api/auth/logout`, `/api/auth/me`, troca de senha | Usuário autenticado + CSRF nas mutações | Cookie opaco, `HttpOnly`, `SameSite=Lax`. |
| Console HTML/estáticos | `/`, `/simulation`, `/static/*` | Sessão válida, exceto ativos mínimos da tela de login | A versão inicial local não expõe a console de Simulation. |
| Consulta operacional | `GET /api/*`, CSV, relatórios e downloads | `VIEWER` | Exceto rotas explicitamente administrativas ou internas nesta tabela. |
| Operação de migração | mutações de sources, discoveries, waves, queue, audit e pause/resume | `OPERATOR` | Inclui reprocessamento e ações que alteram filas ou waves. |
| Administração | runtime mode, settings, AWS/OCI connections, pricing, project lifecycle | `ADMIN` | Inclui credenciais e limites operacionais. |
| Administração de acesso | `/api/admin/users*`, `/api/admin/sessions*`, `/api/admin/auth-audit*` | `ADMIN` | Novas rotas de P2–P4. |
| Worker interno legado | `/api/tasks/claim`, `/api/tasks/*/{heartbeat,succeed,fail}`, `/api/tasks/recover` | Canal interno, não browser | P3 definirá credencial de serviço ou bloqueio de rede explícito; nunca será liberado por papel humano. |
| Presence/polling | `/api/console-presence/heartbeat`, runtime clock, status/observability | `VIEWER` | Deve falhar de maneira leve quando a sessão expirar, sem loop de UI. |

## Regras de precedência

1. Uma rota não classificada é negada por padrão quando `auth_mode=local`.
2. A autorização é sempre decidida no servidor; ocultar controles da UI é só
   uma melhoria de usabilidade.
3. A origem encaminhada (`X-Forwarded-*`) é considerada somente quando o peer
   pertence a `RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS`.
4. Workers não recebem cookie de console nem dependem de uma sessão humana.
