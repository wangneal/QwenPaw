// @ts-nocheck
/**
 * 金蝶权限管理前端 UI
 *
 * QwenPaw 前端插件入口，注册侧边栏权限管理页面。
 *
 * 需求：
 * - PERM-07: 注册侧边栏权限管理页面
 * - PERM-08: 从 /api/access-control 读取白名单用户
 *
 * React/antd 从宿主获取，不自行打包。
 */

const host = (window as any).QwenPaw?.host;
const React = host?.React;
const antd = host?.antd;
const antdIcons = host?.antdIcons;
const getApiUrl = host?.getApiUrl;
const getApiToken = host?.getApiToken;

const { useState, useEffect, useCallback } = React;
const {
  Table, Button, Modal, Form, Input, Select, Radio, Tag, Space,
  Popconfirm, message, Card, Tooltip, Empty,
} = antd;
const {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  UserOutlined,
  HomeOutlined,
} = antdIcons || {};

// ── API 请求封装 ─────────────────────────────────────────────

async function fetchApi(path, opts) {
  const url = getApiUrl ? getApiUrl(path) : path;
  const token = getApiToken?.();
  const agentId = getSelectedAgentId();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(agentId ? { "X-Agent-Id": agentId } : {}),
  };
  const resp = await fetch(url, { ...opts, headers: { ...headers, ...opts?.headers } });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(text || `HTTP ${resp.status}`);
  }
  return resp.json();
}

function getSelectedAgentId() {
  try {
    const raw =
      sessionStorage.getItem("qwenpaw-agent-storage") ||
      localStorage.getItem("qwenpaw-agent-storage");
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed?.state?.selectedAgent || "default";
    }
  } catch (e) {
    console.warn("[kingdee-admin] 读取当前 Agent 失败:", e);
  }
  return "default";
}

function getDefaultScope() {
  return {
    channel: (window as any).currentChannel || "console",
    user_id: (window as any).currentUserId || "default",
    agent_id: getSelectedAgentId(),
  };
}

function orgContextPath(scope) {
  const params = new URLSearchParams();
  if (scope.channel) params.set("channel", scope.channel);
  if (scope.user_id) params.set("user_id", scope.user_id);
  if (scope.agent_id) params.set("agent_id", scope.agent_id);
  return "/erp-permissions/org-context?" + params.toString();
}

// ── 权限管理页面 ─────────────────────────────────────────────

