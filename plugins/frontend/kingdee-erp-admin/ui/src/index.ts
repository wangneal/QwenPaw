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
  Table, Button, Modal, Form, Input, InputNumber, Select, Radio, Switch, Tag, Space,
  Popconfirm, message, Card, Tooltip, Empty, Tabs, Divider,
} = antd;
const {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, UserOutlined,
  SettingOutlined, LinkOutlined, SaveOutlined, SearchOutlined, ApiOutlined,
} = antdIcons || {};

// ── API 请求封装 ─────────────────────────────────────────────

async function fetchApi(path, opts) {
  const url = getApiUrl ? getApiUrl(path) : path;
  const token = getApiToken?.();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const resp = await fetch(url, { ...opts, headers: { ...headers, ...opts?.headers } });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(text || `HTTP ${resp.status}`);
  }
  return resp.json();
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
      const orgs = data.orgs || [];
      setOrgList(orgs);
      if (orgs.length === 0) {
        message.warning("未获取到金蝶组织列表，请先在「连接配置」中填写金蝶连接参数");
      }
    } catch (e) {
      console.warn("[kingdee-admin] 加载组织列表失败:", e);
      message.warning("获取组织列表失败，请检查金蝶连接配置");
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
  const domainLabelMap: Record<string, string> = {};  // domain key → 中文名
  const domainOptions = [];
  for (const [system, info] of Object.entries(domainInfo)) {
    const domains = (info as any).domains || {};
    for (const [domainKey, domainVal] of Object.entries(domains)) {
      const label = (domainVal as any)?.label || domainKey;
      domainLabelMap[domainKey] = label;
      domainOptions.push({
        label: label,
        value: domainKey,
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
          ...(domains || []).map((d) => React.createElement(Tag, { key: d, color: "blue" }, domainLabelMap[d] || d))
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

// ── 连接配置页面（多厂商页签化） ──────────────────────────────

function ConnectionConfigPage() {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [backends, setBackends] = useState([]);
  const [activeBackend, setActiveBackend] = useState("");
  const [configFields, setConfigFields] = useState([]);
  const [configValues, setConfigValues] = useState({});
  const [configured, setConfigured] = useState({});
  const [testResult, setTestResult] = useState(null);
  const [form] = Form.useForm();

  // 加载所有后端列表
  const fetchBackends = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchApi("/erp-permissions/config/backends");
      const list = data.backends || [];
      setBackends(list);
      // 设置配置状态
      const cfgMap = {};
      list.forEach((b) => { cfgMap[b.name] = b.configured; });
      setConfigured(cfgMap);
      // 默认选中第一个后端
      if (list.length > 0 && !activeBackend) {
        setActiveBackend(list[0].name);
      }
    } catch (e) {
      console.warn("[erp-admin] 加载后端列表失败:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  // 加载指定后端的配置
  const fetchConfig = useCallback(async (backendName) => {
    if (!backendName) return;
    try {
      const data = await fetchApi("/erp-permissions/config/" + backendName);
      setConfigFields(data.config_fields || []);
      setConfigValues(data.config || {});
      form.setFieldsValue(data.config || {});
      setTestResult(null);
    } catch (e) {
      console.warn("[erp-admin] 加载配置失败:", e);
      setConfigFields([]);
      setConfigValues({});
    }
  }, [form]);

  useEffect(() => { fetchBackends(); }, [fetchBackends]);
  useEffect(() => { if (activeBackend) fetchConfig(activeBackend); }, [activeBackend, fetchConfig]);

  // 切换后端页签
  const handleTabChange = (key) => {
    setActiveBackend(key);
    form.resetFields();
  };

  // 根据 config_fields 动态渲染表单项
  const renderFormField = (fieldDef) => {
    const { name, label, type, required, placeholder, help, options, min, max } = fieldDef;
    const rules = required ? [{ required: true, message: "请输入" + label }] : [];

    let inputEl;
    switch (type) {
      case "password":
        inputEl = React.createElement(Input.Password, { placeholder, autoComplete: "off" });
        break;
      case "number":
        inputEl = React.createElement(InputNumber, { placeholder, min, max, style: { width: "100%" } });
        break;
      case "boolean":
        return React.createElement(Form.Item, {
          name, label, valuePropName: "checked", rules,
        }, React.createElement(Switch));
      case "select":
        inputEl = React.createElement(Select, {
          placeholder,
          children: (options || []).map((opt) =>
            React.createElement(Select.Option, {
              key: typeof opt === "string" ? opt : opt.value,
              value: typeof opt === "string" ? opt : opt.value,
              children: typeof opt === "string" ? opt : opt.label,
            })
          ),
        });
        break;
      case "textarea":
        inputEl = React.createElement(Input.TextArea, { placeholder, rows: 4, autoSize: { minRows: 2, maxRows: 8 } });
        break;
      default:
        inputEl = React.createElement(Input, { placeholder });
    }

    return React.createElement(Form.Item, {
      name, label, rules, extra: help,
    }, inputEl);
  };

  // 保存配置
  const handleSave = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();
      await fetchApi("/erp-permissions/config/" + activeBackend, {
        method: "POST",
        body: JSON.stringify({ config: values }),
      });
      message.success("配置已保存");
      // 刷新配置状态
      setConfigured((prev) => ({ ...prev, [activeBackend]: true }));
      setConfigValues(values);
    } catch (e) {
      if (e.message) message.error("保存失败: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  // 测试连接
  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const values = form.getFieldsValue();
      const result = await fetchApi("/erp-permissions/config/" + activeBackend + "/test", {
        method: "POST",
        body: JSON.stringify({ config: values }),
      });
      setTestResult(result);
      if (result.success) {
        message.success(result.message || "连接成功");
      } else {
        message.error(result.message || "连接失败");
      }
    } catch (e) {
      setTestResult({ success: false, message: e.message });
      message.error("测试失败: " + e.message);
    } finally {
      setTesting(false);
    }
  };

  // 生成页签
  const tabItems = backends.map((b) => ({
    key: b.name,
    label: React.createElement(Space, null,
      React.createElement("span", null, b.label),
      React.createElement(Tag, {
        color: configured[b.name] ? "success" : "warning",
        style: { marginLeft: 4, fontSize: 11 },
      }, configured[b.name] ? "✓" : "未配置")
    ),
    children: React.createElement("div", { key: "content-" + b.name },
      React.createElement("div", {
        style: {
          background: "#e6f4ff", border: "1px solid #91caff",
          borderRadius: 6, padding: "8px 12px", marginBottom: 16,
          fontSize: 12, color: "#0958d9",
        },
      }, "配置" + b.label + "连接参数，保存后即可使用相关功能。"),
      React.createElement(
        Form, {
          form,
          layout: "vertical",
          style: { maxWidth: 560 },
        },
        (activeBackend === b.name ? configFields : []).map((field) => renderFormField(field))
      ),
      activeBackend === b.name && testResult && React.createElement(
        "div", {
          style: {
            marginTop: 12, padding: "8px 12px", borderRadius: 6,
            background: testResult.success ? "#f6ffed" : "#fff2f0",
            border: `1px solid ${testResult.success ? "#b7eb8f" : "#ffccc7"}`,
            color: testResult.success ? "#389e0d" : "#cf1322",
            fontSize: 13,
          },
        },
        React.createElement("span", null, testResult.message)
      ),
      React.createElement(
        Space, { style: { marginTop: 16 } },
        React.createElement(Button, {
          type: "primary",
          icon: React.createElement(SaveOutlined),
          loading: activeBackend === b.name ? saving : false,
          onClick: activeBackend === b.name ? handleSave : undefined,
          children: "保存配置",
        }),
        React.createElement(Button, {
          icon: React.createElement(ApiOutlined),
          loading: activeBackend === b.name ? testing : false,
          onClick: activeBackend === b.name ? handleTest : undefined,
          children: "测试连接",
        }),
        React.createElement(Button, {
          icon: React.createElement(ReloadOutlined),
          onClick: () => fetchConfig(b.name),
          children: "重新加载",
        })
      )
    ),
  }));

  return React.createElement(
    "div", { style: { padding: 24 } },
    React.createElement(
      Card, {
        title: React.createElement(Space, null,
          React.createElement(SettingOutlined),
          React.createElement("span", null, "ERP 连接配置")
        ),
      },
      backends.length === 0 && !loading
        ? React.createElement(Empty, { description: "暂无可配置的 ERP 后端" })
        : React.createElement(
          Tabs, {
            activeKey: activeBackend,
            onChange: handleTabChange,
            items: tabItems,
          }
        )
    )
  );
}

// ── 字段映射页面 ─────────────────────────────────────────────

function FieldMappingPage() {
  const [mappings, setMappings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [domain, setDomain] = useState("");
  const [activeTab, setActiveTab] = useState("common");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRecord, setDetailRecord] = useState(null);
  const [fieldRows, setFieldRows] = useState([]);
  const [form] = Form.useForm();

  // 加载字段映射列表
  const fetchMappings = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (domain) params.set("domain", domain);
      if (activeTab === "custom") params.set("source", "custom");
      const data = await fetchApi("/erp-permissions/field-mappings?" + params.toString());
      setMappings(data.items || data || []);
    } catch (e) {
      message.error("加载字段映射失败: " + e.message);
    } finally {
      setLoading(false);
    }
  }, [search, domain, activeTab]);

  useEffect(() => { fetchMappings(); }, [fetchMappings]);

  // 打开新增/编辑弹窗
  const openModal = (record) => {
    setEditing(record || null);
    if (record) {
      form.setFieldsValue({ form_id: record.form_id, form_name: record.form_name });
      setFieldRows((record.fields || []).map((f, i) => ({ ...f, _key: i })));
    } else {
      form.resetFields();
      setFieldRows([]);
    }
    setModalOpen(true);
  };

  // 添加空字段行
  const addFieldRow = () => {
    setFieldRows((prev) => [...prev, { field_key: "", display_name: "", field_type: "text", _key: Date.now() }]);
  };

  // 删除字段行
  const removeFieldRow = (idx) => {
    setFieldRows((prev) => prev.filter((_, i) => i !== idx));
  };

  // 更新字段行
  const updateFieldRow = (idx, field, value) => {
    setFieldRows((prev) => prev.map((row, i) => i === idx ? { ...row, [field]: value } : row));
  };

  // 保存映射
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      await fetchApi("/erp-permissions/field-mappings", {
        method: "PUT",
        body: JSON.stringify({
          form_id: values.form_id,
          form_name: values.form_name,
          fields: fieldRows.map(({ _key, ...rest }) => rest),
        }),
      });
      message.success(editing ? "映射已更新" : "映射已创建");
      setModalOpen(false);
      fetchMappings();
    } catch (e) {
      if (e.message) message.error("保存失败: " + e.message);
    }
  };

  // 删除映射
  const handleDelete = async (form_id) => {
    try {
      await fetchApi(`/erp-permissions/field-mappings/${encodeURIComponent(form_id)}`, {
        method: "DELETE",
      });
      message.success("映射已删除");
      fetchMappings();
    } catch (e) {
      message.error("删除失败: " + e.message);
    }
  };

  // 查看详情
  const openDetail = (record) => {
    setDetailRecord(record);
    setDetailOpen(true);
  };

  // 业务域选项
  const domainOptions = [
    { label: "全部", value: "" },
    { label: "销售", value: "sales" },
    { label: "采购", value: "procurement" },
    { label: "库存", value: "inventory" },
    { label: "财务", value: "finance" },
    { label: "生产", value: "production" },
    { label: "基础资料", value: "base" },
  ];

  // 表格列定义
  const columns = [
    {
      title: "FormId",
      dataIndex: "form_id",
      key: "form_id",
      width: 180,
      render: (text) => React.createElement("code", null, text),
    },
    {
      title: "表单名称",
      dataIndex: "form_name",
      key: "form_name",
      width: 120,
    },
    {
      title: "来源",
      dataIndex: "source",
      key: "source",
      width: 80,
      render: (v) => React.createElement(Tag, {
        color: v === "custom" ? "blue" : "default",
      }, v === "custom" ? "自定义" : "元数据"),
    },
    {
      title: "字段数量",
      dataIndex: "fields",
      key: "field_count",
      width: 80,
      render: (fields) => (fields || []).length,
    },
    {
      title: "操作",
      key: "actions",
      width: 120,
      render: (_, record) => {
        const isCustom = record.source === "custom";
        const hasFields = (record.fields || []).length > 0;
        return React.createElement(
          Space, null,
          hasFields ? React.createElement(
            Tooltip, { title: "查看字段" },
            React.createElement(Button, {
              type: "link", size: "small",
              onClick: () => openDetail(record),
              children: "查看",
            })
          ) : null,
          React.createElement(
            Tooltip, { title: isCustom ? "编辑" : "自定义" },
            React.createElement(Button, {
              type: "link", size: "small",
              icon: React.createElement(EditOutlined),
              onClick: () => openModal(record),
            })
          ),
          isCustom ? React.createElement(
            Popconfirm, {
              title: `确认删除映射 ${record.form_id}?`,
              onConfirm: () => handleDelete(record.form_id),
              okText: "删除", cancelText: "取消",
            },
            React.createElement(
              Tooltip, { title: "删除" },
              React.createElement(Button, {
                type: "link", size: "small", danger: true,
                icon: React.createElement(DeleteOutlined),
              })
            )
          ) : null
        );
      },
    },
  ];

  // 详情子表列
  const detailColumns = [
    { title: "字段标识", dataIndex: "field_key", key: "field_key", width: 180 },
    { title: "显示名称", dataIndex: "display_name", key: "display_name", width: 150 },
    { title: "字段类型", dataIndex: "field_type", key: "field_type", width: 100 },
  ];

  // 渲染页面
  return React.createElement(
    "div", { style: { padding: 24 } },
    React.createElement(
      Card, {
        title: React.createElement(Space, null,
          React.createElement(LinkOutlined),
          React.createElement("span", null, "金蝶字段映射管理")
        ),
        extra: React.createElement(Button, {
          type: "primary",
          icon: React.createElement(PlusOutlined),
          onClick: () => openModal(),
        }, "新增映射"),
      },
      // 搜索栏
      React.createElement(
        Space, { style: { marginBottom: 16 }, wrap: true },
        React.createElement(Input, {
          placeholder: "搜索 FormId 或表单名称",
          value: search,
          onChange: (e) => setSearch(e.target.value),
          style: { width: 240 },
          allowClear: true,
          prefix: React.createElement(SearchOutlined),
        }),
        React.createElement(Select, {
          placeholder: "业务域",
          value: domain || undefined,
          onChange: (v) => setDomain(v || ""),
          style: { width: 120 },
          allowClear: true,
          options: domainOptions,
        }),
        React.createElement(Button, {
          icon: React.createElement(ReloadOutlined),
          onClick: fetchMappings,
          children: "刷新",
        })
      ),
      // Tabs 切换
      React.createElement(
        Tabs, {
          activeKey: activeTab,
          onChange: (key) => setActiveTab(key),
          items: [
            {
              key: "common",
              label: "常用表单",
              children: React.createElement(Table, {
                dataSource: mappings,
                columns,
                rowKey: "form_id",
                loading,
                pagination: { pageSize: 20, showSizeChanger: true, showTotal: (t) => "共 " + t + " 条" },
                size: "middle",
              }),
            },
            {
              key: "custom",
              label: "自定义映射",
              children: React.createElement(Table, {
                dataSource: mappings,
                columns,
                rowKey: "form_id",
                loading,
                pagination: { pageSize: 20, showSizeChanger: true, showTotal: (t) => "共 " + t + " 条" },
                size: "middle",
              }),
            },
          ],
        }
      )
    ),

    // 新增/编辑弹窗
    React.createElement(
      Modal, {
        title: editing ? "编辑字段映射" : "新增字段映射",
        open: modalOpen,
        onOk: handleSave,
        onCancel: () => setModalOpen(false),
        okText: "保存",
        cancelText: "取消",
        destroyOnClose: true,
        width: 680,
      },
      React.createElement(
        Form, { form, layout: "vertical", preserve: false },
        React.createElement(
          Form.Item, {
            name: "form_id",
            label: "FormId",
            rules: [{ required: true, message: "请输入 FormId" }],
          },
          React.createElement(Input, {
            placeholder: "SAL_SaleOrder",
            disabled: !!editing,
          })
        ),
        React.createElement(
          Form.Item, {
            name: "form_name",
            label: "表单名称",
            rules: [{ required: true, message: "请输入表单名称" }],
          },
          React.createElement(Input, { placeholder: "销售订单" })
        ),
        React.createElement(Divider, { orientation: "left", plain: true }, "字段列表"),
        // 字段行
        ...fieldRows.map((row, idx) =>
          React.createElement(
            Space, {
              key: row._key,
              style: { display: "flex", marginBottom: 8, width: "100%" },
              align: "start",
            },
            React.createElement(Input, {
              placeholder: "字段标识",
              value: row.field_key,
              onChange: (e) => updateFieldRow(idx, "field_key", e.target.value),
              style: { width: 180 },
            }),
            React.createElement(Input, {
              placeholder: "显示名称",
              value: row.display_name,
              onChange: (e) => updateFieldRow(idx, "display_name", e.target.value),
              style: { width: 160 },
            }),
            React.createElement(Input, {
              placeholder: "类型",
              value: row.field_type,
              onChange: (e) => updateFieldRow(idx, "field_type", e.target.value),
              style: { width: 100 },
            }),
            React.createElement(Button, {
              type: "text",
              danger: true,
              icon: React.createElement(DeleteOutlined),
              onClick: () => removeFieldRow(idx),
            })
          )
        ),
        React.createElement(Button, {
          type: "dashed",
          block: true,
          icon: React.createElement(PlusOutlined),
          onClick: addFieldRow,
          children: "添加字段",
          style: { marginTop: 4 },
        })
      )
    ),

    // 详情弹窗
    React.createElement(
      Modal, {
        title: detailRecord ? detailRecord.form_id + " - " + detailRecord.form_name : "字段详情",
        open: detailOpen,
        onCancel: () => setDetailOpen(false),
        footer: null,
        destroyOnClose: true,
        width: 520,
      },
      detailRecord && React.createElement(Table, {
        dataSource: detailRecord.fields || [],
        columns: detailColumns,
        rowKey: "field_key",
        pagination: false,
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
        path: "/audit-log",
        component: AuditLogPage,
        label: "操作审计日志",
        icon: "📋",
      },
      {
        path: "/kd-config",
        component: ConnectionConfigPage,
        label: "连接配置",
        icon: "⚙️",
      },
      {
        path: "/kd-mapping",
        component: FieldMappingPage,
        label: "字段映射",
        icon: "🔗",
      },
    ]);
    console.log("[kingdee-admin] 路由注册完成: permissions, audit-log, kd-config, kd-mapping");
  }
}

init();
export default init;
