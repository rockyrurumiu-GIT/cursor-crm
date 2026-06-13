/**
 * RMS pipeline tab: filters, progress transitions, status correction (Phase R3-B split).
 */
(function (global) {
  "use strict";

  function pipelineStatusMatches(appStatus, selectedStatuses, Labels) {
    if (Labels.statusMatchesFilter) {
      return Labels.statusMatchesFilter(appStatus, selectedStatuses);
    }
    var selected = Array.isArray(selectedStatuses) ? selectedStatuses : [];
    if (!selected.length) return true;
    var raw = String(appStatus == null ? "" : appStatus).trim();
    var normalized = raw;
    if (Labels.filterProgressStatus) {
      normalized = Labels.filterProgressStatus(raw);
    } else if (raw === "recommended") {
      normalized = "pending_internal_screen";
    } else if (raw === "screening") {
      normalized = "pending_client_screen";
    } else if (raw === "interview") {
      normalized = "pending_first_interview";
    } else if (raw === "offer") {
      normalized = "pending_offer";
    }
    for (var i = 0; i < selected.length; i++) {
      var want = String(selected[i] == null ? "" : selected[i]).trim();
      if (want && (raw === want || normalized === want)) return true;
    }
    return false;
  }

  function createPipelineState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var computed = deps.computed;
    var Labels = deps.Labels;
    var rmsRequest = deps.rmsRequest;
    var toast = deps.toast;
    var jobs = deps.jobs;
    var applicationsState = deps.applicationsState;
    var candidatesState = deps.candidatesState;
    var loadApplications = deps.loadApplications;
    var clientNameById = deps.clientNameById;
    var appCandidateName = deps.appCandidateName;
    var appJobTitle = deps.appJobTitle;

    function progressLabel(status) {
      return Labels.progressLabel ? Labels.progressLabel(status) : status;
    }

    var pipelineFilter = reactive({
      client_id: "",
      job_id: "",
      city: "",
      delivery: "",
      recommender: "",
      statuses: [],
      activeOnly: true,
      date_from: "",
      date_to: "",
    });

    var progressOptions = (Labels.APPLICATION_PROGRESS_STATUSES || []).map(function (s) {
      return { value: s, label: Labels.progressLabel ? Labels.progressLabel(s) : s };
    });
    var pipelineStatusDropdownOpen = ref(false);
    var pipelineStatusDraft = ref([]);
    var pipelineStatusFilterSummary = computed(function () {
      var sel = pipelineFilter.statuses || [];
      if (!sel.length) return "全部";
      if (sel.length === 1) return progressLabel(sel[0]);
      return "已选" + sel.length + "项";
    });

    var filteredPipelineApplications = computed(function () {
      if (!Labels.filterPipelineApplications) return [];
      var appliedStatuses = (pipelineFilter.statuses || []).slice();
      var rows = Labels.filterPipelineApplications(applicationsState.items, {
        filters: {
          client_id: pipelineFilter.client_id,
          job_id: pipelineFilter.job_id,
          city: pipelineFilter.city,
          delivery: pipelineFilter.delivery,
          recommender: pipelineFilter.recommender,
          statuses: [],
          activeOnly: appliedStatuses.length ? false : pipelineFilter.activeOnly,
          date_from: pipelineFilter.date_from,
          date_to: pipelineFilter.date_to,
        },
        getJobs: function () { return jobs.jobsState.items; },
        getCandidates: function () { return candidatesState.items; },
        getUsers: function () { return jobs.userOptions.value; },
        clientNameById: clientNameById,
      });
      if (!appliedStatuses.length) return rows;
      return rows.filter(function (a) {
        return pipelineStatusMatches(a.status, appliedStatuses, Labels);
      });
    });

    function resetPipelineFilter() {
      pipelineFilter.client_id = "";
      pipelineFilter.job_id = "";
      pipelineFilter.city = "";
      pipelineFilter.delivery = "";
      pipelineFilter.recommender = "";
      pipelineFilter.statuses.splice(0, pipelineFilter.statuses.length);
      pipelineStatusDraft.value = [];
      pipelineFilter.activeOnly = true;
      pipelineStatusDropdownOpen.value = false;
      pipelineFilter.date_from = "";
      pipelineFilter.date_to = "";
    }

    function togglePipelineStatusDropdown() {
      if (!pipelineStatusDropdownOpen.value) {
        pipelineStatusDraft.value = (pipelineFilter.statuses || []).slice();
      }
      pipelineStatusDropdownOpen.value = !pipelineStatusDropdownOpen.value;
    }

    function togglePipelineStatusDraft(value) {
      var list = pipelineStatusDraft.value;
      var idx = list.indexOf(value);
      if (idx >= 0) list.splice(idx, 1);
      else list.push(value);
    }

    function clearPipelineStatusDraft() {
      pipelineStatusDraft.value = [];
    }

    function applyPipelineStatusFilter() {
      var next = pipelineStatusDraft.value.slice();
      pipelineFilter.statuses.splice(0, pipelineFilter.statuses.length);
      next.forEach(function (v) {
        pipelineFilter.statuses.push(v);
      });
      pipelineStatusDropdownOpen.value = false;
    }

    function todayDateStr() {
      var d = new Date();
      var m = String(d.getMonth() + 1).padStart(2, "0");
      var day = String(d.getDate()).padStart(2, "0");
      return d.getFullYear() + "-" + m + "-" + day;
    }

    var hiredAtDates = reactive({});

    function progressTransitionsFor(status) {
      return Labels.progressTransitionsFor ? Labels.progressTransitionsFor(status) : [];
    }

    function progressOptionsForCorrection(currentStatus) {
      return Labels.progressOptionsForCorrection
        ? Labels.progressOptionsForCorrection(currentStatus)
        : [];
    }

    function normalizeProgressStatus(status) {
      return Labels.normalizeProgressStatus
        ? Labels.normalizeProgressStatus(status)
        : String(status || "").trim();
    }

    function hiredAtFor(appId) {
      var id = String(appId);
      if (!hiredAtDates[id]) hiredAtDates[id] = todayDateStr();
      return hiredAtDates[id];
    }

    function setHiredAtFor(appId, value) {
      hiredAtDates[String(appId)] = value;
    }

    async function submitProgressConfirm(applicationId, toStatus, mode, formValues) {
      formValues = formValues || {};
      var note = String(formValues.note || "").trim();
      if (mode === "correction" && note.length < 2) {
        toast("状态修正备注至少 2 个字", true);
        return;
      }
      var body = { to_status: toStatus, mode: mode, note: note };
      if (toStatus === "hired") {
        var dateVal = String(formValues.hired_at || todayDateStr()).trim();
        if (!dateVal) {
          toast("请填写入职时间", true);
          return;
        }
        body.hired_at = dateVal;
      }
      var r = await rmsRequest("POST", "/api/rms/applications/" + applicationId + "/status", body);
      if (!r.ok) {
        toast(r.message, true);
        return;
      }
      var data = r.data || {};
      if (data.roster_check && data.roster_check.message) {
        var st = data.roster_check.status;
        var isWarn = st === "missing" || st === "date_mismatch" || st === "ambiguous";
        toast(data.roster_check.message, isWarn);
      } else {
        toast("招聘进展已更新为 " + progressLabel(toStatus), false);
      }
      delete hiredAtDates[String(applicationId)];
      await loadApplications();
    }

    async function openProgressConfirmModal(app, targetStatus, mode) {
      if (!app || app.id == null || !targetStatus) return;
      if (typeof global.crmConfirmActionDialog !== "function") {
        toast("确认对话框不可用", true);
        return;
      }
      var lines = [
        { label: "候选人", value: appCandidateName(app) },
        { label: "岗位", value: appJobTitle(app) },
        { label: "当前状态", value: progressLabel(app.status) },
        { label: "目标状态", value: progressLabel(targetStatus) },
        { label: "操作类型", value: mode === "correction" ? "状态修正" : "正常推进" },
      ];
      var hint = "";
      if (app.status === "hired" && targetStatus !== "hired") {
        hint = "确认后将清空入职时间。";
      }
      var fields = [{
        type: "textarea",
        name: "note",
        label: "备注/原因",
        placeholder: mode === "correction" ? "必填，至少 2 个字" : "可选",
      }];
      if (targetStatus === "hired") {
        fields.push({
          type: "date",
          name: "hired_at",
          label: "入职时间",
          value: hiredAtFor(app.id),
        });
      }
      var result = await global.crmConfirmActionDialog({
        title: "确认变更招聘进展",
        lines: lines,
        hint: hint,
        fields: fields,
        confirmText: "确认",
        cancelText: "取消",
        zIndex: 120,
      });
      if (!result || !result.ok) return;
      await submitProgressConfirm(app.id, targetStatus, mode, result.values || {});
    }

    async function openCorrectionPickerModal(app) {
      if (!app || app.id == null) return;
      if (typeof global.crmConfirmActionDialog !== "function") {
        toast("确认对话框不可用", true);
        return;
      }
      var options = progressOptionsForCorrection(app.status);
      if (!options.length) {
        toast("暂无可选目标状态", true);
        return;
      }
      var hint = "";
      if (normalizeProgressStatus(app.status) === "hired") {
        hint = "若目标不是已入职，确认后将清空入职时间。";
      }
      var result = await global.crmConfirmActionDialog({
        title: "修改招聘进展",
        lines: [
          { label: "候选人", value: appCandidateName(app) },
          { label: "岗位", value: appJobTitle(app) },
          { label: "当前状态", value: progressLabel(app.status) },
          { label: "操作类型", value: "状态修正" },
        ],
        fields: [{
          type: "select",
          name: "to_status",
          label: "目标招聘进展",
          placeholder: "请选择",
          options: options,
        }],
        hint: hint,
        confirmText: "下一步",
        cancelText: "取消",
        zIndex: 120,
      });
      if (!result || !result.ok) return;
      var target = String((result.values && result.values.to_status) || "").trim();
      if (!target) {
        toast("请选择目标状态", true);
        return;
      }
      await openProgressConfirmModal(app, target, "correction");
    }

    return {
      pipelineFilter: pipelineFilter,
      pipelineStatusDropdownOpen: pipelineStatusDropdownOpen,
      pipelineStatusDraft: pipelineStatusDraft,
      pipelineStatusFilterSummary: pipelineStatusFilterSummary,
      togglePipelineStatusDropdown: togglePipelineStatusDropdown,
      togglePipelineStatusDraft: togglePipelineStatusDraft,
      clearPipelineStatusDraft: clearPipelineStatusDraft,
      applyPipelineStatusFilter: applyPipelineStatusFilter,
      resetPipelineFilter: resetPipelineFilter,
      filteredPipelineApplications: filteredPipelineApplications,
      progressOptions: progressOptions,
      progressOptionsForCorrection: progressOptionsForCorrection,
      openCorrectionPickerModal: openCorrectionPickerModal,
      openProgressConfirmModal: openProgressConfirmModal,
      submitProgressConfirm: submitProgressConfirm,
      progressLabel: progressLabel,
      progressTransitionsFor: progressTransitionsFor,
    };
  }

  global.CrmRmsPipeline = {
    createPipelineState: createPipelineState,
  };
})(typeof window !== "undefined" ? window : globalThis);
