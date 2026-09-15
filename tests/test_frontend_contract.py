from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_raijin_uses_the_shared_operational_card_contract():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    shell = (ROOT / "app/static/operational-shell.js").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/operational-shell.css").read_text(encoding="utf-8")
    assert "window.OperationalShell?.enhanceCards()" in page
    assert "createCard" in shell and "enhanceCards" in shell
    assert "selector='.metric,.fujin-metric,.service,.worker-status'" in shell
    assert "observer.observe(scope,{subtree:true,childList:true})" in shell
    assert "attributes:true" not in shell
    assert "--ops-card-neutral" in styles
    assert ".operational-card-title" in styles
    assert ".operational-card-info" in styles
    assert "inferKind" in shell
    assert 'data-card-kind="number"' in styles
    assert 'data-card-kind="status"' in styles


def test_language_selector_is_available_only_in_interface_settings():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert page.count('id="language-selector"') == 1
    assert page.index('id="view-settings"') < page.index('id="language-selector"')
    assert 'id="set-multipart-part-size"' in page
    assert 'id="aws-connection"' in page
    assert 'id="aws-connection-secret"' in page


def test_dynamic_restore_slot_ceiling_is_visible_and_persisted_from_settings():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="set-dynamic-restore-max-slots"' in page
    assert "dynamic_restore_max_slots:Math.round(Number($('#set-dynamic-restore-max-slots').value))" in page
    assert "Raikou starts with two restore slots" in page


def test_translation_catalog_covers_multipart_dynamic_feedback_and_restore_queue():
    catalog = (ROOT / "app/static/i18n.js").read_text(encoding="utf-8")
    for phrase in ("Multipart upload", "OCI destination validated", "Missing example:", "Interface language", "Batch job:", "Next attempt:"):
        assert phrase in catalog
    assert "node.nodeType === Node.TEXT_NODE" in catalog


def test_aws_connection_interface_never_places_secret_content_in_javascript():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "/api/aws-secrets/refresh" in page
    assert "/api/aws-connections" in page
    assert "bootstrap_secret_access_key" not in page.split("<script>", 1)[1]


def test_aws_connection_interface_can_submit_generic_private_endpoints_without_fujin_mode():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    for identifier in ("aws-sts-endpoint-url", "aws-s3-endpoint-url", "aws-s3control-endpoint-url", "aws-s3-addressing-style", "aws-tls-ca-bundle-path"):
        assert f'id="{identifier}"' in page
    assert "Endpoints privados (opcional)" in page
    submit = page[page.index("$('#aws-connection-form').addEventListener('submit'"):page.index("$('#discovery-form')")]
    assert "sts_endpoint_url:b('#aws-sts-endpoint-url')" in submit
    assert "s3_endpoint_url:b('#aws-s3-endpoint-url')" in submit
    assert "s3control_endpoint_url:b('#aws-s3control-endpoint-url')" in submit
    assert "Fujin" not in submit and "LOCAL" not in submit


def test_aws_connection_template_is_formatted_and_copyable():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="aws-secret-json-template"' in page
    assert 'id="aws-secret-template-modal"' in page
    assert "openAwsSecretTemplateModal()" in page
    assert "copyAwsSecretTemplate()" in page
    assert "navigator.clipboard.writeText" in page
    assert ".json-key" in page and ".json-string" in page
    assert '"private_endpoint"' in page
    assert '"s3control_endpoint_url"' in page
    assert "Nenhuma conexão AWS cadastrada" in page


def test_only_active_connection_secrets_are_disabled_and_archived_ones_can_be_reused():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "activeBySecret" in page
    assert "Secret já cadastrado na conexão ativa" in page
    assert "reutilizar; conexão anterior" in page
    assert "id=\"aws-connection-register\"" in page


def test_migration_activity_cards_separate_primary_values_units_and_context():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'class="metric activity-metric ${extra}" data-card-kind="activity"' in page
    assert 'class="activity-primary-value"' in page
    assert 'class="activity-primary-unit"' in page
    assert 'class="activity-secondary"' in page
    assert "`${bytes(used)} de ${bytes(total)}`" in page
    assert "`${fmt(activity.restore_requested_total)} solicitados`" in page
    assert "#activity .activity-primary-value" in page
    assert "#activity.activity-grid{grid-template-columns:repeat(6" in page


def test_platform_status_cards_use_compact_metric_and_worker_layouts():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'data-card-kind="platform-health"' in page
    assert 'class="platform-health-number"' in page
    assert 'class="platform-health-unit"' in page
    assert "renderPlatformHealthMetrics(operations)" in page
    assert "splitPlatformMeasure(bytes(operations.bytes))" in page
    assert 'data-card-kind="worker"' in page
    assert 'class="worker-primary-value"' in page
    assert "renderCompactWorkerStatus(operations,platform)" in page
    assert ".service-grid .service{min-height:76px" in page
    assert "#health.platform-health-grid{grid-template-columns:repeat(6" in page


def test_retired_restore_forecasts_are_not_exposed_as_operational_settings():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "Previsão BULK" not in page
    assert "Previsão STANDARD" not in page
    assert "set-bulk-restore-first-hours" not in page
    assert "set-standard-restore-first-hours" not in page
    assert "janela conservadora de 48 horas" in page
    assert "referência de planejamento para 12 horas" in page