function PermissionPage() {
  const [permissions, setPermissions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [domainInfo, setDomainInfo] = useState({});
  const [whitelistUsers, setWhitelistUsers] = useState([]);
  const [orgList, setOrgList] = useState([]);
  const [form] = Form.useForm();

  // 查询权限列表
  const fetchPermissions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchApi("/erp-permissions/");
      setPermissions(data.items || []);
    } catch (e) {
      message.error("加载权限列表失败: " + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // 查询业务域列表
  const fetchDomains = useCallback(async () => {
    try {
      const data = await fetchApi("/erp-permissions/meta/domains");
      setDomainInfo(data.systems || {});
    } catch (e) {
      console.warn("[kingdee-admin] 加载业务域失败:", e);
    }
  }, []);

  // 查询白名单用户（PERM-08）
  const fetchWhitelist = useCallback(async () => {
    try {
      const data = await fetchApi("/access-control");
      const users = [];
      for (const [channel, acl] of Object.entries(data)) {
        const whitelist = (acl as any).whitelist || {};
        for (const [key, remark] of Object.entries(whitelist)) {
          users.push({ key, channel, remark: remark as string });
        }
      }
      setWhitelistUsers(users);
    } catch (e) {
      console.warn("[kingdee-admin] 加载白名单失败:", e);
    }
  }, []);

  // 查询金蝶组织列表
  const fetchOrgs = useCallback(async () => {
    try {
      const data = await fetchApi("/erp-permissions/meta/orgs");
      setOrgList(data.orgs || []);
    } catch (e) {
      console.warn("[kingdee-admin] 加载组织列表失败:", e);
    }
  }, []);

  useEffect(() => {
    fetchPermissions();
    fetchDomains();
    fetchWhitelist();
    fetchOrgs();
  }, [fetchPermissions, fetchDomains, fetchWhitelist, fetchOrgs]);

  // 打开新增/编辑弹窗
  const openModal = (record) => {
    setEditing(record || null);
    if (record) {
      form.setFieldsValue(record);
    } else {
      form.resetFields();
      form.setFieldsValue({ access: "readonly", domains: [], org_id: "*" });
    }
    setModalOpen(true);
  };

  // 保存权限（per-org）
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      await fetchApi("/erp-permissions/", {
        method: "POST",
        body: JSON.stringify({
          key: values.key,
          org_id: values.org_id || "*",
          display_name: values.display_name || "",
          domains: values.domains || [],
          access: values.access || "readonly",
        }),
      });
      message.success(editing ? "权限已更新" : "权限已创建");
      setModalOpen(false);
      fetchPermissions();
    } catch (e) {
      if (e.message) message.error("保存失败: " + e.message);
    }
  };

  // 删除指定组织权限
  const handleDelete = async (key, org_id) => {
    try {
      await fetchApi(`/erp-permissions/${encodeURIComponent(key)}/${encodeURIComponent(org_id)}`, {
        method: "DELETE",
      });
      message.success("权限已删除");
      fetchPermissions();
    } catch (e) {
      message.error("删除失败: " + e.message);
    }
  };

  // 业务域选项
  const domainOptions = [];
  for (const [system, info] of Object.entries(domainInfo)) {
    for (const domain of Object.keys((info as any).domains || {})) {
      domainOptions.push({
        label: (info as any).display_name + " / " + domain,
        value: domain,
      });
    }
  }

  // 用户选项（白名单）
  const userOptions = whitelistUsers.map((u) => ({
    label: u.key + (u.remark ? " (" + u.remark + ")" : ""),
    value: u.key,
  }));

  // 组织选项（金蝶 BD_Org）
  const orgOptions = [
    { label: "全部（不限组织）", value: "*" },
    ...orgList.map((o) => ({
      label: o.org_name + " (" + o.org_id + ")",
      value: o.org_id,
    })),
  ];

  // 表格列定义
  const columns = [
    {
      title: "用户标识",
      dataIndex: "key",
      key: "key",
      width: 180,
      render: (text) => React.createElement("code", null, text),
    },
    {
      title: "显示名",
      dataIndex: "display_name",
      key: "display_name",
      width: 100,
    },
    {
      title: "组织",
      dataIndex: "org_name",
      key: "org_name",
      width: 150,
      render: (name, record) => {
        if (record.org_id === "*") return React.createElement(Tag, { color: "default" }, "全部");
        return name || record.org_id;
      },
    },
    {
      title: "业务域",
      dataIndex: "domains",
      key: "domains",
      render: (domains) =>
        React.createElement(
          Space, { size: 4, wrap: true },
          ...(domains || []).map((d) => React.createElement(Tag, { key: d, color: "blue" }, d))
        ),
    },
    {
      title: "访问级别",
      dataIndex: "access",
      key: "access",
      width: 80,
      render: (access) =>
        React.createElement(
          Tag,
          { color: access === "writeable" ? "green" : "default" },
          access === "writeable" ? "读写" : "只读"
        ),
    },
    {
      title: "操作",
      key: "actions",
      width: 100,
      render: (_, record) =>
        React.createElement(
          Space, null,
          React.createElement(
            Tooltip, { title: "编辑" },
            React.createElement(Button, {
              type: "link", size: "small",
              icon: React.createElement(EditOutlined),
              onClick: () => openModal(record),
            })
          ),
          React.createElement(
            Popconfirm, {
              title: `确认删除 ${record.org_id === "*" ? "全部" : record.org_name || record.org_id} 的权限?`,
              onConfirm: () => handleDelete(record.key, record.org_id),
              okText: "删除", cancelText: "取消",
            },
            React.createElement(
              Tooltip, { title: "删除" },
              React.createElement(Button, {
                type: "link", size: "small", danger: true,
                icon: React.createElement(DeleteOutlined),
              })
            )
          )
        ),
    },
  ];

  // 渲染权限管理页面
  return React.createElement(
    "div", { style: { padding: 24 } },
    React.createElement(
      Card, {
        title: React.createElement(Space, null,
          React.createElement(UserOutlined),
          React.createElement("span", null, "金蝶权限管理")
        ),
        extra: React.createElement(
          Space, null,
          React.createElement(Button, {
            icon: React.createElement(ReloadOutlined),
            onClick: () => { fetchPermissions(); fetchOrgs(); },
            children: "刷新",
          }),
          React.createElement(Button, {
            type: "primary",
            icon: React.createElement(PlusOutlined),
            onClick: () => openModal(),
          }, "新增权限")
        ),
      },
      React.createElement("div", {
        style: {
          background: "#e6f4ff", border: "1px solid #91caff",
          borderRadius: 6, padding: "8px 12px", marginBottom: 16,
          fontSize: 12, color: "#0958d9",
        },
      }, "按组织配置权限：同一用户在不同组织可有不同业务域和访问级别。"),
      React.createElement(Table, {
        dataSource: permissions,
        columns,
        rowKey: (r) => r.key + ":" + r.org_id,
        loading,
        pagination: { pageSize: 20, showSizeChanger: true, showTotal: (t) => "共 " + t + " 条" },
        size: "middle",
      })
    ),

    // 新增/编辑弹窗
    React.createElement(
      Modal, {
        title: editing ? "编辑权限" : "新增权限",
        open: modalOpen,
        onOk: handleSave,
        onCancel: () => setModalOpen(false),
        okText: "保存",
        cancelText: "取消",
        destroyOnClose: true,
        width: 520,
      },
      React.createElement(
        Form, { form, layout: "vertical", preserve: false },
        // 用户选择（白名单）
        React.createElement(
          Form.Item, {
            name: "key",
            label: "用户",
            rules: [{ required: true, message: "请选择用户" }],
            extra: "从 QwenPaw 白名单中选择",
          },
          React.createElement(Select, {
            showSearch: true,
            placeholder: "选择白名单用户",
            options: userOptions,
            disabled: !!editing,
            filterOption: (input, option) =>
              (option?.label ?? "").toLowerCase().includes(input.toLowerCase()),
            notFoundContent: React.createElement(Empty, {
              description: "白名单为空，请先在 QwenPaw Console 审批用户",
              image: Empty.PRESENTED_IMAGE_SIMPLE,
            }),
          })
        ),
        // 显示名
        React.createElement(
          Form.Item, { name: "display_name", label: "显示名" },
          React.createElement(Input, { placeholder: "张三" })
        ),
        // 组织选择（从金蝶查询）
        React.createElement(
          Form.Item, {
            name: "org_id",
            label: "组织",
            rules: [{ required: true, message: "请选择组织" }],
            extra: "选择该用户可操作的组织",
            initialValue: "*",
          },
          React.createElement(Select, {
            showSearch: true,
            placeholder: "选择组织",
            options: orgOptions,
            filterOption: (input, option) =>
              (option?.label ?? "").toLowerCase().includes(input.toLowerCase()),
          })
        ),
        // 业务域
        React.createElement(
          Form.Item, {
            name: "domains",
            label: "业务域",
            extra: "选择该用户在此组织下可访问的业务域",
          },
          React.createElement(Select, {
            mode: "multiple",
            placeholder: "选择业务域",
            options: domainOptions,
            showSearch: true,
            filterOption: (input, option) =>
              (option?.label ?? "").toLowerCase().includes(input.toLowerCase()),
          })
        ),
        // 访问级别
        React.createElement(
          Form.Item, { name: "access", label: "访问级别", initialValue: "readonly" },
          React.createElement(
            Radio.Group, null,
            React.createElement(Radio, { value: "readonly" }, "只读"),
            React.createElement(Radio, { value: "writeable" }, "读写")
          )
        )
      )
    )
  );
}

