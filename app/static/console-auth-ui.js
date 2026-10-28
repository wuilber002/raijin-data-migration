(() => {
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  const apiCall = (...args) => window.api ? window.api(...args) : Promise.reject(new Error("Console API is not ready"));
  const localTime = value => value ? new Date(value).toLocaleString() : "—";

  async function install() {
    let identity;
    try { identity = await apiCall("/api/auth/me"); } catch (_) { return; }
    if (!identity.enabled) return;
    const actions = document.querySelector(".banner-actions");
    const logout = document.createElement("button");
    logout.type = "button"; logout.className = "secondary";
    logout.textContent = `Sign out (${identity.user.username})`;
    logout.addEventListener("click", async () => {
      try { await apiCall("/api/auth/logout", {method:"POST"}); }
      finally { location.assign("/login"); }
    });
    actions?.append(logout);
    if (identity.user.role !== "ADMIN") return;

    const settings = document.getElementById("view-settings");
    if (!settings) return;
    const card = document.createElement("section");
    card.className = "card"; card.id = "console-access-management";
    card.innerHTML = `
      <h2>Console access</h2>
      <p class="hint">Local users, active browser sessions, and authentication audit evidence.</p>
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
      const [users, sessions, audit] = await Promise.all([
        apiCall("/api/admin/users"), apiCall("/api/admin/sessions"),
        apiCall(`/api/admin/auth-audit${auditQuery()}`),
      ]);
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
    card.querySelector("#console-audit-filter").addEventListener("submit", async event => { event.preventDefault(); await render(); });
    await render();
  }
  queueMicrotask(install);
})();
