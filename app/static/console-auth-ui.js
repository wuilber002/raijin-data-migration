(() => {
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  const apiCall = (...args) => window.api ? window.api(...args) : Promise.reject(new Error("Console API is not ready"));
  const uiText = (value, options) => window.t ? window.t(value, options) : value;
  const localTime = value => value ? new Date(value).toLocaleString(window.raijinLocale?.() || "pt-BR") : "—";
  const roleRank = {VIEWER: 1, OPERATOR: 2, ADMIN: 3};
  // The migration screen builds several controls after the page is loaded
  // (waves, projects and source actions).  The API remains the authority,
  // but a VIEWER must not be invited to issue a request that is guaranteed to
  // be denied.  Keep the read-only buttons (reports, manifests, timelines)
  // available and identify only commands that can change operational state.
  const migrationMutationIds = new Set([
    "source-discovery-action", "source-validate-destination", "source-edit-action",
    "source-lifecycle-action", "create-source-action", "source-submit",
    "wave-create-submit", "waves-queue-all", "migration-project-create",
    "migration-project-archive", "migration-project-closure", "project-closure-issue",
  ]);
  const migrationMutationHandlers = /(?:openDiscoveryModal|startEditSource|removeOrDeactivateSource|openNewSourceModal|submitSelectedWaveMethod|queue(?:All)?PlannedWave|waveAction|verifyWave|deleteWave|start(?:Source)?DeepAudit|toggleDeepAuditQueue|reprocessModifiedDiscoveryObjects|openMigrationProjectCreateModal|openProjectClosureModal)/;
  const markMigrationMutationControls = root => {
    root?.querySelectorAll?.("button, input[type=submit]").forEach(control => {
      const handler = control.getAttribute("onclick") || "";
      if (migrationMutationIds.has(control.id) || migrationMutationHandlers.test(handler)) {
        control.dataset.requiredRole = "OPERATOR";
      }
    });
  };
  const applyAuthTranslations = root => {
    root.querySelectorAll?.("[data-console-i18n]").forEach(node => { node.textContent = uiText(node.dataset.consoleI18n); });
    root.querySelectorAll?.("[data-console-i18n-aria-label]").forEach(node => { node.setAttribute("aria-label", uiText(node.dataset.consoleI18nAriaLabel)); });
    root.querySelectorAll?.("[data-console-i18n-title]").forEach(node => { node.title = uiText(node.dataset.consoleI18nTitle); });
    root.querySelectorAll?.("[data-console-i18n-placeholder]").forEach(node => { node.placeholder = uiText(node.dataset.consoleI18nPlaceholder); });
  };
  const applyRoleControls = role => {
    const currentRank = roleRank[role] || 0;
    document.querySelectorAll("[data-required-role]").forEach(control => {
      const permitted = currentRank >= (roleRank[control.dataset.requiredRole] || Infinity);
      if (control.dataset.hideWhenDenied !== undefined) {
        control.classList.toggle("hidden", !permitted);
        return;
      }
      if ("disabled" in control) control.disabled = !permitted;
      control.setAttribute("aria-disabled", String(!permitted));
    });
  };
  const installAdminSecurityAlerts = () => {
    const baseRenderTopAlerts = window.renderTopAlerts;
    if (typeof baseRenderTopAlerts !== "function") return;
    let securityAlerts = [];
    let operationalAlerts = [];
    window.renderTopAlerts = alerts => {
      operationalAlerts = Array.isArray(alerts) ? alerts : [];
      baseRenderTopAlerts([...operationalAlerts, ...securityAlerts]);
    };
    const message = (data, key) => {
      const en = window.raijinLocale?.() === "en-US";
      const minutes = Math.max(1, Math.round(Number(data.window_seconds || 0) / 60));
      if (key === "bootstrap") return en
        ? "Administrative authentication bootstrap requires host intervention."
        : "O bootstrap da autenticação administrativa requer intervenção no host.";
      if (key === "lockout") return en
        ? `${data.active_lockouts} origin(s) are temporarily rate-limited after login attempts.`
        : `${data.active_lockouts} origem(ns) está(ão) temporariamente bloqueada(s) por tentativas de login.`;
      if (key === "login") return en
        ? `${data.failed_logins} denied login attempt(s) in the last ${minutes} minutes.`
        : `${data.failed_logins} tentativa(s) de login negada(s) nos últimos ${minutes} minutos.`;
      return en
        ? `${data.authorization_denied} denied console access attempt(s) in the last ${minutes} minutes.`
        : `${data.authorization_denied} tentativa(s) de acesso à console negada(s) nos últimos ${minutes} minutos.`;
    };
    const refreshSecurityAlerts = async () => {
      try {
        const data = await apiCall("/api/admin/auth-security-summary");
        const alerts = [];
        if (data.bootstrap_required) alerts.push(["auth-bootstrap", "bad", message(data, "bootstrap")]);
        if (Number(data.active_lockouts || 0)) alerts.push(["auth-lockout", "bad", message(data, "lockout")]);
        if (Number(data.failed_logins || 0) >= 5) alerts.push(["auth-login-failures", "warning", message(data, "login")]);
        if (Number(data.authorization_denied || 0) >= Number(data.denied_alert_threshold || 5)) {
          alerts.push(["auth-authorization-denied", "warning", message(data, "denied")]);
        }
        securityAlerts = alerts;
        window.renderTopAlerts(operationalAlerts);
      } catch (_) {
        // The regular dashboard health path remains independent from this
        // ADMIN-only enhancement, so a transient summary read never disrupts
        // monitoring for the console.
      }
    };
    refreshSecurityAlerts();
    setInterval(() => { if (document.visibilityState !== "hidden") refreshSecurityAlerts(); }, 60_000);
    document.addEventListener("raijin:language-changed", refreshSecurityAlerts);
  };
  const installAdminActiveSessionSummary = () => {
    let sessions = [];
    const modal = document.createElement("section");
    modal.id = "console-active-sessions-modal";
    modal.className = "modal hidden";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "console-active-sessions-title");
    modal.innerHTML = `
      <div class="modal-panel console-profile-panel console-active-sessions-panel">
        <div class="modal-header"><h2 id="console-active-sessions-title" data-console-i18n="Sessões autenticadas"></h2><button type="button" class="secondary" data-close-active-sessions data-console-i18n="Fechar"></button></div>
        <p class="hint" data-console-i18n="Somente administradores podem visualizar ou revogar sessões autenticadas ativas."></p>
        <div id="console-active-sessions-content" class="report-content"></div>
      </div>`;
    document.body.append(modal);
    applyAuthTranslations(modal);
    const content = modal.querySelector("#console-active-sessions-content");
    const close = () => {
      if (window.closeModal) window.closeModal("#console-active-sessions-modal");
      else modal.classList.add("hidden");
    };
    modal.querySelector("[data-close-active-sessions]").addEventListener("click", close);
    const renderModal = () => {
      const empty = uiText("Nenhuma sessão autenticada ativa.");
      content.innerHTML = sessions.length ? `<table><thead><tr><th>${uiText("Usuário")}</th><th>${uiText("Papel")}</th><th>${uiText("Última atividade")}</th><th>${uiText("Expira em")}</th><th>${uiText("Ação")}</th></tr></thead><tbody>${sessions.map(item => `<tr><td>${escapeHtml(item.username)}${item.is_current?` <small>(${uiText("sessão atual")})</small>`:""}</td><td>${escapeHtml(item.role)}</td><td>${localTime(item.last_seen_at)}</td><td>${localTime(item.expires_at)}</td><td><button type="button" class="danger" data-revoke-active-session="${Number(item.id)}" data-current-session="${item.is_current?"true":"false"}">${uiText("Revogar")}</button></td></tr>`).join("")}</tbody></table>` : `<p class="hint">${empty}</p>`;
      content.querySelectorAll("[data-revoke-active-session]").forEach(button => button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await apiCall(`/api/admin/sessions/${button.dataset.revokeActiveSession}/revoke`, {method:"POST"});
          if (button.dataset.currentSession === "true") {
            sessionStorage.removeItem("raijin_csrf");
            location.assign("/login");
            return;
          }
          await refreshActiveSessions();
          renderModal();
        } catch (error) { button.disabled = false; content.insertAdjacentHTML("afterbegin", `<p class="error">${escapeHtml(error.message)}</p>`); }
      }));
    };
    const decorateHealthCard = () => {
      const card = document.querySelector("#health .platform-health-metric:nth-child(2)");
      const detail = card?.querySelector(".platform-health-secondary");
      if (!detail) return;
      const en = window.raijinLocale?.() === "en-US";
      const label = en ? `${sessions.length} authenticated session(s)` : `${sessions.length} sessão(ões) autenticada(s)`;
      detail.replaceChildren(document.createTextNode(`${label} · `));
      const link = document.createElement("button");
      link.type = "button";
      link.className = "console-active-sessions-link";
      link.textContent = en ? "Manage" : "Gerenciar";
      link.addEventListener("click", async () => {
        await refreshActiveSessions();
        renderModal();
        if (window.openModal) window.openModal("#console-active-sessions-modal");
        else modal.classList.remove("hidden");
      });
      detail.append(link);
      detail.title = en
        ? "Authenticated sessions are visible only to administrators. The console heartbeat count remains anonymous."
        : "Sessões autenticadas são visíveis somente para administradores. A contagem de heartbeat da console continua anônima.";
    };
    const refreshActiveSessions = async () => {
      try { sessions = await apiCall("/api/admin/active-sessions"); decorateHealthCard(); }
      catch (_) { /* This ADMIN-only detail must not affect platform health. */ }
    };
    const health = document.getElementById("health");
    // loadHealth replaces direct health cards in one operation. Observing the
    // entire subtree would also observe detail.textContent above and recurse
    // synchronously on our own decoration, freezing the browser.
    if (health) new MutationObserver(decorateHealthCard).observe(health, {childList:true});
    refreshActiveSessions();
    setInterval(() => { if (document.visibilityState !== "hidden") refreshActiveSessions(); }, 60_000);
    document.addEventListener("raijin:language-changed", () => { applyAuthTranslations(modal); decorateHealthCard(); renderModal(); });
  };

  async function install() {
    // Authentication controls are injected after the application shell. Wait
    // for its catalog so their first rendering already uses the selected
    // locale instead of depending on mutation-observer timing.
    try { await window.raijinI18nReady; } catch (_) { /* fallback to Portuguese source strings */ }
    let identity;
    try { identity = await apiCall("/api/auth/me"); } catch (_) { return; }
    if (!identity.enabled) return;
    window.raijinConsoleRole = identity.user.role;
    markMigrationMutationControls(document);
    applyRoleControls(identity.user.role);
    const migrations = document.getElementById("view-migrations");
    if (migrations) {
      // Wave/project refreshes replace their rows in a single DOM update.
      // Reapply the client-side affordance only to newly inserted controls;
      // no network call or layout-wide polling is involved.
      new MutationObserver(records => {
        for (const record of records) {
          for (const node of record.addedNodes) {
            if (node.nodeType !== Node.ELEMENT_NODE) continue;
            markMigrationMutationControls(node);
            if (node.matches?.("button, input[type=submit]")) markMigrationMutationControls(node.parentElement);
          }
        }
        applyRoleControls(identity.user.role);
      }).observe(migrations, {childList:true, subtree:true});
    }
    const actions = document.querySelector(".banner-actions");
    const userMenu = document.createElement("div");
    userMenu.className = "console-user-menu";
    const userMenuTrigger = document.createElement("button");
    userMenuTrigger.type = "button";
    userMenuTrigger.className = "secondary console-user-menu-trigger";
    userMenuTrigger.dataset.consoleI18nAriaLabel = "Menu do usuário";
    userMenuTrigger.setAttribute("aria-haspopup", "menu");
    userMenuTrigger.setAttribute("aria-expanded", "false");
    userMenuTrigger.dataset.consoleI18nTitle = "Menu do usuário";
    userMenuTrigger.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a4.25 4.25 0 1 0 0-8.5 4.25 4.25 0 0 0 0 8.5Zm0 2.1c-4.48 0-8.1 2.18-8.1 4.87V21h16.2v-2.03c0-2.69-3.62-4.87-8.1-4.87Z"/></svg>';
    const userMenuPanel = document.createElement("div");
    userMenuPanel.className = "console-user-menu-panel hidden";
    userMenuPanel.setAttribute("role", "menu");
    userMenuPanel.setAttribute("aria-label", uiText("Ações do usuário"));
    const userIdentity = document.createElement("div");
    userIdentity.className = "console-user-menu-identity";
    userIdentity.textContent = identity.user.username;
    userIdentity.setAttribute("role", "presentation");
    const profile = document.createElement("button");
    profile.type = "button"; profile.className = "console-user-menu-action";
    profile.dataset.consoleI18n = "Meu perfil";
    profile.setAttribute("role", "menuitem");
    const logout = document.createElement("button");
    logout.type = "button"; logout.className = "console-user-menu-action";
    logout.dataset.consoleI18n = "Sair";
    logout.setAttribute("role", "menuitem");
    userMenuPanel.append(userIdentity, profile, logout);
    userMenu.append(userMenuTrigger, userMenuPanel);
    applyAuthTranslations(userMenu);
    actions?.append(userMenu);
    const closeUserMenu = () => {
      userMenuPanel.classList.add("hidden");
      userMenuTrigger.setAttribute("aria-expanded", "false");
    };
    userMenuTrigger.addEventListener("click", event => {
      event.stopPropagation();
      const willOpen = userMenuPanel.classList.contains("hidden");
      userMenuPanel.classList.toggle("hidden", !willOpen);
      userMenuTrigger.setAttribute("aria-expanded", String(willOpen));
    });
    document.addEventListener("click", event => { if (!userMenu.contains(event.target)) closeUserMenu(); });
    document.addEventListener("keydown", event => { if (event.key === "Escape") closeUserMenu(); });
    logout.addEventListener("click", async () => {
      closeUserMenu();
      try { await apiCall("/api/auth/logout", {method:"POST"}); }
      finally { location.assign("/login"); }
    });
    const profileModal = document.createElement("section");
    profileModal.id = "console-profile-modal";
    profileModal.className = "modal hidden";
    profileModal.setAttribute("role", "dialog");
    profileModal.setAttribute("aria-modal", "true");
    profileModal.setAttribute("aria-labelledby", "console-profile-title");
    profileModal.innerHTML = `
      <div class="modal-panel console-profile-panel">
        <div class="modal-header"><h2 id="console-profile-title" data-console-i18n="Meu perfil"></h2><button type="button" class="secondary" data-close-profile data-console-i18n="Fechar"></button></div>
        <p class="hint" data-console-i18n="Atualize somente seus próprios dados. O usuário é gerenciado pelo administrador."></p>
        <form id="console-profile-form" class="grid">
          <label class="field"><span data-console-i18n="Usuário"></span><input name="username" disabled aria-describedby="console-profile-username-help"><small id="console-profile-username-help" class="hint" data-console-i18n="Este dado não pode ser alterado."></small></label>
          <label class="field"><span data-console-i18n="Nome"></span><input name="display_name" maxlength="128" autocomplete="name"></label>
          <label class="field"><span data-console-i18n="E-mail"></span><input name="email" type="email" maxlength="320" autocomplete="email"></label>
          <div class="field action"><span class="field-label" data-console-i18n="Dados pessoais"></span><button data-console-i18n="Salvar perfil"></button></div>
        </form>
        <hr>
        <h3 data-console-i18n="Trocar senha"></h3>
        <form id="console-password-form" class="grid">
          <label class="field"><span data-console-i18n="Senha atual"></span><input name="current_password" type="password" autocomplete="current-password" required></label>
          <label class="field"><span data-console-i18n="Nova senha"></span><input name="new_password" type="password" minlength="14" autocomplete="new-password" required></label>
          <label class="field"><span data-console-i18n="Confirmar nova senha"></span><input name="confirmation" type="password" minlength="14" autocomplete="new-password" required></label>
          <div class="field action"><span class="field-label" data-console-i18n="Segurança"></span><button data-console-i18n="Trocar senha"></button></div>
        </form>
        <p id="console-profile-message" class="hint" role="status"></p>
      </div>`;
    document.body.append(profileModal);
    applyAuthTranslations(profileModal);
    let profileMessageSource = "";
    const profileMessage = value => {
      profileMessageSource = value || "";
      profileModal.querySelector("#console-profile-message").textContent = profileMessageSource ? uiText(profileMessageSource) : "";
    };
    const openProfile = async () => {
      profileMessage("");
      const data = await apiCall("/api/auth/profile");
      const form = profileModal.querySelector("#console-profile-form");
      ["username", "display_name", "email"].forEach(field => { form.elements[field].value = data[field] || ""; });
      if (window.openModal) window.openModal("#console-profile-modal"); else profileModal.classList.remove("hidden");
    };
    profile.addEventListener("click", () => {
      closeUserMenu();
      openProfile().catch(error => profileMessage(error.message));
    });
    profileModal.querySelector("[data-close-profile]").addEventListener("click", () => {
      if (window.closeModal) window.closeModal("#console-profile-modal"); else profileModal.classList.add("hidden");
    });
    profileModal.querySelector("#console-profile-form").addEventListener("submit", async event => {
      event.preventDefault(); const form = event.currentTarget;
      try {
        await apiCall("/api/auth/profile", {method:"PATCH", headers:{"content-type":"application/json"}, body:JSON.stringify({display_name:form.display_name.value, email:form.email.value})});
        profileMessage("Perfil atualizado.");
      } catch (error) { profileMessage(error.message); }
    });
    profileModal.querySelector("#console-password-form").addEventListener("submit", async event => {
      event.preventDefault(); const form = event.currentTarget;
      if (form.new_password.value !== form.confirmation.value) { profileMessage("As novas senhas não coincidem."); return; }
      try {
        const result = await apiCall("/api/auth/password", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({current_password:form.current_password.value, new_password:form.new_password.value})});
        if (result.csrf_token) sessionStorage.setItem("raijin_csrf", result.csrf_token);
        form.reset(); profileMessage("Senha alterada. As demais sessões foram encerradas.");
      } catch (error) { profileMessage(error.message); }
    });
    document.addEventListener("raijin:language-changed", () => {
      applyAuthTranslations(userMenu);
      applyAuthTranslations(profileModal);
      userMenuPanel.setAttribute("aria-label", uiText("Ações do usuário"));
      profileMessage(profileMessageSource);
    });
    if (identity.user.role !== "ADMIN") {
      // Settings contains only tenancy integration and global scheduling
      // controls. Do not make an OPERATOR/VIEWER discover administrative
      // integration blocks that the server must correctly deny anyway.
      document.querySelector('[data-view="settings"]')?.classList.add("hidden");
      document.querySelector('.gear[data-required-role="ADMIN"]')?.classList.add("hidden");
      if (document.getElementById("view-settings")?.classList.contains("active")) {
        window.showView?.("dashboard");
      }
      // An initial settings route can start its asynchronous loaders before
      // this identity check completes. Later route/language refreshes must
      // not issue those administrative reads at all.
      ["loadOciBuckets", "loadAwsConnections", "loadAwsSecrets"].forEach(name => {
        if (typeof window[name] === "function") window[name] = async () => {};
      });
      return;
    }

    installAdminSecurityAlerts();
    installAdminActiveSessionSummary();

    const settings = document.getElementById("view-settings");
    if (!settings) return;
    const card = document.createElement("section");
    card.className = "card"; card.id = "console-access-management";
    card.innerHTML = `
      <h2 data-console-i18n="Acesso ao console"></h2>
      <p class="hint" data-console-i18n="Usuários locais, sessões ativas no navegador e evidências de auditoria de autenticação."></p>
      <form id="console-auth-policy" class="row">
        <label class="field"><span data-console-i18n="Histórico de reutilização de senha"></span><input name="password_history_count" type="number" min="0" max="12" required></label>
        <span class="hint" data-console-i18n="Bloqueia a senha atual e esta quantidade de senhas anteriores (padrão: 3)."></span>
        <button data-console-i18n="Salvar política"></button>
      </form>
      <form id="console-create-user" class="row">
        <label class="field"><span data-console-i18n="Usuário"></span><input name="username" pattern="[a-z][a-z0-9_.-]{2,63}" required></label>
        <label class="field"><span data-console-i18n="Senha temporária"></span><input name="password" type="password" minlength="14" required></label>
        <label class="field"><span data-console-i18n="Papel"></span><select name="role"><option>VIEWER</option><option>OPERATOR</option><option>ADMIN</option></select></label>
        <button data-console-i18n="Criar usuário"></button>
      </form>
      <div id="console-users" class="report-content" data-console-i18n="Carregando usuários…"></div>
      <h3 data-console-i18n="Sessões"></h3><div id="console-sessions" class="report-content" data-console-i18n="Carregando sessões…"></div>
      <h3 data-console-i18n="Auditoria recente de autenticação"></h3>
      <form id="console-audit-filter" class="row">
        <label class="field"><span data-console-i18n="Responsável"></span><input name="actor" pattern="[a-z][a-z0-9_.-]{2,63}"></label>
        <label class="field"><span data-console-i18n="Evento"></span><input name="event_type" placeholder="LOGIN_SUCCEEDED"></label>
        <label class="field"><span data-console-i18n="Resultado"></span><select name="result"><option value="" data-console-i18n="Todos"></option><option>SUCCEEDED</option><option>DENIED</option></select></label>
        <button class="secondary" data-console-i18n="Filtrar"></button>
      </form>
      <div id="console-auth-audit" class="report-content" data-console-i18n="Carregando auditoria…"></div>`;
    settings.append(card);
    applyAuthTranslations(card);

    const auditQuery = () => {
      const form = card.querySelector("#console-audit-filter");
      const query = new URLSearchParams();
      ["actor", "event_type", "result"].forEach(name => {
        const value = form.elements[name].value.trim(); if (value) query.set(name, value);
      });
      return query.toString() ? `?${query}` : "";
    };
    const render = async () => {
      const [users, sessions, audit, authSettings] = await Promise.all([
        apiCall("/api/admin/users"), apiCall("/api/admin/sessions"),
        apiCall(`/api/admin/auth-audit${auditQuery()}`),
        apiCall("/api/admin/auth-settings"),
      ]);
      const auditEventLabel = row => row.event_type === "USER_CREATED" && row.target
        ? `${row.event_type} (${row.target})` : row.event_type;
      card.querySelector("#console-auth-policy").elements.password_history_count.value = authSettings.password_history_count;
      card.querySelector("#console-users").innerHTML = `<table><thead><tr><th>${uiText("Usuário")}</th><th>${uiText("Papel")}</th><th>${uiText("Ativo")}</th><th>${uiText("Redefinir senha")}</th><th>${uiText("Ação")}</th></tr></thead><tbody>${users.map(user => `<tr data-user="${user.id}"><td>${escapeHtml(user.username)}${user.must_change_password?` · ${uiText("troca de senha obrigatória")}`:""}</td><td><select data-field="role">${["VIEWER","OPERATOR","ADMIN"].map(role => `<option${role===user.role?" selected":""}>${role}</option>`).join("")}</select></td><td><input data-field="enabled" type="checkbox"${user.enabled?" checked":""} aria-label="${escapeHtml(uiText("Ativar {{username}}", {username:user.username}))}"></td><td><input data-field="password" type="password" minlength="14" placeholder="${escapeHtml(uiText("Opcional"))}"></td><td><button type="button" data-save-user="${user.id}">${uiText("Salvar")}</button></td></tr>`).join("")}</tbody></table>`;
      card.querySelector("#console-sessions").innerHTML = `<table><thead><tr><th>${uiText("Usuário")}</th><th>${uiText("Última atividade")}</th><th>${uiText("Expira em")}</th><th>${uiText("Ação")}</th></tr></thead><tbody>${sessions.map(row => `<tr><td>${escapeHtml(row.username)}</td><td>${localTime(row.last_seen_at)}</td><td>${localTime(row.expires_at)}</td><td>${row.revoked_at?`${uiText("Revogada")} (${escapeHtml(row.revoke_reason||"")})`:`<button type="button" data-session="${row.id}">${uiText("Revogar")}</button>`}</td></tr>`).join("")}</tbody></table>`;
      card.querySelector("#console-auth-audit").innerHTML = `<table><thead><tr><th>${uiText("Data e hora")}</th><th>${uiText("Responsável")}</th><th>${uiText("Evento")}</th><th>${uiText("Resultado")}</th></tr></thead><tbody>${audit.map(row => `<tr><td>${localTime(row.created_at)}</td><td>${escapeHtml(row.actor||uiText("sistema"))}</td><td>${escapeHtml(auditEventLabel(row))}</td><td>${escapeHtml(row.result)}</td></tr>`).join("")}</tbody></table>`;
      card.querySelectorAll("[data-session]").forEach(button => button.addEventListener("click", async () => {
        await apiCall(`/api/admin/sessions/${button.dataset.session}/revoke`, {method:"POST"}); await render();
      }));
      card.querySelectorAll("[data-save-user]").forEach(button => button.addEventListener("click", async () => {
        const row = button.closest("tr");
        const password = row.querySelector('[data-field="password"]').value;
        const payload = {role:row.querySelector('[data-field="role"]').value, enabled:row.querySelector('[data-field="enabled"]').checked};
        if (password) payload.password = password;
        await apiCall(`/api/admin/users/${button.dataset.saveUser}`, {method:"PATCH", headers:{"content-type":"application/json"}, body:JSON.stringify(payload)});
        await render();
      }));
    };
    card.querySelector("#console-create-user").addEventListener("submit", async event => {
      event.preventDefault(); const form = event.currentTarget;
      await apiCall("/api/admin/users", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({username:form.username.value, password:form.password.value, role:form.role.value})});
      form.reset(); await render();
    });
    card.querySelector("#console-auth-policy").addEventListener("submit", async event => {
      event.preventDefault(); const form = event.currentTarget;
      await apiCall("/api/admin/auth-settings", {method:"PUT", headers:{"content-type":"application/json"}, body:JSON.stringify({password_history_count:Number(form.password_history_count.value)})});
      await render();
    });
    card.querySelector("#console-audit-filter").addEventListener("submit", async event => { event.preventDefault(); await render(); });
    document.addEventListener("raijin:language-changed", () => {
      applyAuthTranslations(card);
      render().catch(() => {});
    });
    document.addEventListener("raijin:open-auth-audit", event => {
      const form = card.querySelector("#console-audit-filter");
      if (!form) return;
      const key = event.detail?.alertKey || "";
      form.elements.actor.value = "";
      form.elements.result.value = "DENIED";
      form.elements.event_type.value = key === "auth-lockout" ? "LOGIN_RATE_LIMITED"
        : key === "auth-bootstrap" ? "BOOTSTRAP_ADMIN_CREATED" : "";
      render().then(() => card.scrollIntoView({block:"start", behavior:"smooth"})).catch(() => {});
    });
    await render();
  }
  queueMicrotask(install);
})();