// ── 默认组织页面 ─────────────────────────────────────────────

function OrgContextPage() {
  const [orgList, setOrgList] = useState([]);
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const orgOptions = orgList.map((o) => ({
    label: o.org_name + " (" + o.org_id + ")",
    value: o.org_id,
  }));

  const fetchOrgs = useCallback(async () => {
    try {
      const data = await fetchApi("/erp-permissions/meta/orgs");
      setOrgList(data.orgs || []);
    } catch (e) {
      console.warn("[kingdee-admin] 加载组织列表失败:", e);
    }
  }, []);

  const fetchContext = useCallback(async (scope) => {
    setLoading(true);
    try {
      const data = await fetchApi(orgContextPath(scope));
      setContext(data);
      form.setFieldsValue({
        channel: data.channel || scope.channel,
        user_id: data.user_id || scope.user_id,
        agent_id: data.agent_id || scope.agent_id,
        org_id: data.org_id || undefined,
      });
    } catch (e) {
      message.error("加载默认组织失败: " + e.message);
    } finally {
      setLoading(false);
    }
  }, [form]);

  useEffect(() => {
    const scope = getDefaultScope();
    form.setFieldsValue(scope);
    fetchOrgs();
    fetchContext(scope);
  }, [fetchOrgs, fetchContext, form]);

  const handleLoad = async () => {
    const values = await form.validateFields(["channel", "user_id", "agent_id"]);
    await fetchContext(values);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const data = await fetchApi("/erp-permissions/org-context", {
        method: "PUT",
        body: JSON.stringify(values),
      });
      if (data.status === "error") {
        message.error(data.message || "保存失败");
        return;
      }
      setContext(data);
      message.success("默认组织已保存");
    } catch (e) {
      if (e.message) message.error("保存失败: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    try {
      const values = await form.validateFields(["channel", "user_id", "agent_id"]);
      await fetchApi(orgContextPath(values), { method: "DELETE" });
      setContext({ ...values, org_id: "", org_name: "" });
      form.setFieldsValue({ org_id: undefined });
      message.success("默认组织已清除");
    } catch (e) {
      message.error("清除失败: " + e.message);
    }
  };

  return React.createElement(
    "div", { style: { padding: 24 } },
    React.createElement(
      Card, {
        title: React.createElement(Space, null,
          React.createElement(HomeOutlined),
          React.createElement("span", null, "金蝶默认组织")
        ),
        extra: React.createElement(
          Space, null,
          React.createElement(Button, {
            icon: React.createElement(ReloadOutlined),
            onClick: handleLoad,
            loading,
          }, "刷新"),
          React.createElement(Button, {
            danger: true,
            onClick: handleClear,
          }, "清除"),
          React.createElement(Button, {
            type: "primary",
            onClick: handleSave,
            loading: saving,
          }, "保存")
        ),
      },
      React.createElement("div", {
        style: {
          background: "#f6ffed", border: "1px solid #b7eb8f",
          borderRadius: 6, padding: "8px 12px", marginBottom: 16,
          fontSize: 12, color: "#237804",
        },
      }, "默认组织按 Agent + 渠道 + 用户保存。对话中不主动切换组织时，金蝶工具会一直使用这里设置的组织。"),
      context?.org_id ? React.createElement(
        "div", {
          style: {
            marginBottom: 16, padding: "10px 12px",
            border: "1px solid #d9d9d9", borderRadius: 6,
          },
        },
        React.createElement(Space, { wrap: true },
          React.createElement("span", null, "当前默认组织:"),
          React.createElement(Tag, { color: "green" }, context.org_name || context.org_id),
          React.createElement("code", null, context.context_key || "")
        )
      ) : React.createElement(
        "div", {
          style: {
            marginBottom: 16, padding: "10px 12px",
            border: "1px solid #ffd591", borderRadius: 6,
            color: "#ad6800", background: "#fff7e6",
          },
        },
        "当前作用域尚未设置默认组织。"
      ),
      React.createElement(
        Form, { form, layout: "vertical" },
        React.createElement(
          Space, { align: "start", wrap: true, style: { width: "100%" } },
          React.createElement(
            Form.Item, {
              name: "channel",
              label: "渠道",
              rules: [{ required: true, message: "请输入渠道" }],
            },
            React.createElement(Input, { style: { width: 160 }, placeholder: "console" })
          ),
          React.createElement(
            Form.Item, {
              name: "user_id",
              label: "用户",
              rules: [{ required: true, message: "请输入用户" }],
            },
            React.createElement(Input, { style: { width: 180 }, placeholder: "default" })
          ),
          React.createElement(
            Form.Item, {
              name: "agent_id",
              label: "Agent",
              rules: [{ required: true, message: "请输入 Agent" }],
            },
            React.createElement(Input, { style: { width: 180 }, placeholder: "default" })
          )
        ),
        React.createElement(
          Form.Item, {
            name: "org_id",
            label: "默认组织",
            rules: [{ required: true, message: "请选择默认组织" }],
          },
          React.createElement(Select, {
            showSearch: true,
            placeholder: "选择金蝶组织",
            options: orgOptions,
            loading,
            filterOption: (input, option) =>
              (option?.label ?? "").toLowerCase().includes(input.toLowerCase()),
          })
        )
      )
    )
  );
}