def test_operational_configuration_numeric_controls_are_integer_only():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    form = page[page.index('<form id="settings-form"'):page.index("</form>", page.index('<form id="settings-form"'))]
    numeric_ids = (
        "set-throughput", "set-multipart-part-size", "set-wave-tb", "set-restore-days",
        "set-lease", "set-dynamic-safety-hours", "set-dynamic-restore-horizon",
        "set-dynamic-restore-max-slots", "set-continuous-min-buffer-hours",
        "set-continuous-target-buffer-hours", "set-continuous-max-buffer-hours",
        "set-continuous-batch-objects", "set-continuous-batch-gib",
        "set-continuous-critical-objects", "set-continuous-critical-mib",
        "set-continuous-critical-priority", "set-continuous-min-marginal-gain-mbps",
        "set-continuous-critical-initial-workers",
    )
    for field_id in numeric_ids:
        marker = f'id="{field_id}"'
        position = form.index(marker)
        tag = form[form.rfind("<input", 0, position):form.index(">", position) + 1]
        assert 'type="number"' in tag
        assert 'step="1"' in tag
        assert 'inputmode="numeric"' in tag
        assert "required" in tag
    assert 'step="0.' not in form
    assert "const hours=(seconds,fallback)=>Math.round" in page
    assert "default_wave_size_bytes:Math.round(Number($('#set-wave-tb').value))*1024**4" in page


def test_observability_cards_use_compact_values_and_fill_the_desktop_row():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert '#observability.observability-grid{grid-template-columns:repeat(7' in page
    assert 'data-card-kind="observability"' in page
    assert 'class="observability-number"' in page
    assert 'class="observability-unit"' in page
    assert 'class="observability-secondary"' in page
    assert "free=splitPlatformMeasure(bytes(freeBytes))" in page
    assert "`${fmt(usedPercent)}% ${en?'used':'utilizado'}`" in page
    assert "freeBytes<10*1024**3?'error':usedPercent>=85?'warning':'success'" in page


def test_connection_api_limits_are_configurable_in_the_interface():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="aws-connection-limits-modal"' in page
    assert "editAwsConnectionLimits" in page
    assert "Limites de API" in page
    assert "updateAwsConnectionRegistrationState" in page


def test_source_summary_identifies_its_aws_connection_with_an_orange_tag():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "aws-connection-tag" in page
    assert "aws_connection_label" in page
    assert "AWS Connections:" in page
    assert "#fb923c" in page


def test_transfer_queue_uses_compact_style_for_batch_job_id():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert ".queue-restore code" in page
    assert "padding:.18rem .35rem" in page


def test_wave_release_policy_and_report_operational_summary_are_visible():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="source-transfer-strategy"' not in page
    assert 'id="wave-transfer-release-policy"' in page
    assert 'id="automatic-transfer-release-policy"' in page
    assert 'id="prefix-transfer-release-policy"' in page
    assert 'id="dynamic-transfer-release-policy"' in page
    assert 'A criação dinâmica sempre libera objetos assim que ficam disponíveis.' in page
    assert "/transfer-strategy" not in page
    assert "Resumo operacional" in page
    assert "Média entre disponibilizações" in page


def test_dynamic_pipeline_exposes_its_fixed_immediate_release_and_source_priority():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert '<option value="dynamic">Pipeline contínuo</option>' in page
    assert 'id="dynamic-transfer-release-policy"' in page
    assert 'value="Assim que disponível" readonly' in page
    assert 'id="source-business-priority"' in page
    assert '<option value="999">Sem preferência</option>' in page
    assert '<option value="1">#1</option>' in page
    assert '<option value="20">#20</option>' in page


def test_aws_connection_sync_and_safe_configuration_controls_are_available():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "viewAwsConnectionConfiguration" in page
    assert "syncAwsConnection" in page
    assert "syncSourceAwsRegion" not in page
    assert "Sincronizar região AWS" not in page
    assert "Campos ocultos" in page
    assert "Tentativas de restore" in page


def test_aws_connection_configuration_opens_in_a_dismissible_modal():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="aws-connection-configuration-modal"' in page
    assert "closeAwsConnectionConfigurationModal()" in page
    assert "openModal('#aws-connection-configuration-modal')" in page
    handler = page[page.index("async function viewAwsConnectionConfiguration"):page.index("async function syncAwsConnection")]
    assert "modal-actions" not in handler
    assert "ACTIONABLE_FAILED" in page


def test_wave_report_is_a_scrollable_modal():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="wave-report-modal"' in page
    assert 'id="wave-report-content" class="report-content"' in page
    assert "openModal('#wave-report-modal')" in page
    assert ".report-content{max-height:72vh;overflow:auto" in page


def test_wave_actions_use_a_fixed_order_and_manifest_is_a_button():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    start = page.index("function normalizeWaveActions()")
    handler = page[start:page.index("const loadWavesWithNormalizedActions", start)]
    assert "manifest.replaceWith(button)" in handler
    assert "button.onclick=()=>window.location.assign(href)" in handler
    assert "const actionItems=[cost,report,manifest,queue,audit,pause,resume,reprocess,remove]" in handler
    assert "setText(report,'Report')" in handler
    assert "setText(manifest,'Manifest')" in handler
    assert "#waves .wave-actions .wave-action" in page


