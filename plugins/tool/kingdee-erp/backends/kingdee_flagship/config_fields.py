# -*- coding: utf-8 -*-
"""金蝶云星空旗舰版后端配置字段定义"""

# 后端标识
BACKEND_NAME = "kingdee_flagship"
BACKEND_LABEL = "金蝶云星空旗舰版"
BACKEND_ICON = "🌟"

FLAGSHIP_CONFIG_FIELDS = [
    {
        "name": "server_url",
        "label": "旗舰版服务器地址",
        "type": "text",
        "required": True,
        "placeholder": "https://kmlt.test.kdgalaxy.com",
        "help": "金蝶云星空旗舰版 API 地址（不需要 /k3cloud/ 后缀）"
    },
    {
        "name": "app_id",
        "label": "应用ID",
        "type": "text",
        "required": True,
        "placeholder": "225649_xxxxx"
    },
    {
        "name": "app_secret",
        "label": "应用密钥",
        "type": "password",
        "required": True,
        "placeholder": "xxxxx"
    },
    {
        "name": "tenantid",
        "label": "租户ID",
        "type": "text",
        "required": True,
        "placeholder": "default_tenant",
        "help": "云星空旗舰版租户ID"
    },
    {
        "name": "account_id",
        "label": "账套ID",
        "type": "text",
        "required": True,
        "placeholder": "100001",
        "help": "云星空旗舰版账套ID"
    },
    {
        "name": "user_name",
        "label": "用户名",
        "type": "text",
        "required": True,
        "placeholder": "demo",
        "help": "旗舰版登录用户名"
    },
    {
        "name": "kd_language",
        "label": "语言",
        "type": "select",
        "required": False,
        "default": "zh_CN",
        "help": "旗舰版登录语言",
        "options": [
            {"label": "简体中文", "value": "zh_CN"},
            {"label": "繁体中文", "value": "zh_TW"},
            {"label": "English", "value": "en_US"}
        ]
    },
    {
        "name": "admin_contact",
        "label": "管理员联系方式",
        "type": "text",
        "required": False,
        "placeholder": "admin@company.com",
        "help": "权限提示中显示，方便用户联系管理员"
    },
]
