(() => {
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  const apiCall = (...args) => window.api ? window.api(...args) : Promise.reject(new Error("Console API is not ready"));
  const localTime = value => value ? new Date(value).toLocaleString() : "—";

  async function install() {
    let identity;
    try { identity = await apiCall("/api/auth/me"); } catch (_) { return; }
    if (!identity.enabled) return;
    const actions = document.querySelector(".banner-actions");
    const userMenu = document.createElement("div");
    userMenu.className = "console-user-menu";
    const userMenuTrigger = document.createElement("button");
    userMenuTrigger.type = "button";
    userMenuTrigger.className = "secondary console-user-menu-trigger";
    userMenuTrigger.setAttribute("aria-label", "Menu do usuário");
    userMenuTrigger.setAttribute("aria-haspopup", "menu");
    userMenuTrigger.setAttribute("aria-expanded", "false");
    userMenuTrigger.title = "Menu do usuário";
    userMenuTrigger.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a4.25 4.25 0 1 0 0-8.5 4.25 4.25 0 0 0 0 8.5Zm0 2.1c-4.48 0-8.1 2.18-8.1 4.87V21h16.2v-2.03c0-2.69-3.62-4.87-8.1-4.87Z"/></svg>';
    const userMenuPanel = document.createElement("div");
    userMenuPanel.className = "console-user-menu-panel hidden";
    userMenuPanel.setAttribute("role", "menu");
    userMenuPanel.setAttribute("aria-label", "Ações do usuário");
    const userIdentity = document.createElement("div");
    userIdentity.className = "console-user-menu-identity";
    userIdentity.textContent = identity.user.username;
    userIdentity.setAttribute("role", "presentation");
    const profile = document.createElement("button");
    profile.type = "button"; profile.className = "console-user-menu-action";
    profile.textContent = "Meu perfil";
    profile.setAttribute("role", "menuitem");
    const logout = document.createElement("button");
    logout.type = "button"; logout.className = "console-user-menu-action";
    logout.textContent = "Sair";
    logout.setAttribute("role", "menuitem");
    userMenuPanel.append(userIdentity, profile, logout);
    userMenu.append(userMenuTrigger, userMenuPanel);
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
        <div class="modal-header"><h2 id="console-profile-title">Meu perfil</h2><button type="button" class="secondary" data-close-profile>Fechar</button></div>
        <p class="hint">Atualize somente seus próprios dados. O usuário é gerenciado pelo administrador.</p>
        <form id="console-profile-form" class="grid">
          <label class="field"><span>Usuário</span><input name="username" disabled aria-describedby="console-profile-username-help"><small id="console-profile-username-help" class="hint">Este dado não pode ser alterado.</small></label>
          <label class="field"><span>Nome</span><input name="display_name" maxlength="128" autocomplete="name"></label>
          <label class="field"><span>E-mail</span><input name="email" type="email" maxlength="320" autocomplete="email"></label>
          <div class="field action"><span class="field-label">Dados pessoais</span><button>Salvar perfil</button></div>
        </form>
        <hr>
        <h3>Trocar senha</h3>
        <form id="console-password-form" class="grid">
          <label class="field"><span>Senha atual</span><input name="current_password" type="password" autocomplete="current-password" required></label>
          <label class="field"><span>Nova senha</span><input name="new_password" type="password" minlength="14" autocomplete="new-password" required></label>
          <label class="field"><span>Confirmar nova senha</span><input name="confirmation" type="password" minlength="14" autocomplete="new-password" required></label>
          <div class="field action"><span class="field-label">Segurança</span><button>Trocar senha</button></div>
        </form>
        <p id="console-profile-message" class="hint" role="status"></p>
      </div>`;
    document.body.append(profileModal);
    const profileMessage = value => { profileModal.querySelector("#console-profile-message").textContent = value || ""; };
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
    if (identity.user.role !== "ADMIN") {
      // Settings contains only tenancy integration and global scheduling
      // controls. Do not make an OPERATOR/VIEWER discover administrative
      // integration blocks that the server must correctly deny anyway.
      document.querySelector('[data-view="settings"]')?.classList.add("hidden");
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

    const settings = document.getElementById("view-settings");
    if (!settings) return;
    const card = document.createElement("section");
    card.className = "card"; card.id = "console-access-management";
    card.innerHTML = `
      <h2>Console access</h2>
      <p class="hint">Local users, active browser sessions, and authentication audit evidence.</p>
      <form id="console-auth-policy" class="row">
        <label class="field"><span>Password reuse history</span><input name="password_history_count" type="number" min="0" max="12" required></label>
        <span class="hint">Blocks the current password plus this number of previous passwords (default: 3).</span>
        <button>Save policy</button>
      </form>
      <form id="console-create-user" class="row">
        <label class="field"><span>Username</span><input name="username" pattern="[a-z][a-z0-9_.-]{2,63}" required></label>
        <label class="field"><span>Temporary password</span><input name="password" type="password" minlength="14" required></label>
        <label class="field"><span>Role</span><select name="role"><option>VIEWER</option><option>OPERATOR</option><option>ADMIN</option></select></label>
        <button>Create user</button>
      </form>
      <div id="console-users" class="report-content">Loading users…</div>
      <h3>Sessions</h3><div id="console-sessions" class="report-content">Loading sessions…</div>
      <h3>Recent authentication audit</h3>
      <form id="console-audit-filter" class="row">
        <label class="field"><span>Actor</span><input name="actor" pattern="[a-z][a-z0-9_.-]{2,63}"></label>
        <label class="field"><span>Event</span><input name="event_type" placeholder="LOGIN_SUCCEEDED"></label>
        <label class="field"><span>Result</span><select name="result"><option value="">All</option><option>SUCCEEDED</option><option>DENIED</option></select></label>
        <button class="secondary">Filter</button>
      </form>
      <div id="console-auth-audit" class="report-content">Loading audit…</div>`;
    settings.append(card);

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
      card.querySelector("#console-auth-policy").elements.password_history_count.value = authSettings.password_history_count;
      card.querySelector("#console-users").innerHTML = `<table><thead><tr><th>Username</th><th>Role</th><th>Enabled</th><th>Reset password</th><th>Action</th></tr></thead><tbody>${users.map(user => `<tr data-user="${user.id}"><td>${escapeHtml(user.username)}${user.must_change_password?" · password change required":""}</td><td><select data-field="role">${["VIEWER","OPERATOR","ADMIN"].map(role => `<option${role===user.role?" selected":""}>${role}</option>`).join("")}</select></td><td><input data-field="enabled" type="checkbox"${user.enabled?" checked":""} aria-label="Enable ${escapeHtml(user.username)}"></td><td><input data-field="password" type="password" minlength="14" placeholder="Optional"></td><td><button type="button" data-save-user="${user.id}">Save</button></td></tr>`).join("")}</tbody></table>`;
      card.querySelector("#console-sessions").innerHTML = `<table><thead><tr><th>User</th><th>Last seen</th><th>Expires</th><th>Action</th></tr></thead><tbody>${sessions.map(row => `<tr><td>${escapeHtml(row.username)}</td><td>${localTime(row.last_seen_at)}</td><td>${localTime(row.expires_at)}</td><td>${row.revoked_at?`Revoked (${escapeHtml(row.revoke_reason||"")})`:`<button type="button" data-session="${row.id}">Revoke</button>`}</td></tr>`).join("")}</tbody></table>`;
      card.querySelector("#console-auth-audit").innerHTML = `<table><thead><tr><th>Time</th><th>Actor</th><th>Event</th><th>Result</th></tr></thead><tbody>${audit.map(row => `<tr><td>${localTime(row.created_at)}</td><td>${escapeHtml(row.actor||"system")}</td><td>${escapeHtml(row.event_type)}</td><td>${escapeHtml(row.result)}</td></tr>`).join("")}</tbody></table>`;
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
    await render();
  }
  queueMicrotask(install);
})();