def test_wave_table_prioritizes_compact_operational_columns_without_copy_duration():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    start = page.index("async function loadWaves()")
    renderer = page[start:page.index("async function verifyWave", start)]
    assert '<th>Restore</th><th>Ações</th>' in renderer
    assert "Duração da cópia" not in renderer
    assert "transfer_duration_seconds" not in renderer
    assert "#waves th,#waves td{white-space:nowrap}" in page


def test_duration_displays_use_the_shared_calendar_clock_format():
    migration = (ROOT / "app/static/index.html").read_text()
    simulation = (ROOT / "app/static/simulation.html").read_text()
    required = "if(year)units.push(`${year}y`);if(month)units.push(`${month}m`);if(day)units.push(`${day}d`);"
    for page in (migration, simulation):
        assert required in page
        assert "return units.join(' ')" in page
    assert "function flightBoardDuration(seconds){return duration(seconds)}" in migration
    assert "function completionDuration(seconds){return seconds===null||seconds===undefined?'—':duration(Math.abs(Number(seconds)))}" in migration
    assert "Real elapsed<b>${duration(r.real_elapsed_seconds)}</b>" in simulation


def test_wave_actions_stay_inside_their_scroll_container_and_cost_is_compact():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "#waves{max-width:100%;overflow-x:auto;overflow-y:clip" in page
    assert "#waves table{table-layout:auto;min-width:1320px}" in page
    assert "waves-action-tooltip" in page
    assert "document.body.appendChild(tooltip)" in page
    assert "#waves .cost-action[data-cost-help]:hover::after" in page
    assert "setText(cost,'💰 Custo')" in page
    assert "button.removeAttribute('title')" in page
    assert "button:disabled{opacity:1!important" in page


def test_wave_status_help_uses_the_rich_aligned_tooltip_variant():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "status-tooltip-grid" in page
    assert "status-tooltip-tag status-${tone}" in page
    assert "data-rich-help" in page
    assert "tooltip.innerHTML=contentFor(target)" in page
    assert "Waves: Status" in page
    assert "raijin-tooltip-title" in page
    assert "scope===item?item:`${scope}: ${item}`" in page


def test_restore_queue_state_help_lists_all_operational_states_with_colored_tags():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "const restoreStateTooltip=()" in page
    assert "RESTORE SCHEDULED" in page
    assert "RESTORE + TRANSFER" in page
    assert "RESTORE REAPPROVAL REQUIRED" in page
    assert "restore-state-tooltip-grid" in page
    assert "stateHelp.dataset.richHelp=restoreStateTooltip()" in page


def test_simulation_help_uses_the_shared_rich_tooltip_pattern():
    page = (ROOT / "app/static/simulation.html").read_text(encoding="utf-8")
    assert "raijin-tooltip-title" in page
    assert "const targetFor=node=>node?.closest?.('.help[data-help]')||null" in page
    assert ".help:hover::after,.help:focus-visible::after{content:none!important}" in page


def test_simulation_sources_show_template_status_and_fixed_actions():
    simulation = (ROOT / "app/static/simulation.html").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    simulator = (ROOT / "app/simulator.py").read_text(encoding="utf-8")
    assert "Template: ${esc(s.template_name||'Custom scenario')}" in simulation
    assert "${sourceStatusTag(s.operational_status)}" in simulation
    assert "deleteSimulationSource(${s.id},${sourceName})" in simulation
    assert "/api/simulation/sources/${id}" in simulation
    assert '@app.delete("/api/simulation/sources/{source_id}")' in main
    assert '"template_name": template_snapshot.get("name") or "Custom scenario"' in simulator


def test_discovered_objects_and_source_cost_actions_live_in_the_discovery_summary():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    source_actions = page[page.index('<div class="row source-actions">'):page.index('<div id="source-summary"')]
    assert 'id="discovered-objects-modal"' in page
    assert 'id="inventory-page-size"' in page
    assert "openDiscoveredObjectsModal()" in page
    assert "const actions=$('#source-summary-actions')" in page
    assert "refreshAll()" not in source_actions
    assert ".source-actions{flex-wrap:nowrap;overflow:visible" in page
    assert ".source-actions .source-combobox{flex:0 0 490px" in page


def test_wave_report_distinguishes_aws_batch_evidence_from_raijin_polling():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "AWS submission:" in page
    assert "Batch execution:" in page
    assert "Completion evidence:" in page
    assert "Raijin polling:" in page


def test_object_detail_opens_in_a_scrollable_modal():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="object-detail-modal"' in page
    assert 'id="object-detail-content" class="report-content"' in page
    assert "closeObjectDetailModal()" in page
    handler = page[page.index("async function showObject"):page.index("async function loadWaves")]
    assert "openModal('#object-detail-modal')" in handler


def test_inline_code_uses_compact_chip_styling_instead_of_large_code_blocks():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "code,pre{" not in page
    assert "code{display:inline-block;max-width:100%;padding:.12rem .36rem" in page
    assert "pre code{display:block;max-width:none;padding:0" in page


def test_source_region_is_derived_and_read_only_from_the_aws_connection():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="region" required readonly' in page
    assert "applyAwsConnectionRegion(){const c=" in page
    assert "$('#region').value=c?c.default_region:''" in page