// ── 审计日志页面 ─────────────────────────────────────────────

function AuditLogPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ operator: "", action: "", form_id: "" });

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (filters.operator) params.set("operator", filters.operator);
      if (filters.action) params.set("action", filters.action);
      if (filters.form_id) params.set("form_id", filters.form_id);
      const data = await fetchApi("/erp-permissions/audit-log?" + params.toString());
      setLogs(data || []);
    } catch (e) {
      message.error("加载审计日志失败: " + e.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const ACTION_LABELS = {
    save: { text: "保存", color: "blue" },
    delete: { text: "删除", color: "red" },
    submit: { text: "提交", color: "cyan" },
    audit: { text: "审核", color: "green" },
    unaudit: { text: "反审核", color: "orange" },
    push: { text: "下推", color: "purple" },
    execute_op: { text: "操作", color: "geekblue" },
  };

  const columns = [
    { title: "时间", dataIndex: "created_at", key: "created_at", width: 160 },
    {
      title: "操作人", dataIndex: "operator", key: "operator", width: 180,
      render: (v) => React.createElement("code", null, v),
    },
    {
      title: "操作", dataIndex: "action", key: "action", width: 80,
      render: (v) => {
        const label = ACTION_LABELS[v] || { text: v, color: "default" };
        return React.createElement(Tag, { color: label.color }, label.text);
      },
    },
    { title: "表单", dataIndex: "form_id", key: "form_id", width: 150 },
    { title: "目标", dataIndex: "target", key: "target", width: 120 },
    { title: "详情", dataIndex: "detail", key: "detail", ellipsis: true },
  ];

  return React.createElement(
    "div", { style: { padding: 24 } },
    React.createElement(
      Card, {
        title: React.createElement(Space, null,
          React.createElement("span", null, "📋"),
          React.createElement("span", null, "操作审计日志")
        ),
        extra: React.createElement(Button, {
          icon: React.createElement(ReloadOutlined),
          onClick: fetchLogs, children: "刷新",
        }),
      },
      React.createElement(
        Space, { style: { marginBottom: 16 }, wrap: true },
        React.createElement(Input, {
          placeholder: "操作人",
          value: filters.operator,
          onChange: (e) => setFilters({ ...filters, operator: e.target.value }),
          style: { width: 180 },
          allowClear: true,
        }),
        React.createElement(Select, {
          placeholder: "操作类型",
          value: filters.action || undefined,
          onChange: (v) => setFilters({ ...filters, action: v || "" }),
          style: { width: 120 },
          allowClear: true,
          options: Object.entries(ACTION_LABELS).map(([k, v]) => ({
            label: (v as any).text, value: k,
          })),
        }),
        React.createElement(Input, {
          placeholder: "FormId",
          value: filters.form_id,
          onChange: (e) => setFilters({ ...filters, form_id: e.target.value }),
          style: { width: 150 },
          allowClear: true,
        }),
        React.createElement(Button, { type: "primary", onClick: fetchLogs }, "查询")
      ),
      React.createElement(Table, {
        dataSource: logs,
        columns,
        rowKey: "id",
        loading,
        pagination: { pageSize: 50, showSizeChanger: true, showTotal: (t) => "共 " + t + " 条" },
        size: "small",
      })
    )
  );
}

// ── 插件注册 ─────────────────────────────────────────────────

function init() {
  const QwenPaw = (window as any).QwenPaw;
  if (!QwenPaw) {
    console.error("[kingdee-admin] QwenPaw 不可用");
    return;
  }

  if (QwenPaw.registerRoutes) {
    QwenPaw.registerRoutes("kingdee-admin", [
      {
        path: "/permissions",
        component: PermissionPage,
        label: "金蝶权限管理",
        icon: "🔐",
      },
      {
        path: "/org-context",
        component: OrgContextPage,
        label: "金蝶默认组织",
        icon: "🏢",
      },
      {
        path: "/audit-log",
        component: AuditLogPage,
        label: "操作审计日志",
        icon: "📋",
      },
    ]);
    console.log("[kingdee-admin] 路由注册完成: permissions, audit-log");
  }
}

init();
export default init;
