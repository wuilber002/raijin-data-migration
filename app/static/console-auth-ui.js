(() => {
  // Controlled Phase 2 rollout probe: this static-only marker validates that
  // a WEB_UI_ONLY revision replaces only the web/API container.
  document.documentElement.dataset.raijinWebRolloutProbe = "phase2-web-1";
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
      content.innerHTML = sessions.length ? `<table><thead><tr><th>${uiText("Usuário")}</th><th>${uiText("Papel")}</th><th>${uiText("Última atividade")}</th><th>${uiText("Expira em")}</th><th>${uiText("Ação")}</th></tr></thead><tbody>${sessions.map(item => {
        const revoke = item.is_current
          ? `<button type="button" class="danger" disabled title="${escapeHtml(uiText("Você não pode revogar a sessão atual."))}">${uiText("Revogar")}</button>`
          : `<button type="button" class="danger" data-revoke-active-session="${Number(item.id)}">${uiText("Revogar")}</button>`;
        const disable = item.is_current_user
          ? `<button type="button" class="danger" disabled title="${escapeHtml(uiText("Você não pode desativar sua própria conta."))}">${uiText("Desativar")}</button>`
          : `<button type="button" class="danger" data-disable-active-user="${Number(item.user_id)}" data-disable-active-username="${escapeHtml(item.username)}">${uiText("Desativar")}</button>`;
        return `<tr><td>${escapeHtml(item.username)}${item.is_current?` <small>(${uiText("sessão atual")})</small>`:""}</td><td>${escapeHtml(item.role)}</td><td>${localTime(item.last_seen_at)}</td><td>${localTime(item.expires_at)}</td><td><div class="console-active-session-actions">${revoke}${disable}</div></td></tr>`;
      }).join("")}</tbody></table>` : `<p class="hint">${empty}</p>`;
      content.querySelectorAll("[data-revoke-active-session]").forEach(button => button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await apiCall(`/api/admin/sessions/${button.dataset.revokeActiveSession}/revoke`, {method:"POST"});
          await refreshActiveSessions();
          renderModal();
        } catch (error) { button.disabled = false; content.insertAdjacentHTML("afterbegin", `<p class="error">${escapeHtml(error.message)}</p>`); }
      }));
      content.querySelectorAll("[data-disable-active-user]").forEach(button => button.addEventListener("click", async () => {
        const username = button.dataset.disableActiveUsername;
        if (!window.confirm(uiText("Desativar este usuário encerrará todas as suas sessões. Continuar?", {username}))) return;
        button.disabled = true;
        try {
          await apiCall(`/api/admin/users/${button.dataset.disableActiveUser}`, {method:"PATCH", headers:{"content-type":"application/json"}, body:JSON.stringify({enabled:false})});
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
        <hr>
        <h3 data-console-i18n="Autenticação em duas etapas"></h3>
        <p class="hint" id="console-mfa-state"></p>
        <div id="console-mfa-authenticators" class="report-content"></div>
        <button type="button" id="console-mfa-start" data-console-i18n="Configurar autenticador"></button>
        <p id="console-profile-message" class="hint" role="status"></p>
      </div>`;
    document.body.append(profileModal);
    applyAuthTranslations(profileModal);
    const mfaModal = document.createElement("section");
    mfaModal.id = "console-mfa-enrollment-modal";
    mfaModal.className = "modal hidden";
    mfaModal.setAttribute("role", "dialog"); mfaModal.setAttribute("aria-modal", "true");
    mfaModal.innerHTML = `<div class="modal-panel console-mfa-enrollment-panel"><h2>RAIJIN</h2><div id="console-mfa-enrollment-body"><p class="hint" data-console-i18n="Escaneie o QR Code e confirme o código de seis dígitos do autenticador."></p><div class="console-mfa-fields"><label class="field"><span data-console-i18n="Chave de configuração"></span><input id="console-mfa-secret" readonly></label><figure class="console-mfa-qr"><img id="console-mfa-qr" alt="" width="224" height="224"></figure><label class="field"><span data-console-i18n="Código de autenticação"></span><input id="console-mfa-code" inputmode="numeric" autocomplete="one-time-code" maxlength="6"></label></div><p id="console-mfa-message" class="hint" role="status"></p></div><div id="console-mfa-complete" class="console-mfa-complete hidden" role="status"><h3 data-console-i18n="Autenticação em duas etapas ativada."></h3><p data-console-i18n="O autenticador foi configurado com sucesso para esta conta."></p><p class="warning" data-console-i18n="Guarde estes códigos de recuperação em local seguro. Eles não serão exibidos novamente."></p><code id="console-mfa-recovery-codes"></code></div><div class="console-mfa-actions"><button type="button" id="console-mfa-confirm" data-console-i18n="Ativar autenticação em duas etapas"></button><button type="button" class="secondary" data-close-mfa data-console-i18n="Cancelar"></button></div></div>`;
    document.body.append(mfaModal); applyAuthTranslations(mfaModal);
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
      profileModal.querySelector("#console-mfa-state").textContent = data.mfa_enabled ? uiText("Autenticador configurado.") : uiText("Nenhum autenticador configurado.");
      const authenticators = Array.isArray(data.mfa_authenticators) ? data.mfa_authenticators : [];
      const list = profileModal.querySelector("#console-mfa-authenticators");
      list.innerHTML = authenticators.length ? `<table><thead><tr><th>${uiText("Autenticador")}</th><th>${uiText("Último uso")}</th><th>${uiText("Ação")}</th></tr></thead><tbody>${authenticators.map(item => `<tr><td>${escapeHtml(item.label)}</td><td>${localTime(item.last_used_at)}</td><td><button type="button" class="danger" data-remove-mfa="${item.id}">${uiText("Remover")}</button></td></tr>`).join("")}</tbody></table>` : "";
      list.querySelectorAll("[data-remove-mfa]").forEach(button => button.addEventListener("click", async () => {
        if (!window.confirm(uiText("Remover este autenticador? As outras sessões serão encerradas."))) return;
        try { await apiCall(`/api/auth/mfa/authenticators/${button.dataset.removeMfa}`, {method:"DELETE"}); await openProfile(); renderAdminMfaAlert(false); }
        catch (error) { profileMessage(error.message); }
      }));
      const start = profileModal.querySelector("#console-mfa-start");
      start.disabled = authenticators.length >= 2;
      start.title = authenticators.length >= 2 ? uiText("O limite de dois autenticadores já foi atingido.") : "";
      if (window.openModal) window.openModal("#console-profile-modal"); else profileModal.classList.remove("hidden");
    };
    profile.addEventListener("click", () => {
      closeUserMenu();
      openProfile().catch(error => profileMessage(error.message));
    });
    let adminMfaAlert;
    const adminMfaAlertTop = () => window.innerWidth <= 520 ? "145px" : (window.innerWidth <= 850 ? "104px" : "78px");
    const renderAdminMfaAlert = enabled => {
      if (!adminMfaAlert) return;
      adminMfaAlert.classList.toggle("hidden", Boolean(enabled));
      adminMfaAlert.style.top = adminMfaAlertTop();
      adminMfaAlert.querySelector("span").textContent = uiText("Esta conta administrativa precisa ativar a autenticação em duas etapas.");
      adminMfaAlert.querySelector("button").textContent = uiText("Configurar autenticador");
    };
    if (identity.user.role === "ADMIN" && identity.mfa_enrollment_recommended) {
      adminMfaAlert = document.createElement("section");
      adminMfaAlert.className = "alert warning console-admin-mfa-alert";
      adminMfaAlert.setAttribute("role", "alert");
      adminMfaAlert.style.cssText = "position:fixed;z-index:29;top:78px;left:0;width:100%;margin:0;padding:.55rem max(1.4rem,calc((100vw - 1440px)/2 + 2rem));border:0;border-bottom:1px solid #f87171;border-radius:0;background:#991b1b;color:#fee2e2;box-shadow:0 5px 14px #0008;display:flex;align-items:center;justify-content:space-between;gap:.75rem;font-weight:800;";
      adminMfaAlert.innerHTML = `<span></span><button type="button" class="secondary"></button>`;
      adminMfaAlert.querySelector("button").addEventListener("click", () => openProfile().catch(error => profileMessage(error.message)));
      document.body.append(adminMfaAlert);
      renderAdminMfaAlert(false);
      window.addEventListener("resize", () => renderAdminMfaAlert(false));
    }
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
    const mfaMessage = value => { mfaModal.querySelector("#console-mfa-message").textContent = value ? uiText(value) : ""; };
    const startMfaEnrollment = async () => {
      try {
        const data = await apiCall("/api/auth/mfa/enrollment", {method:"POST"});
        mfaModal.querySelector("#console-mfa-secret").value = data.secret;
        const qr = mfaModal.querySelector("#console-mfa-qr");
        qr.src = `${data.qr_code_url}?v=${Date.now()}`;
        qr.alt = uiText("QR Code para configurar o autenticador");
        mfaMessage("Informe o código exibido no autenticador para concluir a ativação.");
      } catch (error) { mfaMessage(error.message); }
    };
    profileModal.querySelector("#console-mfa-start").addEventListener("click", () => {
      mfaModal.querySelector("#console-mfa-secret").value = "";
      mfaModal.querySelector("#console-mfa-code").value = ""; mfaModal.querySelector("#console-mfa-qr").removeAttribute("src");
      mfaModal.querySelector("#console-mfa-enrollment-body").classList.remove("hidden");
      mfaModal.querySelector("#console-mfa-complete").classList.add("hidden");
      mfaModal.querySelector("#console-mfa-confirm").classList.remove("hidden");
      const closeMfa = mfaModal.querySelector("[data-close-mfa]");
      closeMfa.dataset.consoleI18n = "Cancelar"; closeMfa.textContent = uiText("Cancelar"); mfaMessage("");
      if (window.openModal) window.openModal("#console-mfa-enrollment-modal"); else mfaModal.classList.remove("hidden");
      startMfaEnrollment();
    });
    mfaModal.querySelector("[data-close-mfa]").addEventListener("click", () => { if (window.closeModal) window.closeModal("#console-mfa-enrollment-modal"); else mfaModal.classList.add("hidden"); openProfile().catch(() => {}); });
    mfaModal.querySelector("#console-mfa-confirm").addEventListener("click", async () => {
      try {
        const code = mfaModal.querySelector("#console-mfa-code").value;
        if (!/^\d{6}$/.test(code)) { mfaMessage("Informe um código de seis dígitos."); return; }
        const data = await apiCall("/api/auth/mfa/enrollment/confirm", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({code})});
        mfaModal.querySelector("#console-mfa-recovery-codes").textContent = data.recovery_codes.join("  ");
        mfaModal.querySelector("#console-mfa-enrollment-body").classList.add("hidden");
        mfaModal.querySelector("#console-mfa-complete").classList.remove("hidden");
        mfaModal.querySelector("#console-mfa-confirm").classList.add("hidden");
        const closeMfa = mfaModal.querySelector("[data-close-mfa]");
        closeMfa.dataset.consoleI18n = "Fechar"; closeMfa.textContent = uiText("Fechar");
        renderAdminMfaAlert(true);
      } catch (error) { mfaMessage(error.message); }
    });
    document.addEventListener("raijin:language-changed", () => {
      applyAuthTranslations(userMenu);
      applyAuthTranslations(profileModal);
      applyAuthTranslations(mfaModal);
      userMenuPanel.setAttribute("aria-label", uiText("Ações do usuário"));
      profileMessage(profileMessageSource);
      if (adminMfaAlert && !adminMfaAlert.classList.contains("hidden")) renderAdminMfaAlert(false);
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
      <hr>
      <h3 data-console-i18n="Endpoint da console"></h3>
      <p class="hint" id="console-web-bind-help" data-console-i18n="HTTPS direto usa certificado autoassinado persistente. HTTP fora do loopback exige os IPs privados /32 dos terminadores TLS."></p>
      <form id="console-web-bind" class="row console-endpoint-form">
        <label class="field"><span data-console-i18n="IP de bind"></span><select name="host" required></select></label>
        <label class="field"><span data-console-i18n="Porta"></span><input name="port" type="number" min="1" max="65535" required></label>
        <label class="field"><span data-console-i18n="Transporte"></span><select name="transport"><option value="https">HTTPS</option><option value="http">HTTP</option></select></label>
        <label class="field"><span data-console-i18n="IPs confiáveis do terminador TLS (/32, separados por vírgula)"></span><input name="trusted_upstream_ips"></label>
        <button data-console-i18n="Aplicar endpoint"></button>
      </form>
      <p class="hint" id="console-web-bind-status"></p>
      <hr class="console-section-divider">
      <h3 data-console-i18n="Atualizações da plataforma"></h3>
      <p class="hint" data-console-i18n="Consulta uma revisão aprovada no GitHub. A instalação exige fila completamente drenada, backup e validação local de saúde."></p>
      <div class="console-update-layout">
        <div class="console-update-summary">
          <div id="console-update-status"></div>
          <div class="row console-update-actions"><button type="button" class="secondary console-update-check" id="console-update-check"></button><button type="button" id="console-update-apply" data-console-i18n="Instalar atualização"></button></div>
        </div>
        <div id="console-update-impact-slot"></div>
      </div>
      <hr class="console-section-divider">
      <h3 data-console-i18n="Gerenciamento de usuários"></h3>
      <form id="console-create-user" class="row">
        <label class="field"><span data-console-i18n="Usuário"></span><input name="username" pattern="(?:[a-z][a-z0-9_.-]{2,63}|[a-z0-9][a-z0-9._+-]{0,63}@[a-z0-9-]+(?:\.[a-z0-9-]+)+)" required></label>
        <label class="field"><span data-console-i18n="Senha temporária"></span><input name="password" type="password" minlength="14" required></label>
        <label class="field"><span data-console-i18n="Papel"></span><select name="role"><option>VIEWER</option><option>OPERATOR</option><option>ADMIN</option></select></label>
        <button data-console-i18n="Criar usuário"></button>
      </form>
      <div id="console-users" class="report-content" data-console-i18n="Carregando usuários…"></div>
      <hr class="console-section-divider">
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
    const updateModal = document.createElement("section");
    updateModal.id = "console-update-workflow-modal";
    updateModal.className = "modal hidden";
    updateModal.setAttribute("role", "dialog");
    updateModal.setAttribute("aria-modal", "true");
    updateModal.setAttribute("aria-labelledby", "console-update-workflow-title");
    updateModal.innerHTML = `<div class="modal-panel console-update-workflow-panel"><h2 id="console-update-workflow-title" data-console-i18n="Atualização da plataforma em andamento"></h2><div id="console-update-workflow-content"></div></div>`;
    document.body.append(updateModal);
    applyAuthTranslations(updateModal);
    const updateCommitsModal = document.createElement("section");
    updateCommitsModal.id = "console-update-commits-modal";
    updateCommitsModal.className = "modal hidden";
    updateCommitsModal.setAttribute("role", "dialog");
    updateCommitsModal.setAttribute("aria-modal", "true");
    updateCommitsModal.setAttribute("aria-labelledby", "console-update-commits-title");
    updateCommitsModal.innerHTML = `<div class="modal-panel console-update-commits-panel"><div class="modal-header"><h2 id="console-update-commits-title" data-console-i18n="Commits desta atualização"></h2><button type="button" class="secondary" data-close-update-commits data-console-i18n="Fechar"></button></div><p class="hint" id="console-update-commits-range"></p><ol id="console-update-commits-list" class="console-update-commits-list"></ol><p class="hint hidden" id="console-update-commits-truncated"></p></div>`;
    document.body.append(updateCommitsModal);
    applyAuthTranslations(updateCommitsModal);

    const auditQuery = () => {
      const form = card.querySelector("#console-audit-filter");
      const query = new URLSearchParams();
      ["actor", "event_type", "result"].forEach(name => {
        const value = form.elements[name].value.trim(); if (value) query.set(name, value);
      });
      return query.toString() ? `?${query}` : "";
    };
    let latestUpdateState = null;
    let updateRefreshTimer = null;
    let updateCheckInProgress = false;
    let updateWorkflowActive = false;
    let updateWorkflowLocked = false;
    let updateWorkflowSelective = false;
    let updateWorkflowPollTimer = null;
    const updateWorkflowContent = updateModal.querySelector("#console-update-workflow-content");
    const showUpdateCommits = () => {
      const impact = latestUpdateState?.impact || {};
      const commits = Array.isArray(impact.commits) ? impact.commits : [];
      const count = Number.isInteger(Number(impact.commit_count)) ? Number(impact.commit_count) : commits.length;
      updateCommitsModal.querySelector("#console-update-commits-range").textContent = `${uiText("Revisão instalada")}: ${latestUpdateState?.current_revision || "—"} → ${uiText("Revisão disponível")}: ${latestUpdateState?.available_revision || "—"}`;
      updateCommitsModal.querySelector("#console-update-commits-list").innerHTML = commits.length
        ? commits.map(commit => `<li><code>${escapeHtml(String(commit.revision || "").slice(0, 12))}</code><span>${escapeHtml(commit.subject || "—")}</span></li>`).join("")
        : `<li class="hint">${escapeHtml(uiText("Nenhum commit adicional foi informado para esta atualização."))}</li>`;
      const truncated = updateCommitsModal.querySelector("#console-update-commits-truncated");
      truncated.classList.toggle("hidden", !impact.commits_truncated);
      truncated.textContent = impact.commits_truncated
        ? uiText("Exibindo os primeiros {{shown}} de {{total}} commits.", {shown: commits.length, total: count}) : "";
      if (window.openModal) window.openModal("#console-update-commits-modal"); else updateCommitsModal.classList.remove("hidden");
    };
    updateCommitsModal.querySelector("[data-close-update-commits]").addEventListener("click", () => window.closeModal?.("#console-update-commits-modal"));
    const updateWorkflowSteps = state => {
      const phases = [
        ["VALIDATING", "Validar revisão e fila"], ["BACKING_UP", "Criar backup do PostgreSQL"],
        ["DEPLOYING", "Instalar nova revisão"], ["VERIFYING", "Reiniciar e validar plataforma"],
      ];
      const order = {VALIDATING:0, BACKING_UP:1, DEPLOYING:2, RESTARTING:3, RECONNECTING:3, VERIFYING:3, SUCCEEDED:4, ROLLED_BACK:4, FAILED:4, REJECTED:0};
      const current = order[state.state] ?? 0;
      return `<ol class="console-update-workflow-steps">${phases.map(([phase, label], index) => `<li class="${index < current || state.state === "SUCCEEDED" ? "complete" : index === current ? "active" : ""}"><span class="console-update-workflow-step-mark">${index < current || state.state === "SUCCEEDED" ? "✓" : index === current ? "•" : ""}</span>${escapeHtml(uiText(label))}</li>`).join("")}</ol>`;
    };
    const updateWorkflowProgress = state => {
      const fallback = {VALIDATING:10, BACKING_UP:35, DEPLOYING:65, RESTARTING:80, RECONNECTING:90, VERIFYING:90, SUCCEEDED:100, ROLLED_BACK:100, FAILED:100, REJECTED:0};
      return Math.max(0, Math.min(100, Number.isFinite(Number(state.progress)) ? Number(state.progress) : (fallback[state.state] || 0)));
    };
    const updateImpactMarkup = impact => {
      const value = impact || {};
      const classification = {
        WEB_UI_ONLY: uiText("Somente interface web"), DOCUMENTATION_ONLY: uiText("Somente documentação"),
        CONTROLLER_ONLY: uiText("Somente controller"),
        RESTORE_WORKER_ONLY: uiText("Somente worker de restore"),
        DISCOVERY_WORKER_ONLY: uiText("Somente worker de discovery"),
        AUDIT_WORKER_ONLY: uiText("Somente worker de auditoria"),
        TRANSFER_WORKER_ONLY: uiText("Somente worker de transferência"),
        FULL_PLATFORM: uiText("Plataforma completa"), UNKNOWN: uiText("Não classificado"),
      }[value.classification] || uiText("Não classificado");
      const componentLabels = {
        WEB_UI: uiText("Interface web"), WORKERS: uiText("Workers de migração"),
        CONTROLLER: uiText("Controller de migração"),
        RESTORE_WORKER: uiText("Worker de restore"), DISCOVERY_WORKER: uiText("Worker de discovery"),
        AUDIT_WORKER: uiText("Worker de auditoria"), TRANSFER_WORKER: uiText("Worker de transferência"),
        DATABASE_OR_API: uiText("API e banco de dados"), HOST_RUNTIME: uiText("Runtime do host"), DOCUMENTATION: uiText("Documentação"),
      };
      const components = (value.components || []).map(component => componentLabels[component] || component).join(", ") || "—";
      const transferImpact = value.classification === "TRANSFER_WORKER_ONLY"
        ? uiText("O worker de transferência será substituído após concluir o limite de trabalho durável; transferências retomam do checkpoint.")
        : value.classification === "RESTORE_WORKER_ONLY"
          ? uiText("Novos restores aguardam brevemente; transferências já despachadas continuam.")
        : value.classification === "DISCOVERY_WORKER_ONLY"
          ? uiText("Novas descobertas aguardam brevemente; transferências em curso continuam.")
        : value.classification === "AUDIT_WORKER_ONLY"
          ? uiText("Auditorias aguardam brevemente; restores e transferências em curso continuam.")
        : value.classification === "CONTROLLER_ONLY"
        ? uiText("Transferências já despachadas continuam; novas decisões aguardam a retomada do controller.")
        : value.transfer_impact === "NONE"
        ? uiText("Nenhuma lógica de transferência foi alterada.")
        : value.transfer_impact === "CONTROLLED_PAUSE"
          ? uiText("A instalação controlada pausará brevemente os componentes e os workers serão reiniciados.")
          : uiText("Impacto de transferência ainda não classificado.");
      const phaseOne = value.installation_strategy === "TRANSFER_WORKER_ROLLING"
        ? uiText("Esta atualização trocará somente o worker de transferência após seu checkpoint durável; os demais componentes continuarão ativos.")
        : value.installation_strategy === "RESTORE_WORKER_ROLLING"
          ? uiText("Esta atualização trocará somente o worker de restore após o limite de trabalho durável; os demais componentes continuarão ativos.")
        : value.installation_strategy === "DISCOVERY_WORKER_ROLLING"
          ? uiText("Esta atualização trocará somente o worker de discovery após o limite de trabalho durável; os demais componentes continuarão ativos.")
        : value.installation_strategy === "AUDIT_WORKER_ROLLING"
          ? uiText("Esta atualização trocará somente o worker de auditoria após o limite de trabalho durável; os demais componentes continuarão ativos.")
        : value.installation_strategy === "CONTROLLER_ONLY_ROLLING"
        ? uiText("Esta atualização trocará somente o controller após o ciclo transacional atual; workers de restore e transferência continuarão ativos.")
        : value.installation_strategy === "WEB_ONLY_ROLLING"
        ? uiText("Esta atualização trocará somente a interface web; os workers e transferências em curso continuarão ativos.")
        : uiText("Esta atualização exige backup e reinício controlado da plataforma.");
      const requiredSchema = Number.isInteger(Number(value.required_database_schema_revision)) ? `v${Number(value.required_database_schema_revision)}` : "—";
      return `<section class="console-update-impact"><h3>${escapeHtml(uiText("Impacto da atualização"))}</h3><p><strong>${escapeHtml(uiText("Classificação"))}:</strong> ${escapeHtml(classification)}</p><p><strong>${escapeHtml(uiText("Componentes alterados"))}:</strong> ${escapeHtml(components)}</p><p><strong>${escapeHtml(uiText("Schema exigido"))}:</strong> <code>${escapeHtml(requiredSchema)}</code></p><p><strong>${escapeHtml(uiText("Impacto nas transferências"))}:</strong> ${escapeHtml(transferImpact)}</p><p class="hint">${escapeHtml(phaseOne)}</p></section>`;
    };
    const showUpdateWorkflow = state => {
      latestUpdateState = {...(latestUpdateState || {}), ...state};
      const progress = updateWorkflowProgress(state);
      const finalSuccess = state.state === "SUCCEEDED";
      const finalFailure = ["FAILED", "ROLLED_BACK", "REJECTED"].includes(state.state);
      if (finalSuccess || finalFailure) updateWorkflowLocked = false;
      const reconnecting = state.state === "RECONNECTING";
      const message = reconnecting ? uiText("Reconectando à plataforma…") : ({
        VALIDATING: uiText("Validando a revisão aprovada e a fila drenada."),
        BACKING_UP: uiText("Criando backup do PostgreSQL antes da atualização."),
        DEPLOYING: uiText("Instalando a revisão aprovada."),
        RESTARTING: uiText("A plataforma será reiniciada agora; a sessão atual será encerrada."),
        VERIFYING: uiText("Reiniciando a plataforma e validando o health check local."),
        SUCCEEDED: uiText("Atualização concluída e validada pelo health check local."),
      }[state.state] || state.message || uiText("Processando atualização…"));
      const action = finalSuccess
        ? updateWorkflowSelective
          ? `<p class="console-update-workflow-final" data-console-i18n="Atualização seletiva concluída. Sua sessão permaneceu ativa."></p><button type="button" class="secondary" id="console-update-workflow-close" data-console-i18n="Fechar"></button>`
          : `<p class="console-update-workflow-final" data-console-i18n="Atualização concluída. Sua sessão atual será encerrada para concluir a instalação."></p><button type="button" id="console-update-workflow-logout" data-console-i18n="Entrar novamente"></button>`
        : finalFailure
          ? `<p class="error"><strong>${escapeHtml(uiText("Atualização não foi concluída."))}</strong> ${escapeHtml(state.message || uiText("A revisão anterior foi preservada. Verifique Settings antes de tentar novamente."))}</p><button type="button" class="secondary" id="console-update-workflow-close" data-console-i18n="Fechar"></button>`
          : "";
      updateWorkflowContent.innerHTML = `<p class="hint">${escapeHtml(message)}</p>${updateWorkflowSteps(state)}<div class="console-update-workflow-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}" aria-label="${escapeHtml(uiText("Progresso"))}"><span style="width:${progress}%"></span></div><p class="console-update-workflow-percent">${progress}%</p>${action}`;
      applyAuthTranslations(updateModal);
      updateModal.querySelector("#console-update-workflow-close")?.addEventListener("click", () => {
        updateWorkflowActive = false; updateWorkflowLocked = false; clearTimeout(updateWorkflowPollTimer); window.closeModal?.("#console-update-workflow-modal");
      });
      updateModal.querySelector("#console-update-workflow-logout")?.addEventListener("click", async () => {
        try { await apiCall("/api/auth/logout", {method:"POST"}); } finally { location.assign("/login"); }
      });
    };
    const pollUpdateWorkflow = async () => {
      if (!updateWorkflowActive) return;
      try {
        const state = await apiCall("/api/admin/updates");
        latestUpdateState = state;
        // The request file is visible before the root timer has written its
        // first progress state. Do not render the prior AVAILABLE result
        // (which correctly carries 100% for a completed *check*) as though
        // installation itself had completed.
        const awaitingAgent = updateWorkflowLocked && state.pending && state.state === "AVAILABLE";
        showUpdateWorkflow(awaitingAgent
          ? {...state, state:"VALIDATING", progress:10, message:uiText("Validando a revisão aprovada e a fila drenada.")}
          : state);
        if (["SUCCEEDED", "FAILED", "ROLLED_BACK", "REJECTED"].includes(state.state) && !state.pending) {
          // A selective rollout keeps this page alive. Refresh the Settings
          // card using the terminal host state so it cannot retain the prior
          // AVAILABLE revision or leave the install button enabled.
          await render();
          return;
        }
      } catch (_) {
        showUpdateWorkflow({state:"RECONNECTING", progress:90});
      }
      updateWorkflowPollTimer = window.setTimeout(pollUpdateWorkflow, 1500);
    };
    const openUpdateConfirmation = () => {
      updateWorkflowActive = true; updateWorkflowLocked = false;
      updateWorkflowContent.innerHTML = `<p data-console-i18n="Uma atualização criará um backup, reiniciará a plataforma e encerrará sua sessão atual. Será necessário entrar novamente. Continuar?"></p><p><strong>${uiText("Revisão disponível")}:</strong> <code>${escapeHtml(latestUpdateState?.available_revision || "—")}</code></p>${updateImpactMarkup(latestUpdateState?.impact, false)}<div class="modal-actions"><button type="button" class="secondary" id="console-update-workflow-cancel" data-console-i18n="Cancelar"></button><button type="button" id="console-update-workflow-confirm" data-console-i18n="Instalar atualização"></button></div>`;
      updateModal.querySelector("h2").dataset.consoleI18n = "Confirme a instalação da atualização";
      applyAuthTranslations(updateModal);
      if (window.openModal) window.openModal("#console-update-workflow-modal"); else updateModal.classList.remove("hidden");
      updateModal.querySelector("#console-update-workflow-cancel").addEventListener("click", () => {
        updateWorkflowActive = false; window.closeModal?.("#console-update-workflow-modal");
      });
      updateModal.querySelector("#console-update-workflow-confirm").addEventListener("click", async event => {
        updateWorkflowSelective = ["WEB_ONLY_ROLLING", "CONTROLLER_ONLY_ROLLING", "RESTORE_WORKER_ROLLING", "DISCOVERY_WORKER_ROLLING", "AUDIT_WORKER_ROLLING", "TRANSFER_WORKER_ROLLING"].includes(latestUpdateState?.impact?.installation_strategy);
        const button = event.currentTarget; button.disabled = true;
        updateWorkflowLocked = true;
        updateModal.querySelector("h2").dataset.consoleI18n = "Atualização da plataforma em andamento";
        updateModal.querySelector("h2").textContent = uiText("Atualização da plataforma em andamento");
        showUpdateWorkflow({state:"VALIDATING", progress:10, message:uiText("Validando a revisão aprovada e a fila drenada.")});
        try {
          await apiCall("/api/admin/updates/apply", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({revision:latestUpdateState.available_revision})});
          pollUpdateWorkflow();
        } catch (error) {
          updateWorkflowLocked = false;
          showUpdateWorkflow({state:"FAILED", progress:0, message:error.message});
        }
      });
    };
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && updateWorkflowLocked) {
        event.preventDefault(); event.stopImmediatePropagation();
      }
    }, true);
    const renderUpdateCheckButton = (busy, disabled) => {
      const button = card.querySelector("#console-update-check");
      if (!button) return;
      button.classList.toggle("is-busy", busy);
      button.disabled = Boolean(disabled);
      button.setAttribute("aria-busy", String(Boolean(busy)));
      button.setAttribute("aria-label", uiText(busy ? "Verificando" : "Verificar atualizações"));
      button.innerHTML = `<span class="console-update-check-idle" data-console-i18n="Verificar atualizações"></span><span class="console-update-check-progress" role="status"><span data-console-i18n="Verificando"></span><span class="console-update-check-spinner" aria-hidden="true"></span></span>`;
      applyAuthTranslations(button);
    };
    const render = async () => {
      const [users, sessions, audit, authSettings, webBind, bindAddresses, updateState] = await Promise.all([
        apiCall("/api/admin/users"), apiCall("/api/admin/sessions"),
        apiCall(`/api/admin/auth-audit${auditQuery()}`),
        apiCall("/api/admin/auth-settings"), apiCall("/api/admin/web-bind"), apiCall("/api/admin/web-bind/addresses"), apiCall("/api/admin/updates"),
      ]);
      const auditEventLabel = row => row.event_type === "USER_CREATED" && row.target
        ? `${row.event_type} (${row.target})` : row.event_type;
      card.querySelector("#console-auth-policy").elements.password_history_count.value = authSettings.password_history_count;
      const bindForm = card.querySelector("#console-web-bind");
      const addresses = Array.isArray(bindAddresses.addresses) ? bindAddresses.addresses : [];
      if (!addresses.some(item => item.value === webBind.host)) addresses.push({value:webBind.host, label:webBind.host});
      bindForm.host.innerHTML = addresses.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label || item.value)}</option>`).join("");
      bindForm.host.value = webBind.host; bindForm.port.value = webBind.port; bindForm.transport.value = webBind.transport;
      bindForm.trusted_upstream_ips.value = (webBind.trusted_upstream_ips || []).join(",");
      bindForm.querySelectorAll("input, select, button").forEach(control => { control.disabled = Boolean(webBind.locked || webBind.pending); });
      card.querySelector("#console-web-bind-status").textContent = webBind.locked ? uiText(webBind.lock_reason) : (webBind.pending ? uiText("Solicitação de endpoint aguardando aplicação no host.") : (webBind.result?.message || ""));
      const updatePending = Boolean(updateState.pending);
      const updateAvailable = updateState.state === "AVAILABLE" && /^[0-9a-f]{40}$/.test(updateState.available_revision || "");
      const updateMessage = {
        UNAVAILABLE: uiText("O controle de atualização do host não está disponível."),
        CURRENT: uiText("A revisão instalada está atual."),
        AVAILABLE: uiText("Uma revisão aprovada está disponível."),
        BACKING_UP: uiText("Criando backup do PostgreSQL antes da atualização."),
        DEPLOYING: uiText("Instalando a revisão aprovada."),
        RESTARTING: uiText("A plataforma será reiniciada agora; a sessão atual será encerrada."),
        VERIFYING: uiText("Reiniciando a plataforma e validando o health check local."),
        SUCCEEDED: uiText("Atualização concluída e validada pelo health check local."),
        ROLLED_BACK: uiText("A nova revisão falhou; a revisão anterior foi restaurada."),
      }[updateState.state] || updateState.message || "";
      latestUpdateState = updateState;
      const impactPreview = updateAvailable ? updateImpactMarkup(updateState.impact) : "";
      const failedUpdate = ["FAILED", "ROLLED_BACK", "REJECTED"].includes(updateState.state);
      const schemaRevision = Number.isInteger(Number(updateState.database_schema_revision)) ? `v${Number(updateState.database_schema_revision)}` : "—";
      const commitCount = Number.isInteger(Number(updateState.impact?.commit_count)) ? Number(updateState.impact.commit_count) : 0;
      const availableRevision = escapeHtml(updateState.available_revision || "—");
      const availableRevisionMarkup = updateAvailable && commitCount > 0
        ? `<button type="button" class="console-update-revision" id="console-update-commits-button" title="${escapeHtml(uiText("Ver commits desta atualização"))}"><code>${availableRevision}</code><span>(${commitCount})</span></button>`
        : `<code>${availableRevision}</code>`;
      card.querySelector("#console-update-status").innerHTML = `<p><strong>${uiText("Revisão instalada")}:</strong> <code>${escapeHtml(updateState.current_revision || "—")}</code></p><p><strong>${uiText("Revisão disponível")}:</strong> ${availableRevisionMarkup}</p><p><strong>${uiText("Schema do banco")}:</strong> <code>${escapeHtml(schemaRevision)}</code></p><p class="${failedUpdate ? "console-update-status-error" : "hint"}"><strong>${uiText("Estado")}:</strong> ${escapeHtml(updateState.state || "UNKNOWN")} — ${escapeHtml(updateMessage)}</p>`;
      card.querySelector("#console-update-commits-button")?.addEventListener("click", showUpdateCommits);
      let failureBanner = document.querySelector("#console-update-failure-banner");
      if (failedUpdate) {
        if (!failureBanner) { failureBanner = document.createElement("div"); failureBanner.id = "console-update-failure-banner"; failureBanner.className = "console-update-failure-banner"; document.querySelector(".topbar")?.after(failureBanner); }
        failureBanner.textContent = `${uiText("Atualização da plataforma não foi concluída")}: ${updateMessage}`;
      } else failureBanner?.remove();
      card.querySelector("#console-update-impact-slot").innerHTML = impactPreview;
      // A request is processed by the host agent asynchronously. Keep the
      // progress indication visible through its pending state, not only while
      // the short API request that creates it is in flight.
      renderUpdateCheckButton(updateCheckInProgress, updatePending || updateCheckInProgress);
      card.querySelector("#console-update-apply").disabled = updatePending || !updateAvailable;
      clearTimeout(updateRefreshTimer);
      if (updatePending || ["BACKING_UP", "DEPLOYING", "VERIFYING", "ROLLING_BACK"].includes(updateState.state)) {
        updateRefreshTimer = window.setTimeout(() => render().catch(() => {}), 3000);
      }
      card.querySelector("#console-users").innerHTML = `<table><thead><tr><th>${uiText("Usuário")}</th><th>${uiText("Papel")}</th><th>${uiText("Ativo")}</th><th>MFA</th><th>${uiText("Redefinir senha")}</th><th>${uiText("Ação")}</th></tr></thead><tbody>${users.map(user => { const isCurrentUser = user.id === identity.user.id; const deleteControl = isCurrentUser ? `<button type="button" class="danger" disabled title="${escapeHtml(uiText("Você não pode excluir sua própria conta."))}">${uiText("Excluir")}</button>` : `<button type="button" class="danger" data-delete-user="${user.id}">${uiText("Excluir")}</button>`; return `<tr data-user="${user.id}"><td>${escapeHtml(user.username)}${user.must_change_password?` · ${uiText("troca de senha obrigatória")}`:""}</td><td><select data-field="role">${["VIEWER","OPERATOR","ADMIN"].map(role => `<option${role===user.role?" selected":""}>${role}</option>`).join("")}</select></td><td><input data-field="enabled" type="checkbox"${user.enabled?" checked":""} aria-label="${escapeHtml(uiText("Ativar {{username}}", {username:user.username}))}"></td><td>${user.mfa_enabled ? `<button type="button" class="secondary" data-reset-mfa="${user.id}">${uiText("Redefinir MFA")}</button>` : uiText("Não configurado")}</td><td><input data-field="password" type="password" minlength="14" placeholder="${escapeHtml(uiText("Opcional"))}"></td><td><div class="row"><button type="button" data-save-user="${user.id}">${uiText("Salvar")}</button>${deleteControl}</div></td></tr>`; }).join("")}</tbody></table>`;
      card.querySelector("#console-sessions").innerHTML = `<table><thead><tr><th>${uiText("Usuário")}</th><th>${uiText("Última atividade")}</th><th>${uiText("Expira em")}</th><th>${uiText("Ação")}</th></tr></thead><tbody>${sessions.map(row => `<tr><td>${escapeHtml(row.username)}</td><td>${localTime(row.last_seen_at)}</td><td>${localTime(row.expires_at)}</td><td>${row.revoked_at?`${uiText("Revogada")} (${escapeHtml(row.revoke_reason||"")})`:row.is_current?`<button type="button" disabled title="${escapeHtml(uiText("Você não pode revogar a sessão atual."))}">${uiText("Revogar")}</button>`:`<button type="button" data-session="${row.id}">${uiText("Revogar")}</button>`}</td></tr>`).join("")}</tbody></table>`;
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
      card.querySelectorAll("[data-delete-user]").forEach(button => button.addEventListener("click", async () => {
        const row = button.closest("tr");
        const username = row.querySelector("td").textContent.split(" · ")[0];
        if (!window.confirm(uiText("Excluir {{username}} permanentemente? Todas as sessões, configurações de MFA e histórico de senhas deste usuário serão removidos. A auditoria será preservada.", {username}))) return;
        await apiCall(`/api/admin/users/${button.dataset.deleteUser}`, {method:"DELETE"});
        await render();
      }));
      card.querySelectorAll("[data-reset-mfa]").forEach(button => button.addEventListener("click", async () => {
        if (!window.confirm(uiText("Redefinir MFA deste usuário encerrará suas sessões. Continuar?"))) return;
        await apiCall(`/api/admin/users/${button.dataset.resetMfa}/mfa/reset`, {method:"POST"}); await render();
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
    card.querySelector("#console-web-bind").addEventListener("submit", async event => {
      event.preventDefault(); const form = event.currentTarget;
      const trusted_upstream_ips = form.trusted_upstream_ips.value.split(",").map(value => value.trim()).filter(Boolean);
      await apiCall("/api/admin/web-bind", {method:"PUT", headers:{"content-type":"application/json"}, body:JSON.stringify({host:form.host.value, port:Number(form.port.value), transport:form.transport.value, trusted_upstream_ips})});
      await render();
    });
    card.querySelector("#console-update-check").addEventListener("click", async () => {
      if (updateCheckInProgress) return;
      updateCheckInProgress = true;
      renderUpdateCheckButton(true, true);
      try {
        const priorUpdatedAt = latestUpdateState?.updated_at || "";
        await apiCall("/api/admin/updates/check", {method:"POST"});
        for (let attempt = 0; attempt < 12; attempt += 1) {
          await render();
          if ((latestUpdateState?.updated_at || "") !== priorUpdatedAt && !latestUpdateState?.pending) break;
          await new Promise(resolve => window.setTimeout(resolve, 500));
        }
        updateCheckInProgress = false;
        renderUpdateCheckButton(false, Boolean(latestUpdateState?.pending));
      } catch (error) {
        updateCheckInProgress = false;
        renderUpdateCheckButton(false, Boolean(latestUpdateState?.pending));
        throw error;
      }
    });
    card.querySelector("#console-update-apply").addEventListener("click", async () => {
      if (!latestUpdateState?.available_revision) return;
      openUpdateConfirmation();
    });
    card.querySelector("#console-audit-filter").addEventListener("submit", async event => { event.preventDefault(); await render(); });
    document.addEventListener("raijin:language-changed", () => {
      applyAuthTranslations(card);
      if (!updateModal.classList.contains("hidden") && updateModal.querySelector(".console-update-workflow-steps")) showUpdateWorkflow(latestUpdateState || {state:"VALIDATING", progress:10});
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