def test_source_summary_shows_discovery_duration_and_checkpoint_progress():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "discovery.duration_seconds" in page
    assert "discovery.pages_completed" in page
    assert "checkpoint salvo" in page


def test_discovery_is_selected_in_a_minimal_modal_with_remote_and_inventory_file_paths():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="discovery-modal"' in page
    assert 'onclick="openDiscoveryModal()" disabled>Discovery</button>' in page
    assert 'id="discovery-mode-remote"' in page
    assert 'id="discovery-mode-file"' in page
    assert 'id="inventory-file" type="file"' in page
    assert 'id="discovery-submit" type="submit">OK</button>' in page
    assert "new FormData()" in page
    assert "/inventory/upload" in page
    assert "mais de <b>1 milhão de objetos</b>" in page
    assert "input[type=checkbox],input[type=radio]{width:auto}" in page
    assert 'class="discovery-options"' in page
    assert "docs.aws.amazon.com/AmazonS3/latest/userguide/storage-inventory.html" in page


def test_all_application_messages_use_raijin_notification_windows():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="notification-stack"' in page
    assert "function dismissNotification" in page
    assert "className=`notification ${bad?'error':'ok'}`" in page
    assert "stack.append(item)" in page


def test_all_confirmation_questions_use_the_raijin_modal_instead_of_browser_confirm():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="confirm-modal"' in page
    assert "function ask(message" in page
    assert "function finishConfirmation" in page
    assert "window.confirm" not in page
    assert "confirm(" not in page
    assert page.count("await ask(") >= 14


def test_discovery_origin_is_visible_and_retired_lab_mode_is_not_exposed():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="set-laboratory-mode"' not in page
    assert 'id="laboratory-mode-banner"' not in page
    assert "syncLaboratoryModeBanner" not in page
    assert "Discovery: ${escape(discoveryModeLabel(discovery.mode))}" in page
    # Runtime selection is an administrative localhost API operation.  It
    # must never be available to a console operator as a settings control.
    assert 'id="operation-mode-action"' not in page
    assert "requestOperationMode(" not in page


def test_real_mode_hides_every_virtual_clock_residue_and_centers_system_clock():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="system-clock-row"' in page
    assert "body:not(.simulation-mode) #virtual-clock-row{display:none!important}" in page
    assert "body:not(.simulation-mode) #system-clock-row .banner-clock-label" in page


def test_source_prefixes_use_a_controlled_add_remove_list():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="prefix-input"' in page
    assert 'id="prefix-list"' in page
    assert "function addSourcePrefix" in page
    assert "function removeSourcePrefix" in page
    assert "sourcePrefixScopesOverlap" in page
    assert "max-height:7.4rem" in page


def test_source_form_opens_in_a_modal_with_a_fixed_prefix_workspace():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="create-source-action"' in page
    assert 'onclick="openNewSourceModal()">Criar nova origem</button>' in page
    assert 'id="source-modal" class="modal hidden"' in page
    assert 'id="source-form" class="source-form-layout"' in page
    assert "function openNewSourceModal()" in page
    assert "openModal('#source-modal')" in page
    assert "function closeSourceModal()" in page
    assert "#source-modal .prefix-list{align-content:start;height:10rem;max-height:10rem;overflow-y:auto" in page
    assert "closeSourceModal();await loadSources()" in page


def test_source_selector_uses_name_only_and_context_tags_are_in_the_heading():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="source-context-tags"' in page
    assert 'class="source-inventory-heading"' in page
    assert 'sources.map(x=>`<option value="${x.id}">${escape(x.name)}</option>`)' in page
    assert "<b>Prefixos S3</b>" in page


def test_archiving_a_source_clears_the_migration_selection_and_url_state():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    handler = page[page.index("async function removeOrArchiveSource"):page.index("let sourceMessageRotationTimer")]
    assert "sourceSelect.value=''" in handler
    assert "await selectSource()" in handler


def test_wave_cost_estimate_and_connection_pricing_are_available_in_modals():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="cost-pricing-modal"' in page
    assert 'id="wave-cost-modal"' in page
    assert "editCostPricing" in page
    assert "showWaveCost" in page
    assert "Estimativa de custo" in page


def test_continuous_lane_queue_exposes_priority_and_idle_diagnosis():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "priority_bands" in page
    assert "oldest_wait_seconds" in page
    assert "idle_diagnosis" in page
    assert "next_decision" in page
    assert "Próxima decisão Raikou:" in page
    assert "handoff_reservations" in page
    assert "handoff(s) crítico(s) reservado(s)" in page
    assert "Prioridades:" in page


def test_queue_restore_panel_hides_completed_waves_but_migrations_keeps_history():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "w.status!=='COMPLETED'&&(restoreStates.has(w.status)||w.restore?.requested_at)" in page
    assert "async function loadWaves" in page


