(() => {
  const portuguese = (navigator.language || "").toLowerCase().startsWith("pt");
  const form = document.getElementById("login");
  document.querySelectorAll(".pt").forEach(element => { element.style.display = portuguese ? "" : "none"; });
  document.querySelectorAll(".en").forEach(element => {
    element.style.display = portuguese ? "none" : (element.tagName === "P" ? "block" : "inline");
  });
  let csrf = "";
  let changingPassword = false;
  let mfaChallenge = "";
  let mfaEnrollment = false;
  const passwordControl = (name, label, autocomplete) => `<label>${label}<span class="password-control"><input name="${name}" type="password" autocomplete="${autocomplete}" minlength="14" required><button type="button" class="password-visibility-toggle" aria-pressed="false"><span class="password-eye" aria-hidden="true"></span></button></span></label>`;
  const installPasswordVisibilityControls = () => {
    form.querySelectorAll(".password-visibility-toggle").forEach(button => {
      const input = button.closest(".password-control")?.querySelector("input");
      if (!input || button.dataset.ready) return;
      button.dataset.ready = "true";
      const update = () => {
        const visible = input.type === "text";
        button.setAttribute("aria-pressed", String(visible));
        button.setAttribute("aria-label", visible
          ? (portuguese ? "Ocultar senha" : "Hide password")
          : (portuguese ? "Exibir senha" : "Show password"));
        button.title = button.getAttribute("aria-label");
      };
      button.addEventListener("click", () => { input.type = input.type === "password" ? "text" : "password"; update(); input.focus(); });
      update();
    });
  };
  const responseError = async response => {
    let detail = "";
    try { detail = (await response.json()).detail || ""; } catch (_) { /* use a generic fallback */ }
    const error = new Error(detail || "request-failed");
    throw error;
  };
  const rememberCsrf = value => { csrf = value || ""; sessionStorage.setItem("raijin_csrf", csrf); };
  const message = () => document.getElementById("message");
  const showChangePassword = () => {
    changingPassword = true;
    document.querySelector(".card p")?.replaceChildren(portuguese ? "Defina uma nova senha para continuar." : "Set a new password to continue.");
    form.innerHTML = `${passwordControl("password", portuguese ? "Nova senha" : "New password", "new-password")}${passwordControl("confirmation", portuguese ? "Confirmar senha" : "Confirm password", "new-password")}<p id="message" role="alert"></p><button type="submit">${portuguese ? "Alterar senha" : "Change password"}</button>`;
    installPasswordVisibilityControls();
  };
  const showMfa = () => {
    mfaChallenge = mfaChallenge || "";
    document.querySelector(".card p")?.replaceChildren(portuguese ? "Informe o código de seis dígitos do seu autenticador." : "Enter the six-digit code from your authenticator.");
    form.innerHTML = `<label>${portuguese ? "Código de autenticação" : "Authentication code"}<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required autofocus></label><p id="message" role="alert"></p><button type="submit">${portuguese ? "Verificar código" : "Verify code"}</button>`;
  };
  const showMfaRecommendation = () => {
    changingPassword = false; mfaChallenge = ""; mfaEnrollment = false;
    document.querySelector(".card p")?.replaceChildren(portuguese ? "Proteja esta conta administrativa com autenticação em duas etapas." : "Protect this administrative account with two-step authentication.");
    form.innerHTML = `<p>${portuguese ? "Você pode configurar agora usando um aplicativo autenticador ou continuar e configurar depois no seu perfil." : "You can set it up now with an authenticator app, or continue and configure it later from your profile."}</p><p id="message" role="alert"></p><button type="button" id="mfa-enroll-now">${portuguese ? "Configurar autenticação em duas etapas" : "Set up two-step authentication"}</button><button type="button" id="mfa-skip" class="secondary">${portuguese ? "Pular por enquanto" : "Skip for now"}</button>`;
    form.querySelector("#mfa-skip").addEventListener("click", () => location.assign("/"));
    form.querySelector("#mfa-enroll-now").addEventListener("click", startMfaEnrollment);
  };
  const startMfaEnrollment = async () => {
    const button = form.querySelector("#mfa-enroll-now");
    if (button) button.disabled = true;
    message().textContent = "";
    try {
      const response = await fetch("/api/auth/mfa/enrollment", {method:"POST", headers:{"x-raijin-csrf-token":csrf}});
      if (!response.ok) await responseError(response);
      const data = await response.json(); mfaEnrollment = true;
      document.querySelector(".card p")?.replaceChildren(portuguese ? "Escaneie o QR Code e confirme o código de seis dígitos do autenticador." : "Scan the QR Code and confirm the six-digit code from your authenticator.");
      form.innerHTML = `<label>${portuguese ? "Chave de configuração" : "Setup key"}<input name="mfa_secret" readonly value="${data.secret}"></label><img class="mfa-qr" src="${data.qr_code_url}?v=${Date.now()}" alt="${portuguese ? "QR Code para configurar o autenticador" : "QR Code to set up the authenticator"}"><label>${portuguese ? "Código de autenticação" : "Authentication code"}<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required autofocus></label><p id="message" role="alert"></p><button type="submit">${portuguese ? "Ativar autenticação em duas etapas" : "Enable two-step authentication"}</button><button type="button" id="mfa-enroll-skip" class="secondary">${portuguese ? "Pular por enquanto" : "Skip for now"}</button>`;
      form.querySelector("#mfa-enroll-skip").addEventListener("click", () => location.assign("/"));
    } catch (error) {
      message().textContent = error.message || (portuguese ? "Não foi possível iniciar a configuração." : "Unable to start setup.");
    } finally { if (button) button.disabled = false; }
  };
  const showRecoveryCodes = codes => {
    mfaEnrollment = false;
    document.querySelector(".card p")?.replaceChildren(portuguese ? "Guarde estes códigos de recuperação em local seguro. Eles não serão exibidos novamente." : "Store these recovery codes securely. They will not be shown again.");
    form.innerHTML = `<code class="recovery-codes">${codes.join("  ")}</code><p id="message" role="alert"></p><button type="button" id="mfa-complete">${portuguese ? "Continuar para a console" : "Continue to console"}</button>`;
    form.querySelector("#mfa-complete").addEventListener("click", () => location.assign("/"));
  };
  form.addEventListener("submit", async event => {
    event.preventDefault(); event.stopImmediatePropagation();
    const button = form.querySelector('button[type="submit"]'); button.disabled = true; message().textContent = "";
    try {
      if (changingPassword) {
        if (form.password.value !== form.confirmation.value) throw new Error("password-mismatch");
        const response = await fetch("/api/auth/password", {method: "POST", headers: {"content-type": "application/json", "x-raijin-csrf-token": csrf}, body: JSON.stringify({new_password: form.password.value})});
        if (!response.ok) await responseError(response);
        const payload = await response.json(); rememberCsrf(payload.csrf_token);
        if (payload.mfa_enrollment_recommended) showMfaRecommendation(); else location.assign("/");
        return;
      }
      if (mfaChallenge) {
        const response = await fetch("/api/auth/mfa/verify", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({challenge_token:mfaChallenge, code:form.code.value})});
        if (!response.ok) await responseError(response);
        const payload = await response.json(); rememberCsrf(payload.csrf_token); location.assign("/"); return;
      }
      if (mfaEnrollment) {
        const response = await fetch("/api/auth/mfa/enrollment/confirm", {method:"POST", headers:{"content-type":"application/json", "x-raijin-csrf-token":csrf}, body:JSON.stringify({code:form.code.value})});
        if (!response.ok) await responseError(response);
        showRecoveryCodes((await response.json()).recovery_codes); return;
      }
      const response = await fetch("/api/auth/login", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({username: form.username.value, password: form.password.value})});
      if (!response.ok) await responseError(response);
      const payload = await response.json();
      if (payload.mfa_required) { mfaChallenge = payload.challenge_token; showMfa(); return; }
      rememberCsrf(payload.csrf_token);
      if (payload.must_change_password) showChangePassword(); else if (payload.mfa_enrollment_recommended) showMfaRecommendation(); else location.assign("/");
    } catch (error) {
      message().textContent = error.message === "password-mismatch"
        ? (portuguese ? "As senhas não coincidem." : "Passwords do not match.")
        : (error.message && error.message !== "request-failed" ? error.message
          : (changingPassword ? (portuguese ? "Não foi possível alterar a senha." : "Unable to change the password.") : (portuguese ? "Não foi possível autenticar com essas credenciais." : "Unable to authenticate with these credentials.")));
    }
    finally { button.disabled = false; }
  }, true);
  installPasswordVisibilityControls();
  (async () => {
    try {
      const response = await fetch("/api/auth/me", {cache: "no-store"});
      if (!response.ok) return;
      const payload = await response.json(); if (!payload.enabled) return;
      rememberCsrf(payload.csrf_token); if (payload.user?.must_change_password) showChangePassword(); else if (payload.mfa_enrollment_recommended) showMfaRecommendation(); else location.assign("/");
    } catch (_) { /* The login page remains usable while the API starts. */ }
  })();
})();
