# -*- coding: utf-8 -*-
"""金蝶后端配置字段定义

每个后端声明其名称、标签和配置字段。
ConfigManager 使用这些字段动态生成配置界面。
"""

# 后端标识
BACKEND_NAME = "kingdee"
BACKEND_LABEL = "金蝶云星空"
BACKEND_ICON = "🦋"

KINGDEE_CONFIG_FIELDS = [
    {
        "name": "server_url",
        "label": "金蝶服务器地址",
        "type": "text",
        "required": True,
        "placeholder": "http://192.168.1.100/k3cloud/",
        "help": "金蝶云星空 WebAPI 地址，以 /k3cloud/ 结尾"
    },
    {
        "name": "acct_id",
        "label": "账套ID",
        "type": "text",
        "required": True,
        "placeholder": "6304ba61219bf5"
    },
    {
        "name": "user_name",
        "label": "用户名",
        "type": "text",
        "required": True,
        "placeholder": "demo"
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
        "name": "admin_contact",
        "label": "管理员联系方式",
        "type": "text",
        "required": False,
        "placeholder": "admin@company.com",
        "help": "权限提示中显示，方便用户联系管理员"
    },
    {
        "name": "kdcloud_token",
        "label": "金蝶云社区 Token",
        "type": "password",
        "required": False,
        "placeholder": "kdt_xxxxxxxx...",
        "help": "用于产品智能问答功能。访问 https://vip.kingdee.com → 个人主页 → 编辑资料 → 个人访问令牌 获取"
    },
    {
        "name": "kdcloud_product_id",
        "label": "金蝶产品",
        "type": "select",
        "required": False,
        "placeholder": "1",
        "help": "产品智能问答的目标产品",
        "options": [
            {"label": "金蝶AI星空企业版/标准版", "value": "1"},
            {"label": "金蝶AI星瀚", "value": "3"},
            {"label": "金蝶AI星辰", "value": "9"},
            {"label": "金蝶AI苍穹", "value": "87"},
            {"label": "金蝶AI套件", "value": "93"},
            {"label": "EAS Cloud", "value": "11"},
            {"label": "S-HR Cloud", "value": "16"},
            {"label": "精斗云-云会计", "value": "15"},
            {"label": "精斗云-云进销存", "value": "98"},
        ]
    }
]