def test_restore_and_continuous_lane_panels_share_the_top_row_and_details_span_below():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert ".queue-operations-grid{" in page
    assert "display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in page
    assert "align-items:stretch;min-width:0;max-width:100%" in page
    assert "grid-template-columns:minmax(0,1fr);align-items:start" in page
    assert ".queue-lane-details{grid-column:1/-1" in page
    assert ".queue-lane-details .lane-dispatches .queue-table-wrap{max-height:none" in page
    assert "const dispatchesOpen=$('#transfer-queue .lane-dispatches')?.open??false" in page
    assert "const raijusOpen=$('#transfer-queue .lane-raijus')?.open??false" in page
    assert "${dispatchesOpen?' open':''}" in page
    assert "${raijusOpen?' open':''}" in page
    assert "Reservado / aguardando Raiju" in page
    assert "Capacidade alvo" in page
    assert "reference_mbps_basis" in page
    assert '--raikou-accent:#d97706' in page
    assert '--raiju-accent:#22d3ee' in page
    assert '<span class="queue-panel-tag">Raiju</span>' in page
    assert '<h3>Detalhes da transferência contínua ' in page
    assert '.lane-backlog-copying{background:#d946ef}' in page
    assert '.lane-dispatches{border-top:0}' in page
    assert '.restore-operation .queue-table-wrap{width:100%;overflow-x:auto' in page
    assert '.queue-cell-line{display:block;white-space:nowrap}' in page
    assert '.lane-decision-lines{display:grid;gap:.12rem;margin:.3rem 0 0 1.65rem' in page
    assert '<span class="lane-decision-title"><strong>Próxima decisão: despacho elegível.</strong></span>' in page
    assert '${bytes(next.size_bytes||0)} · prioridade ${fmt(next.priority_score)}' in page


def test_raiju_lane_cards_and_tables_expose_contextual_help():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'const laneHelp=text=>' in page
    for label in (
        "Elegível agora",
        "Retry / retomada",
        "Reservado / aguardando Raiju",
        "Em cópia agora",
    ):
        assert f"<strong>{label} ${{laneHelp(" in page
    assert 'class="lane-backlog-legend"' not in page
    assert "<b>${bytes(leasedBytes)}</b><small>${fmt(leased)} objetos reservados ou em cópia" in page
    assert '<span class="lane-flow-title">Reservado/<wbr>copying</span>${laneHelp(' in page
    assert '.lane-flow-step.leased{border-color:#d946ef}' in page
    assert '.lane-flow-step.waiting,.lane-flow-step.copying{border-color:var(--raiju-accent,#22d3ee)}' in page
    assert page.rfind('.lane-flow-step.waiting,.lane-flow-step.copying') > page.find('.lane-flow-step.waiting{border-color:#64748b}')
    assert '.lane-flow-step.leased strong{display:grid;grid-template-columns:minmax(0,1fr) 17px' in page
    assert "<strong>Taxa de referência ${laneHelp(" not in page
    for label in (
        "Momento",
        "Lote despachado",
        "Capacidade alvo",
        "Prioridade",
        "Estado",
        "Motivo",
        "Worker",
        "Origem",
        "Arquivo atual",
        "Progresso",
    ):
        assert f'<span class="lane-table-heading">{label} ${{laneHelp(' in page
    assert ".lane-table-heading{display:inline-flex" in page


def test_cost_estimation_has_a_global_operational_toggle():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="set-cost-estimation"' in page
    assert "costEstimationEnabled" in page
    assert "estimativa de custo está desabilitada" in page
    assert "wave-cost-action" in page
    assert "source-cost-action" in page
    assert page.count("button.textContent='💰 Custo'") == 2
    assert "button.textContent='💲'" not in page


def test_running_tasks_are_not_rendered_as_alerts_but_stale_leases_are():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "tarefa(s) em execução" not in page
    assert "tarefa(s) com lease expirado" in page
    assert "api('/api/observability')" in page


def test_cost_estimation_supports_public_aws_prices_and_per_connection_overrides():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="global-pricing-settings"' in page
    assert 'id="set-cost-pricing-auto-refresh"' in page
    assert 'id="set-cost-pricing-refresh-days"' in page
    assert "refreshGlobalAwsPricing" in page
    assert "lista pública AWS" in page
    assert 'id="cost-include-aws-transfer-out"' in page


def test_public_aws_pricing_controls_are_visible_when_cost_estimation_is_enabled():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "classList.toggle('hidden',!costEstimationEnabled)" in page
    assert "if(costEstimationEnabled)await loadGlobalAwsPricing()" in page
    assert 'class="global-pricing-toolbar"' in page
    assert 'class="toggle-box global-pricing-auto-toggle"' in page
    assert 'class="global-pricing-auto-label"' in page
    assert "#global-pricing-settings .global-pricing-auto-toggle{display:inline-flex!important" in page
    assert "grid-template-columns:auto minmax(230px,1fr) auto auto" in page


def test_cost_pricing_can_show_collected_public_rates_and_modals_lock_background_scroll():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="public-pricing-modal"' in page
    assert "showCollectedPublicPricing" in page
    assert "Ver valores coletados" in page
    assert 'id="global-pricing-settings"' in page
    assert 'id="cost-include-oci-costs"' in page
    assert "body.modal-open{overflow:hidden}" in page
    assert "syncModalScrollLock" in page
    assert 'class="public-pricing-outbound-label"' in page
    assert ".public-pricing-outbound{display:grid;grid-template-columns:auto minmax(0,auto) auto" in page
    assert ".public-pricing-outbound input{width:auto!important;margin:0;align-self:center}" in page


def test_collected_public_pricing_handler_keeps_modal_open_inside_its_try_block():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    start = page.index("async function showCollectedPublicPricing")
    handler = page[start:page.index("\nasync function saveCostPricing", start)]
    assert "openModal('#public-pricing-modal')}catch" in handler
    assert "renderCollectedPublicPricing(select.value)" in handler
    assert 'id="public-pricing-region"' in page
    assert "unitRateMoney" in page


