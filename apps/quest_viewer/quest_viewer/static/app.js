(() => {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const mainCategory = document.getElementById("main-category");
  const subCategory = document.getElementById("sub-category");
  const aboutDialog = document.getElementById("about-dialog");
  const todayVisitors = document.getElementById("today-visitors");

  const recordAnonymousVisit = async () => {
    if (!todayVisitors) return;
    try {
      const storageKey = "xunxian-anonymous-visitor";
      let visitorId = localStorage.getItem(storageKey);
      if (!visitorId) {
        visitorId =
          globalThis.crypto?.randomUUID?.() ||
          `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
        localStorage.setItem(storageKey, visitorId);
      }
      const response = await fetch("/api/visit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ visitor_id: visitorId }),
        keepalive: true,
      });
      if (!response.ok) return;
      const data = await response.json();
      if (Number.isInteger(data.count)) todayVisitors.textContent = String(data.count);
    } catch {
      // Storage-disabled browsers remain uncounted instead of inflating the total.
    }
  };

  recordAnonymousVisit();

  const themeButtons = [...document.querySelectorAll(".theme-swatch")];
  const currentTheme = () => {
    const root = document.documentElement;
    if (root.dataset.mode === "dark") return "dark";
    return root.dataset.theme === "orange" ? "orange" : "green";
  };
  const syncThemeButtons = () => {
    const value = currentTheme();
    themeButtons.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.themeValue === value));
    });
  };
  themeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const root = document.documentElement;
      const theme = button.dataset.themeValue;
      if (theme === "green") delete root.dataset.theme;
      else root.dataset.theme = "orange";
      if (theme === "dark") root.dataset.mode = "dark";
      else delete root.dataset.mode;
      try {
        localStorage.setItem("xunxian-color-theme", theme);
      } catch {
        // Theme still applies for this page view without storage.
      }
      syncThemeButtons();
    });
  });
  syncThemeButtons();

  document.querySelector("[data-open-about]")?.addEventListener("click", () => {
    aboutDialog?.showModal();
  });
  document.querySelector("[data-close-about]")?.addEventListener("click", () => {
    aboutDialog?.close();
  });
  aboutDialog?.addEventListener("click", (event) => {
    if (event.target === aboutDialog) aboutDialog.close();
  });

  const updateSubcategoryOptions = () => {
    if (!mainCategory || !subCategory) return;
    const selectedMain = mainCategory.value;
    let visibleCount = 0;
    [...subCategory.options].forEach((option) => {
      if (!option.dataset.parent) return;
      const isVisible = option.dataset.parent === selectedMain;
      option.hidden = !isVisible;
      option.disabled = !isVisible;
      if (isVisible) visibleCount += 1;
    });
    const selectedOption = subCategory.selectedOptions[0];
    if (selectedOption?.dataset.parent !== selectedMain) {
      subCategory.value = "";
    }
    subCategory.disabled = !selectedMain || visibleCount === 0;
  };

  mainCategory?.addEventListener("change", updateSubcategoryOptions);

  // Copy the active text tab as plain text; entity tags contribute only their label.
  const copyTextButton = document.querySelector("[data-copy-text]");
  const copyStatus = copyTextButton?.querySelector(".copy-text-status");
  let copyResetTimer = null;
  const panelPlainText = (panel) => {
    const prose = panel?.querySelector(".quest-prose");
    if (!prose) return "";
    return [...prose.childNodes]
      .map((node) => {
        if (node.nodeType === Node.TEXT_NODE) return node.textContent;
        if (node.classList?.contains("entity-tag")) {
          return [...node.childNodes]
            .filter((child) => child.nodeType === Node.TEXT_NODE)
            .map((child) => child.textContent)
            .join("");
        }
        return node.textContent;
      })
      .join("")
      .trim();
  };
  const writeClipboard = async (text) => {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch {
        // Fall through to the selection-based copy below.
      }
    }
    const scratch = document.createElement("textarea");
    scratch.value = text;
    scratch.setAttribute("readonly", "");
    scratch.style.position = "fixed";
    scratch.style.opacity = "0";
    document.body.append(scratch);
    scratch.select();
    const copied = document.execCommand("copy");
    scratch.remove();
    if (!copied) throw new Error("copy failed");
  };
  copyTextButton?.addEventListener("click", async () => {
    const panel = document.querySelector(".text-panel:not([hidden])");
    const text = panelPlainText(panel);
    if (!text) return;
    let message = "已复制";
    try {
      await writeClipboard(text);
      copyTextButton.classList.add("is-copied");
    } catch {
      message = "复制失败";
    }
    if (copyStatus) copyStatus.textContent = message;
    clearTimeout(copyResetTimer);
    copyResetTimer = setTimeout(() => {
      copyTextButton.classList.remove("is-copied");
      if (copyStatus) copyStatus.textContent = "";
    }, 1600);
  });

  const filterCount = document.getElementById("filter-count");
  const filterFields = [...document.querySelectorAll(".filter-grid input, .filter-grid select")];
  const updateFilterCount = () => {
    if (!filterCount) return;
    const count = filterFields.filter((field) => !field.disabled && field.value).length;
    filterCount.textContent = String(count);
    filterCount.hidden = count === 0;
  };
  filterFields.forEach((field) => {
    field.addEventListener("input", updateFilterCount);
    field.addEventListener("change", updateFilterCount);
  });
  updateSubcategoryOptions();

  const activateTab = (tab) => {
    tabs.forEach((candidate) => {
      const selected = candidate === tab;
      candidate.setAttribute("aria-selected", String(selected));
      candidate.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(`panel-${candidate.dataset.tab}`);
      if (panel) panel.hidden = !selected;
    });
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let nextIndex = index;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      activateTab(tabs[nextIndex]);
      tabs[nextIndex].focus();
    });
  });

  const evidenceCard = document.getElementById("evidence-card");
  const evidenceList = document.getElementById("evidence-list");
  const evidenceEmpty = document.getElementById("evidence-empty");
  const relatedQuests = document.getElementById("related-quests");
  const relatedCount = document.getElementById("related-count");
  let preservedQuery = relatedQuests?.dataset.preservedQuery || "";
  const relatedPageSize = 5;
  const relatedState = { quests: [], page: 1 };
  const overflowTitleSelector = [
    ".quest-card > strong",
    ".quest-facts dd",
    ".reward-card > span",
    ".reward-card > strong",
    ".relation-node strong",
    ".related-quest strong",
    ".related-quest small",
  ].join(",");

  const applyOverflowTitles = (root = document) => {
    root.querySelectorAll(overflowTitleSelector).forEach((element) => {
      const isClipped =
        element.scrollWidth > element.clientWidth ||
        element.scrollHeight > element.clientHeight;
      if (isClipped) {
        element.title = element.textContent.trim();
      } else {
        element.removeAttribute("title");
      }
    });
  };

  const searchResultList = document.getElementById("search-result-list");
  const searchResultSummary = document.getElementById("search-result-summary");
  const searchPagination = document.getElementById("search-pagination");
  const searchPageCache = new Map();
  let searchRequestController = null;

  const currentSearchParams = () => {
    const params = new URLSearchParams(window.location.search);
    return new URLSearchParams(
      ["q", "npc", "area", "category", "subcategory", "page"]
        .filter((key) => params.get(key))
        .map((key) => [key, params.get(key)])
    );
  };

  const searchApiUrl = (params) => {
    const apiParams = new URLSearchParams(params);
    apiParams.delete("selected");
    return `/api/quests?${apiParams.toString()}`;
  };

  const searchCacheKey = (params) => {
    const cacheParams = new URLSearchParams(params);
    cacheParams.delete("selected");
    cacheParams.delete("window");
    return `/api/quests?${cacheParams.toString()}`;
  };

  const fetchSearchPage = (params, signal) => {
    const cacheKey = searchCacheKey(params);
    const url = searchApiUrl(params);
    if (!searchPageCache.has(cacheKey)) {
      const request = fetch(url, {
        headers: { Accept: "application/json" },
        signal,
      })
        .then((response) => {
          if (!response.ok) throw new Error(`检索请求失败：${response.status}`);
          return response.json();
        })
        .catch((error) => {
          searchPageCache.delete(cacheKey);
          throw error;
        });
      searchPageCache.set(cacheKey, request);
    }
    return searchPageCache.get(cacheKey);
  };

  const questLink = (questId, params) => {
    const linkParams = new URLSearchParams(params);
    linkParams.set("selected", String(questId));
    const ordered = new URLSearchParams([["selected", String(questId)]]);
    ["q", "npc", "area", "category", "subcategory", "page"].forEach((key) => {
      if (linkParams.get(key)) ordered.set(key, linkParams.get(key));
    });
    return `/?${ordered.toString()}`;
  };

  const searchPageLink = (params) => {
    const ordered = new URLSearchParams();
    ["q", "npc", "area", "category", "subcategory", "page"].forEach((key) => {
      if (params.get(key)) ordered.set(key, params.get(key));
    });
    const query = ordered.toString();
    return query ? `/?${query}` : "/";
  };

  const syncPreservedTaskLinks = (params) => {
    preservedQuery = params.toString();
    if (relatedQuests) relatedQuests.dataset.preservedQuery = preservedQuery;
    document
      .querySelectorAll(
        "#quest-dossier a[href^='/?selected='], #context-rail a[href^='/?selected=']"
      )
      .forEach((link) => {
        const selected = new URL(link.href).searchParams.get("selected");
        if (selected) link.href = questLink(selected, params);
      });
  };

  const compactNumber = (value) => {
    const number = Number(value) || 0;
    const absolute = Math.abs(number);
    const sign = number < 0 ? "-" : "";
    if (absolute >= 1000000000000) {
      const roundedTenths = Math.floor(
        (absolute + 50000000000) / 100000000000
      );
      const whole = Math.floor(roundedTenths / 10);
      const decimal = roundedTenths % 10;
      return `${sign}${decimal ? `${whole}.${decimal}` : whole}万亿`;
    }
    if (absolute >= 100000000) {
      return `${sign}${Math.floor((absolute + 50000000) / 100000000)}亿`;
    }
    if (absolute >= 10000) {
      return `${sign}${Math.floor((absolute + 5000) / 10000)}万`;
    }
    return String(number);
  };

  const renderSearchPage = (data, params) => {
    if (!searchResultList || !searchResultSummary || !searchPagination) return;
    const selected = new URLSearchParams(window.location.search).get("selected");
    const experienceSummary = data.search_active
      ? ` · 总经验 ${compactNumber(data.total_experience)}`
      : "";
    searchResultSummary.textContent =
      `${data.total} 条${experienceSummary}`;
    searchResultList.innerHTML = data.items.length
      ? data.items
          .map(
            (quest) => `<a
              class="quest-card ${String(quest.quest_id) === selected ? "is-active" : ""}"
              href="${questLink(quest.quest_id, params)}"
              data-recent-quest="${escapeHtml(String(quest.quest_id))}"
            >
              <strong>${escapeHtml(String(quest.quest_name))}</strong>
            </a>`
          )
          .join("")
      : `<div class="empty-state">
          <span aria-hidden="true">⌁</span>
          <strong>没有找到任务</strong>
          <p>换一个任务名称、NPC、地区或任务类型试试。</p>
        </div>`;
    const pageParams = new URLSearchParams(params);
    pageParams.set("page", String(Math.max(1, data.page - 1)));
    const previousUrl = searchPageLink(pageParams);
    pageParams.set("page", String(Math.min(data.page_count, data.page + 1)));
    const nextUrl = searchPageLink(pageParams);
    searchPagination.innerHTML = `
      <a href="${previousUrl}" aria-disabled="${data.page <= 1}">上一页</a>
      <span>${data.page} / ${data.page_count}</span>
      <a href="${nextUrl}" aria-disabled="${data.page >= data.page_count}">下一页</a>`;
    searchResultList.setAttribute("aria-busy", "false");
    searchResultList.classList.remove("is-loading");
    syncPreservedTaskLinks(params);
    applyOverflowTitles(searchResultList);
  };

  const loadSearchPage = async (url, { updateHistory = true } = {}) => {
    if (!searchResultList) return;
    const target = new URL(url, window.location.href);
    const params = new URLSearchParams(target.search);
    params.delete("selected");
    if (!params.get("page")) params.set("page", "1");
    searchRequestController?.abort();
    searchRequestController = new AbortController();
    searchResultList.setAttribute("aria-busy", "true");
    searchResultList.classList.add("is-loading");
    try {
      const data = await fetchSearchPage(params, searchRequestController.signal);
      if (updateHistory) {
        history.pushState({}, "", searchPageLink(params));
      }
      renderSearchPage(data, params);
    } catch (error) {
      if (error.name === "AbortError") return;
      searchResultList.setAttribute("aria-busy", "false");
      searchResultList.classList.remove("is-loading");
      window.location.assign(target.href);
    }
  };

  searchPagination?.addEventListener("click", (event) => {
    const link = event.target.closest("a");
    if (!link || link.getAttribute("aria-disabled") === "true") return;
    event.preventDefault();
    loadSearchPage(link.href);
  });

  window.addEventListener("popstate", () => {
    loadSearchPage(window.location.href, { updateHistory: false });
  });

  const evidenceLabels = {
    label: "对象名称",
    namespace: "对象类型",
    amount: "任务数量",
    area_name: "所属地区",
    speaker_profile_name: "说话者类型",
    call_variants: "候选称呼",
    selection_rule: "选择规则",
  };

  // Long values such as candidate forms of address fold to two lines until expanded.
  const evidenceFoldLength = 36;
  evidenceList?.addEventListener("click", (event) => {
    const toggle = event.target.closest(".evidence-toggle");
    if (!toggle) return;
    const value = toggle.closest("dd");
    const folded = value.classList.toggle("is-folded");
    toggle.setAttribute("aria-expanded", String(!folded));
    toggle.textContent = folded ? "展开" : "收起";
  });

  const renderRelatedPage = () => {
    const quests = relatedState.quests;
    const pageCount = Math.ceil(quests.length / relatedPageSize);
    relatedState.page = Math.min(Math.max(1, relatedState.page), pageCount);
    const start = (relatedState.page - 1) * relatedPageSize;
    const pageItems = quests.slice(start, start + relatedPageSize);
    const questMarkup = pageItems
      .map((quest) => {
        const meta = [
          quest.level_requirement == null ? null : `等级 ${quest.level_requirement}`,
          quest.category_name,
          quest.area_name,
        ]
          .filter(Boolean)
          .join(" · ");
        const preservedSuffix = preservedQuery ? `&${preservedQuery}` : "";
        return `<a class="related-quest" href="/?selected=${encodeURIComponent(quest.quest_id)}${preservedSuffix}">
          <strong>${escapeHtml(String(quest.quest_name))}</strong>
          <small>${escapeHtml(meta || "任务信息")}</small>
        </a>`;
      })
      .join("");
    const paginationMarkup =
      pageCount > 1
        ? `<nav class="related-pagination" aria-label="相关任务分页">
            <button type="button" data-related-page="prev" ${relatedState.page === 1 ? "disabled" : ""}>上一页</button>
            <span>${relatedState.page} / ${pageCount}</span>
            <button type="button" data-related-page="next" ${relatedState.page === pageCount ? "disabled" : ""}>下一页</button>
          </nav>`
        : "";
    relatedQuests.innerHTML = questMarkup + paginationMarkup;
    applyOverflowTitles(relatedQuests);
  };

  const renderRelatedQuests = (data) => {
    if (!relatedQuests || !relatedCount) return;
    const quests = Array.isArray(data.related_quests) ? data.related_quests : [];
    const isRole = ["npc", "enemy", "target", "friend"].includes(data.kind);
    relatedState.quests = quests;
    relatedState.page = 1;
    if (!isRole) {
      relatedCount.textContent = "无角色关联";
      relatedQuests.innerHTML =
        '<div class="related-empty">这个标签不是任务角色，没有可关联的其他任务。</div>';
      return;
    }
    relatedCount.textContent = quests.length ? `${quests.length} 项` : "暂无其他任务";
    if (!quests.length) {
      relatedQuests.innerHTML =
        '<div class="related-empty">当前角色暂未出现在其他任务中。</div>';
      return;
    }
    renderRelatedPage();
  };

  const renderEvidence = (data, updateRelated = true) => {
    if (!evidenceList || !data) return;
    const fields = Object.keys(evidenceLabels).filter(
      (key) => data[key] !== undefined && data[key] !== null && data[key] !== ""
    );
    evidenceList.innerHTML = fields
      .map((key) => {
        const value = escapeHtml(String(data[key]));
        if (String(data[key]).length <= evidenceFoldLength) {
          return `<div><dt>${evidenceLabels[key]}</dt><dd>${value}</dd></div>`;
        }
        return `<div><dt>${evidenceLabels[key]}</dt><dd class="is-folded"><span class="evidence-value">${value}</span><button type="button" class="evidence-toggle" aria-expanded="false">展开</button></dd></div>`;
      })
      .join("");
    evidenceList.hidden = false;
    if (evidenceEmpty) evidenceEmpty.hidden = true;
    if (updateRelated) renderRelatedQuests(data);
  };

  const escapeHtml = (value) =>
    value.replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#039;",
        })[character]
    );

  if (evidenceCard?.dataset.defaultEvidence) {
    const defaultEvidence = JSON.parse(evidenceCard.dataset.defaultEvidence);
    // Role defaults (accept/submit NPC) also fill the related-quest list, like a click would.
    renderEvidence(defaultEvidence, Array.isArray(defaultEvidence.related_quests));
  }
  applyOverflowTitles();
  syncPreservedTaskLinks(currentSearchParams());
  window.addEventListener("resize", () => applyOverflowTitles());

  document.querySelectorAll(".entity-tag, .role-trigger").forEach((tag) => {
    tag.addEventListener("click", () => {
      renderEvidence(JSON.parse(tag.dataset.evidence));
      document.getElementById("context-rail")?.classList.add("is-open");
      document.querySelector("[data-sheet-backdrop]")?.classList.add("is-visible");
      tag.setAttribute("aria-pressed", "true");
    });
  });
  relatedQuests?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-related-page]");
    if (!button) return;
    relatedState.page += button.dataset.relatedPage === "next" ? 1 : -1;
    renderRelatedPage();
  });

  const backdrop = document.querySelector("[data-sheet-backdrop]");
  const closeSheets = () => {
    document.querySelectorAll(".search-rail, .context-rail").forEach((rail) => {
      rail.classList.remove("is-open");
    });
    backdrop?.classList.remove("is-visible");
  };

  document.querySelectorAll("[data-open-sheet]").forEach((button) => {
    button.addEventListener("click", () => {
      closeSheets();
      const target = document.getElementById(button.dataset.openSheet);
      target?.classList.add("is-open");
      backdrop?.classList.add("is-visible");
    });
  });

  document.querySelectorAll("[data-close-sheet]").forEach((button) => {
    button.addEventListener("click", closeSheets);
  });
  backdrop?.addEventListener("click", closeSheets);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSheets();
  });

  const activeQuest = document.querySelector(".quest-card.is-active");
  if (activeQuest?.dataset.recentQuest) {
    const currentId = activeQuest.dataset.recentQuest;
    const existing = JSON.parse(localStorage.getItem("quest-viewer-recent") || "[]");
    localStorage.setItem(
      "quest-viewer-recent",
      JSON.stringify([currentId, ...existing.filter((id) => id !== currentId)].slice(0, 8))
    );
  }
})();
