import { Layout, Space, Dropdown } from "antd";
import type { MenuProps } from "antd";
import LanguageSwitcher from "../components/LanguageSwitcher/index";
import ThemeToggleButton from "../components/ThemeToggleButton";
import CodingModeToggle from "../components/CodingModeToggle";
import { useTranslation } from "react-i18next";
import { Button, Modal } from "@agentscope-ai/design";
import styles from "./index.module.less";
import api from "../api";
import {
  getDocsUrl,
  getFaqUrl,
  UPDATE_MD,
} from "./constants";
import { useTheme } from "../contexts/ThemeContext";
import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  CopyOutlined,
  CheckOutlined,
  TagOutlined,
  ReadOutlined,
  QuestionCircleOutlined,
  DownOutlined,
} from "@ant-design/icons";

const { Header: AntHeader } = Layout;

// ── Code block with copy button ───────────────────────────────────────────
function UpdateCodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className={styles.codeBlock}>
      <code className={styles.codeBlockInner}>{code}</code>
      <button
        className={`${styles.copyBtn} ${
          copied ? styles.copyBtnCopied : styles.copyBtnDefault
        }`}
        onClick={handleCopy}
        title="Copy"
      >
        {copied ? <CheckOutlined /> : <CopyOutlined />}
      </button>
    </div>
  );
}

export default function Header() {
  const { t, i18n } = useTranslation();
  const { isDark } = useTheme();
  const [version, setVersion] = useState<string>("");
  const [updateModalOpen, setUpdateModalOpen] = useState(false);
  const [updateMarkdown, setUpdateMarkdown] = useState<string>("");

  useEffect(() => {
    api
      .getVersion()
      .then((res) => setVersion(res?.version ?? ""))
      .catch(() => {});
  }, []);

  // ── Update notification (no PyPI check — self-hosted, no auto-update) ────

  const handleOpenUpdateModal = () => {
    const lang = i18n.language?.startsWith("zh")
      ? "zh"
      : i18n.language?.startsWith("ru")
      ? "ru"
      : "en";
    setUpdateMarkdown(UPDATE_MD[lang] ?? UPDATE_MD.en);
    setUpdateModalOpen(true);
  };

  const handleNavClick = (url: string) => {
    if (url) {
      const pywebview = (window as any).pywebview;
      if (pywebview?.api) {
        pywebview.api.open_external_link(url);
      } else {
        window.open(url, "_blank");
      }
    }
  };

  return (
    <>
      <AntHeader className={styles.header}>
        <div className={styles.logoWrapper}>
          <img
            src={isDark ? "/logo-dark.svg" : "/logo-light.svg"}
            alt="StarMind"
            className={styles.logoImg}
          />
          <div className={styles.logoDivider} />
          {version && (
            <span
              className={`${styles.versionBadge} ${styles.versionBadgeClickable}`}
              onClick={handleOpenUpdateModal}
            >
              v{version}
            </span>
          )}
        </div>
        <Space size="middle">
          <Dropdown
            menu={{
              items: [
                {
                  key: "tutorial",
                  icon: <ReadOutlined />,
                  label: t("header.tutorial"),
                  onClick: () => handleNavClick(getDocsUrl(i18n.language)),
                },
                {
                  key: "faq",
                  icon: <QuestionCircleOutlined />,
                  label: t("header.faq"),
                  onClick: () => handleNavClick(getFaqUrl(i18n.language)),
                },
              ] as MenuProps["items"],
            }}
          >
            <Button type="text">
              {t("header.resources")} <DownOutlined />
            </Button>
          </Dropdown>
          <div className={styles.headerDivider} />
          <CodingModeToggle />
          <div className={styles.headerDivider} />
          <LanguageSwitcher />
          <ThemeToggleButton />
        </Space>
      </AntHeader>

      <Modal
        title={null}
        open={updateModalOpen}
        onCancel={() => setUpdateModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setUpdateModalOpen(false)}>
            {t("common.close")}
          </Button>,
        ]}
        width={960}
        className={styles.updateModal}
      >
        {/* Banner area */}
        <div className={styles.updateModalBanner}>
          <div className={styles.updateModalBannerLeft}>
            <span className={styles.updateModalVersionTag}>
              <TagOutlined />
              Version {version}
            </span>
            <div className={styles.updateModalBannerTitle}>
              StarMind
            </div>
          </div>
        </div>

        {/* Markdown content */}
        <div className={styles.updateModalBody}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, className, children, ...props }: any) {
                const match = /language-(\w+)/.exec(className || "");
                const isBlock =
                  node?.position?.start?.line !== node?.position?.end?.line ||
                  match;
                return isBlock ? (
                  <UpdateCodeBlock
                    code={String(children).replace(/\n$/, "")}
                  />
                ) : (
                  <code className={styles.codeInline} {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {updateMarkdown}
          </ReactMarkdown>
        </div>
      </Modal>
    </>
  );
}