def test_cost_symbols_show_hover_summary_and_keep_clickable_detail():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "loadWaveCostTooltip" in page
    assert "loadSourceCostTooltip" in page
    assert "costTooltip(data)" in page
    assert ".cost-action[data-cost-help]:hover::after" in page
    assert "Custo único ${complete?'estimado':'parcial'}" in page


def test_wave_creation_uses_one_shared_action_for_every_method():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'id="wave-create-submit"' in page
    assert 'onclick="submitSelectedWaveMethod()" disabled>Criar onda</button>' in page
    assert 'id="wave-creation-empty"' in page
    assert "function syncSourceDependentControls" in page
    assert "queueAll.disabled=true" in page
    assert "function submitSelectedWaveMethod()" in page
    assert "manual:'#wave-form'" in page
    assert "automatic:'#automatic-wave-form'" in page
    assert "prefix:'#prefix-wave-form'" in page
    assert "dynamic:'#dynamic-wave-form'" in page
    assert "<h3>Onda manual</h3>" not in page
    assert "<h3>Ondas por prefixo S3</h3>" not in page
    assert "<h3>Criação dinâmica</h3>" not in page


def test_dynamic_wave_creation_gives_immediate_busy_feedback():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "function setDynamicWaveCreationBusy(busy)" in page
    assert "Criando waves…" in page
    assert "Criando waves dinâmicas e preparando o pipeline" in page
    handler = page[page.rindex("async function submitDynamicWaves"):page.index("saveSettings=", page.rindex("async function submitDynamicWaves"))]
    assert "setDynamicWaveCreationBusy(true)" in handler
    assert "finally{setDynamicWaveCreationBusy(false)}" in handler
    assert ".wave-create-busy::before" in page


def test_buttons_use_content_width_and_standard_horizontal_spacing():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "width:max-content!important" in page
    assert "padding-left:1em!important" in page
    assert "padding-right:1em!important" in page
    assert "button.hidden{display:none!important}" in page
    assert 'id="waves-queue-all" class="secondary hidden" onclick="queueAllPlannedWaves()" disabled' in page
    assert "queueAll.classList.toggle('hidden',!hasSource)" in page
    assert 'id="source-validate-destination"' in page
    assert 'id="source-edit-action"' in page


def test_banner_exposes_synchronized_system_and_simulation_clocks():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    simulation = (ROOT / "app/static/simulation.html").read_text(encoding="utf-8")
    for document in (page, simulation):
        assert 'id="banner-clock"' in document
        assert 'id="virtual-banner-clock"' in document
        assert 'id="virtual-clock-rate"' in document
        assert "/api/runtime/clock" in document
        assert "Boolean(data.held)" in document
        assert "ACCELERATED" in document and "HELD" in document


def test_operational_history_emphasizes_selected_source_in_title():
    page = Path("app/static/index.html").read_text()

    assert 'id="operational-history-source"' in page
    assert "function syncOperationalHistorySource()" in page
    assert "'All sources':'Todos os sources'" in page
    assert "`— ${source?.name||allSources}`" in page
    assert "syncOperationalHistorySource();openModal('#operational-history-modal')" in page


def test_migration_tools_are_contextual_footer_modals_with_critical_ticker():
    page = Path("app/static/index.html").read_text()
    assert 'id="operational-statusbar" class="operational-statusbar"' in page
    assert 'id="statusbar-migrations-actions" class="statusbar-actions hidden" data-footer-view="migrations"' in page
    assert 'id="durable-queue-modal" class="modal hidden"' in page
    assert 'id="operational-history-modal" class="modal hidden"' in page
    assert '<section class="card"><h2>Fila durável</h2>' not in page
    assert '<section class="card"><h2>Histórico operacional</h2>' not in page
    assert "function syncStatusbarContext(view)" in page
    assert "function updateOperationalMessages(operations,platform,observability)" in page
    assert "setInterval(refreshOperationalMessages,30000)" in page
    assert "operationalMessages.length" in page


def test_wave_report_explains_restore_failures_and_supports_evidence_recovery():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "function renderWaveReportOverall" in page
    assert "Status geral:" in page
    assert "Polling de disponibilidade" in page
    assert "wave-report-overall" in page
    assert "function renderRestoreDiagnosis" in page
    assert "Processamento do restore" in page
    assert "restoreDiagnosisMessage" in page
    assert "Continue o polling de disponibilidade." in page
    assert "Código AWS" in page
    assert "Ação recomendada" in page
    assert "retry-restore-evidence" in page
    assert "Esta ação não cria nem submete um novo restore" in page


def test_source_modal_keeps_original_full_width_form_layout():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "#source-modal .modal-panel{width:min(1400px,100%)}" in page
    assert 'id="source-form" class="source-form-layout"' in page


