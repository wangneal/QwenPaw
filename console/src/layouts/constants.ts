// ── URLs ──────────────────────────────────────────────────────────────────

export const PYPI_URL = "";

export const GITHUB_URL = "" as const;

// ── Timing ────────────────────────────────────────────────────────────────

export const ONE_HOUR_MS = 60 * 60 * 1000;

// ── Navigation ────────────────────────────────────────────────────────────

export const DEFAULT_OPEN_KEYS = [
  "chat-group",
  "control-group",
  "agent-group",
  "settings-group",
];

export const KEY_TO_PATH: Record<string, string> = {
  chat: "/chat",
  channels: "/channels",
  sessions: "/sessions",
  inbox: "/inbox",
  "cron-jobs": "/cron-jobs",
  heartbeat: "/heartbeat",
  skills: "/skills",
  "skill-pool": "/skill-pool",
  market: "/market",
  tools: "/tools",
  mcp: "/mcp",
  acp: "/acp",
  workspace: "/workspace",
  agents: "/agents",
  models: "/models",
  environments: "/environments",
  "agent-config": "/agent-config",
  security: "/security",
  "token-usage": "/token-usage",
  "agent-stats": "/agent-stats",
  "voice-transcription": "/voice-transcription",
  debug: "/debug",
  backups: "/backups",
  "plugin-manager": "/plugin-manager",
};

export const KEY_TO_LABEL: Record<string, string> = {
  chat: "nav.chat",
  channels: "nav.channels",
  sessions: "nav.sessions",
  inbox: "nav.inbox",
  "cron-jobs": "nav.cronJobs",
  heartbeat: "nav.heartbeat",
  skills: "nav.skills",
  "skill-pool": "nav.skillPool",
  market: "nav.market",
  tools: "nav.tools",
  mcp: "nav.mcp",
  acp: "nav.acp",
  "agent-config": "nav.agentConfig",
  workspace: "nav.workspace",
  models: "nav.models",
  environments: "nav.environments",
  security: "nav.security",
  "token-usage": "nav.tokenUsage",
  agents: "nav.agents",
  debug: "nav.debug",
  backups: "nav.backups",
};

// ── URL helpers ───────────────────────────────────────────────────────────

export const getWebsiteLang = (lang: string): string =>
  lang.startsWith("zh") ? "zh" : "en";

export const getDocsUrl = (lang: string): string =>
  `/api/erp/docs?lang=${getWebsiteLang(lang)}`;

export const getFaqUrl = (lang: string): string =>
  `/api/erp/docs/faq?lang=${getWebsiteLang(lang)}`;

export const getReleaseNotesUrl = (lang: string): string =>
  `/api/erp/docs/release-notes?lang=${getWebsiteLang(lang)}`;

export const getFeatureDemosUrl = (lang: string): string =>
  `/api/erp/docs/functiondemo?lang=${getWebsiteLang(lang)}`;

// ── Version helpers ────────────────────────────────────────────────────────

// Filter out pre-release versions; post-releases are treated as stable.
// PEP 440 pre-release suffixes: aN / bN / rcN (or cN) / devN.
export const isStableVersion = (v: string): boolean =>
  !/(\d)(a|alpha|b|beta|rc|c|dev)\d*/i.test(v);

// Compare two PEP 440 version strings. Returns >0 if a>b, <0 if a<b, 0 if equal.
// .postN releases sort after their base version (e.g. 1.0.0.post1 > 1.0.0).
// Pre-release versions (aN, bN, rcN) sort before their base version.
export const compareVersions = (a: string, b: string): number => {
  const normalise = (v: string): number[] => {
    // Handle .postN suffix
    const postMatch = v.match(/\.post(\d+)$/i);
    const postNum = postMatch ? Number(postMatch[1]) : 0;
    const baseVersion = v.replace(/\.post\d+$/i, "");

    // Handle pre-release suffix (e.g., 1.0.1b1 -> base=1.0.1, preType=b, preNum=1)
    const preMatch = baseVersion.match(/^(.+?)(a|alpha|b|beta|rc|c)(\d*)$/i);
    let coreVersion = baseVersion;
    let preType = 0; // 0 = stable, -3 = alpha, -2 = beta, -1 = rc
    let preNum = 0;
    if (preMatch) {
      coreVersion = preMatch[1];
      const preLabel = preMatch[2].toLowerCase();
      preType =
        preLabel === "a" || preLabel === "alpha"
          ? -3
          : preLabel === "b" || preLabel === "beta"
          ? -2
          : -1; // rc or c
      preNum = preMatch[3] ? Number(preMatch[3]) : 0;
    }

    const parts = coreVersion.split(/[.\-]/).map((seg) => Number(seg) || 0);
    // Append: preType (0 for stable, negative for pre-release), preNum, postNum
    return [...parts, preType, preNum, postNum];
  };

  const aN = normalise(a);
  const bN = normalise(b);
  const len = Math.max(aN.length, bN.length);
  for (let i = 0; i < len; i++) {
    const diff = (aN[i] ?? 0) - (bN[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
};

// ── Update markdown ───────────────────────────────────────────────────────
export const UPDATE_MD: Record<string, string> = {
  zh: `### StarMind 如何更新

要更新 StarMind 到最新版本，请联系系统管理员进行版本更新。

管理员可通过以下方式升级：

1. **Docker 部署**：拉取最新镜像并重启容器即可。

2. **源码部署**：拉取最新代码，重新构建前端并重启服务。

升级后重启服务即可生效。`,

  ru: `### Как обновить StarMind

Для обновления StarMind обратитесь к системному администратору.

Администратор может обновить:

1. **Docker**: загрузить новый образ и перезапустить контейнер.
2. **Из исходников**: получить последние изменения, пересобрать и перезапустить.

После обновления перезапустите сервис.`,

  en: `### How to update StarMind

To update StarMind, please contact your system administrator.

Administrators can upgrade by:

1. **Docker deployment**: Pull the latest image and restart the container.
2. **Source deployment**: Pull the latest code, rebuild the frontend, and restart the service.

After upgrading, restart the service to apply changes.`,
};