def test_simulation_mode_keeps_the_regular_console_and_exposes_a_red_admin_page():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    simulation = (ROOT / "app/static/simulation.html").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")

    assert 'id="simulation-nav" class="simulation-nav hidden"' in page
    assert 'id="simulation-runtime-banner"' in page
    assert "location.href='/simulation'" in page
    assert "with open(\"app/static/index.html\"" in main
    assert '@app.get("/simulation", response_class=HTMLResponse)' in main
    assert 'class="simulation-active" href="/simulation">Simulation</a>' in simulation
    assert 'href="/?view=dashboard">Status</a>' in simulation
    assert 'href="/?view=queue">Queue</a>' in simulation
    assert 'href="/?view=migrations">Migrations</a>' in simulation
    assert page.index('id="simulation-nav"') < page.index('class="gear secondary"')
    assert simulation.index('class="simulation-active"') < simulation.index('class="gear"')
    assert ".simulation-nav{background:transparent!important" in page
    assert ".simulation-active{background:#b91c1c" in simulation
    assert "body.simulation-mode #alerts{top:134px}" in page
    assert "body.simulation-mode .notification-stack{top:138px}" in page
    assert "Reative source" in simulation
    assert "/api/simulation/sources/${id}/reactivate" in simulation
    assert '@app.post("/api/simulation/sources/{source_id}/reactivate")' in main
    assert '>Discovery</button><button onclick="createWaves' not in simulation
    assert '>Create dynamic waves</button>' not in simulation
    assert '>Queue all</button>' not in simulation


def test_simulation_scenario_form_suggests_a_free_immutable_name():
    simulation = (ROOT / "app/static/simulation.html").read_text(encoding="utf-8")
    assert "function refreshScenarioNameSuggestion(scenarios)" in simulation
    assert "api('/api/simulation/scenarios')" in simulation
    assert "simulation-${String(number).padStart(3,'0')}" in simulation


def test_new_simulated_source_is_available_and_selected_in_migrations_without_reload():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    simulation = (ROOT / "app/static/simulation.html").read_text(encoding="utf-8")

    assert "cache:'no-store'" in page
    assert "cache:'no-store'" in simulation
    assert "raijin:pending-simulation-source-id" in page
    assert "sessionStorage.setItem('raijin:pending-simulation-source-id',String(sourceId))" in simulation
    assert "function announceMigrationSource(sourceId)" in simulation
    assert "new BroadcastChannel('raijin-sources')" in simulation
    assert "raijin:simulation-source-notification" in simulation
    assert "function receiveSimulationSourceNotification(message)" in page
    assert "new BroadcastChannel('raijin-sources')" in page
    assert "window.addEventListener('storage'" in page
    assert "onclick=\"reactivateSource(${s.id})\"" in simulation


def test_final_report_throughput_chart_resolves_its_id_as_a_css_selector():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert "const target=$(`#${targetId}`);if(!target)return;" in page
    assert "Carregar gráfico de taxa de transferência" in page
    assert "Velocidade do link" in page
    assert "throughput-footer" in page
    assert ">Throughput</strong>" in page
    assert "<b>Util:</b> ${fmt(throughputUtilization)}%" in page
    assert "A utilização é a média de throughput em relação ao limite configurado." not in page
    assert 'id="source-throughput-chart-action"' in page
    assert "target.innerHTML='<p class=\"hint\">Carregando amostras de throughput…</p>'" in page
    assert "target.innerHTML='<button id=\"source-throughput-chart-action\"" in page
    assert "action?.replaceWith(target)" not in page
    assert 'id="source-throughput-chart" class="source-throughput-chart" aria-live="polite"><button' in page
    assert "throughput-observed" in page
    assert "throughput-range" not in page
    assert ".throughput-chart text{fill:#dbeafe}" in page
    assert "const plottedMinimum=Math.min(...points.map(point=>Number(point.average_mbps)||0));" in page
    assert "const yMin=Math.max(0,plottedMinimum-plottedRange*.1);" in page


def test_discovery_queue_renders_at_most_five_items():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert "(await api('/api/discovery-queue')).slice(0,5)" in page


def test_final_report_keeps_its_header_visible_and_explains_evidence_metrics():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert 'class="modal-header source-completion-header"' in page
    assert 'class="source-completion-content hint"' in page
    assert ".source-completion-panel{display:flex;flex-direction:column" in page
    assert ".source-completion-content{min-height:0;overflow-y:auto" in page
    assert "function completionHelp(text)" in page
    assert "Acima do modelo de link ${completionHelp(" in page
    assert "Itens com retry ${completionHelp(" in page
    assert "Lane contínua ${completionHelp(" in page
    assert "Entrega OCI ${completionHelp(" in page
    assert "source-completion-footnote" in page


def test_operational_top_alerts_are_dismissible_without_removing_the_footer_condition():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert "const dismissedTopAlerts=new Set()" in page
    assert "function dismissTopAlert(key)" in page
    assert "function renderTopAlerts(alerts)" in page
    assert 'class="alert-dismiss"' in page
    assert "if(!activeKeys.has(key))dismissedTopAlerts.delete(key)" in page
    assert "updateOperationalMessages(d,p,o)" in page
    assert "renderTopAlerts(alerts)" in page


def test_simulation_admin_page_keeps_the_persistent_operational_footer():
    simulation = (ROOT / "app/static/simulation.html").read_text(encoding="utf-8")

    assert 'id="operational-statusbar" class="operational-statusbar"' in simulation
    assert 'id="statusbar-ticker" class="statusbar-ticker idle"' in simulation
    assert "function updateOperationalMessages(operations,platform,observability)" in simulation
    assert "async function refreshOperationalMessages()" in simulation
    assert "setInterval(refreshOperationalMessages,30000)" in simulation


def test_simulation_scenario_form_uses_grouped_integers_and_gb_units():
    simulation = (ROOT / "app/static/simulation.html").read_text(encoding="utf-8")

    assert "Logical size (GB)" in simulation
    assert "DATA physical budget (GB)" in simulation
    assert 'value="100.000"' in simulation
    assert 'value="1.000"' in simulation
    assert 'value="3.600"' in simulation
    assert "const GB_BYTES=1_000_000_000" in simulation
    assert "logical_size_bytes:logicalSizeGb*GB_BYTES" in simulation
    assert "physical_budget_bytes:physicalBudgetGb*GB_BYTES" in simulation
    assert "function prepareIntegerFields()" in simulation
    assert "stepIntegerInput(input,direction)" in simulation
    assert 'step="0.01"' not in simulation


def test_public_project_links_use_current_repository_name():
    repository_url = "github.com/wuilber002/raijin-data-migration"
    assert repository_url in (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert repository_url in (ROOT / "README.md").read_text(encoding="utf-8")
    assert repository_url in (ROOT / "terraform/orm/schema.yaml").read_text(encoding="utf-8")
    assert repository_url in (ROOT / "terraform/orm/variables.tf").read_text(encoding="utf-8")


def test_flight_board_modal_has_only_one_vertical_scroll_container():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert "#flight-board-modal .modal-panel{display:flex;flex-direction:column" in page
    assert "max-height:calc(100vh - 2rem);overflow:hidden" in page
    assert "#flight-board-content{min-height:0;max-height:none;overflow-y:auto;overflow-x:hidden}" in page
    assert "Lane contínua de transferência" in page
    assert "flight-board-transfer-lane" in page
    assert "filter(phase=>phase.kind!=='TRANSFER')" in page


def test_activity_auto_refresh_is_a_compact_horizontal_control():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert 'class="toggle-box activity-auto-refresh-toggle"' in page
    assert 'class="activity-auto-refresh-label"' in page
    assert ".activity-auto-refresh-toggle{display:inline-flex!important;flex-direction:row!important" in page
    assert "grid-template-columns:minmax(230px,1fr) auto auto minmax(220px,300px)" in page


def test_aws_connection_actions_are_compact_and_region_never_wraps():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert "action('⚙️','Ver configuração'" in page
    assert "action('💰','Tarifas'" in page
    assert "action('🔄','Sincronizar Secret'" in page
    assert "action('📋','Pré-check'" in page
    assert "c.sources?'🗄️':'🗑️'" in page
    assert "limits.textContent='🎚️'" in page
    assert ".aws-connection-actions{display:flex;align-items:center;gap:.42rem" in page
    assert ".aws-connection-action{display:inline-flex!important" in page
    assert '#aws-connections th:nth-child(3),#aws-connections td:nth-child(3){min-width:92px;white-space:nowrap}' in page


def test_flight_board_supports_manual_refresh_and_bounded_loading():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert 'id="flight-board-refresh"' in page
    assert 'onclick="refreshFlightBoard()"' in page
    assert "const flightBoardTimeoutMs=45000" in page
    assert "flightBoardRequestController?.abort()" in page
    assert "RESTORE_SAVING:['restore-saving','Tempo economizado no restore']" in page
    assert ".flight-board-phase.restore-saving" in page
    assert ".flight-board-phase.restore-saving{background-color:#16a34a!important;background-image:none!important;opacity:1}" in page
    assert "phase.planned&&!observedSaving?' planned':''" in page
    assert "continues-to-saving" in page
    assert "continues-from-restore" in page
    assert ".flight-board-restore-row .flight-board-phase.restore-saving{top:10px}" in page
    assert ".flight-board-restore-row .flight-board-phase{top:10px;height:8px}" in page
    assert "function flightBoardBars(" in page
    assert "joins-previous" in page and "joins-next" in page
    assert "function flightBoardRestoreSchedule(w)" in page
    assert "Aguardando vaga de restore." in page
    assert "Aguardando drenagem segura da fila contínua." in page
    assert "A data acima indica elegibilidade, não uma submissão programada." in page
    assert "A disponibilidade será calculada após a submissão." in page
    assert "Tempo decorrido / janela máxima:" in page
    assert "Janela máxima prevista:" in page
    assert "Início do restore:" in page


def test_flight_board_repeats_the_time_axis_below_the_restore_rows():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert '${chart}${flightBoardAxis(start,end)}</div><table class="flight-board-table"' in page


def test_refresh_restores_the_current_view_and_selected_source_without_duplicate_loads():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert "showView(initialView,{persist:false,scroll:false,load:false})" in page
    assert "const requested=new URLSearchParams(location.search).get('source')||''" in page
    assert "url.searchParams.set('source',selectedSource)" in page
    assert "await Promise.all([loadSettings(),loadSources()])" in page
    assert "else if(view==='migrations'){await Promise.all([loadTasks(),loadEvents()])}" in page


def test_reprocess_requires_a_second_explicit_confirmation_when_restore_cost_may_recur():
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert "Aprovar novo restore" in page
    assert "approve_new_restore:true" in page
    assert "pode gerar cobrança AWS" in page
