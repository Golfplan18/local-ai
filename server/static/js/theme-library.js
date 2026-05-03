// Ora Theme Library — UI mounted into the right pane while customization
// mode is active. Three sections: Installed, Browse (Obsidian community
// directory), Import (GitHub URL + local upload).
//
// Exposed at window.OraThemeLibrary with mount(container) / unmount().
// The customizer mounts this when entering customization mode and
// unmounts when exiting.

(() => {
  let container = null;
  let directoryCache = null;
  let statsCache = null;

  const escapeHtml = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  // Match the server's _v3_slugify so we can detect installed-by-name in Browse
  const slugify = (s) => {
    const slug = (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    return slug || 'theme';
  };

  const setStatus = (el, message, isError) => {
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('error', !!isError);
  };

  const mount = (el) => {
    if (container) return;
    container = el;
    container.classList.add('theme-library-mounted');

    const root = document.createElement('div');
    root.className = 'theme-library';
    root.innerHTML = `
      <div class="theme-library-tabs">
        <button data-section="installed" class="active" type="button">Installed</button>
        <button data-section="browse" type="button">Browse</button>
        <button data-section="import" type="button">Import</button>
      </div>
      <div class="theme-library-content"></div>
    `;
    container.appendChild(root);

    root.querySelectorAll('.theme-library-tabs button').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        showSection(btn.dataset.section);
      });
    });

    showSection('installed');
  };

  const unmount = () => {
    if (!container) return;
    const lib = container.querySelector('.theme-library');
    if (lib) lib.remove();
    container.classList.remove('theme-library-mounted');
    container = null;
  };

  const showSection = (section) => {
    if (!container) return;
    const root = container.querySelector('.theme-library');
    if (!root) return;
    root.querySelectorAll('.theme-library-tabs button').forEach(b => {
      b.classList.toggle('active', b.dataset.section === section);
    });
    const content = root.querySelector('.theme-library-content');
    content.innerHTML = '';

    if (section === 'installed') renderInstalled(content);
    else if (section === 'browse') renderBrowse(content);
    else if (section === 'import') renderImport(content);
  };

  const renderInstalled = async (content) => {
    content.innerHTML = '<div class="theme-library-loading">Loading installed themes…</div>';
    try {
      const result = await window.OraThemeLoader.listInstalled();
      const themes = result.themes || [];
      const active = window.OraThemeLoader.getActive();

      if (themes.length === 0) {
        content.innerHTML = '<div class="theme-library-empty">No themes installed.</div>';
        return;
      }

      const html = themes.map(theme => {
        const isActive = active === theme.id;
        const m = theme.manifest || {};
        return `
          <div class="theme-card ${isActive ? 'active' : ''}" data-theme-id="${escapeHtml(theme.id)}">
            <div class="theme-card-header">
              <div class="theme-card-name">${escapeHtml(m.name || theme.name || theme.id)}</div>
              ${isActive ? '<div class="theme-card-badge">Active</div>' : ''}
            </div>
            ${m.author ? `<div class="theme-card-meta">by ${escapeHtml(m.author)}</div>` : ''}
            ${m.version ? `<div class="theme-card-meta">v${escapeHtml(m.version)}</div>` : ''}
            <div class="theme-card-actions">
              ${!isActive ? `<button data-action="activate" type="button">Activate</button>` : '<span class="theme-card-active-note">In use</span>'}
              ${theme.bundled ? '<span class="theme-card-bundled">Bundled</span>' : `<button data-action="delete" class="theme-card-danger" type="button">Delete</button>`}
            </div>
          </div>
        `;
      }).join('');

      content.innerHTML = `<div class="theme-card-list">${html}</div>`;

      content.querySelectorAll('.theme-card').forEach(card => {
        const themeId = card.dataset.themeId;
        const activateBtn = card.querySelector('[data-action="activate"]');
        if (activateBtn) {
          activateBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await window.OraThemeLoader.applyTheme(themeId);
            renderInstalled(content);
          });
        }
        const deleteBtn = card.querySelector('[data-action="delete"]');
        if (deleteBtn) {
          deleteBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!confirm(`Delete theme "${themeId}"?`)) return;
            // If deleting the active theme, fall back to default
            if (window.OraThemeLoader.getActive() === themeId) {
              await window.OraThemeLoader.applyTheme('default');
            }
            const result = await window.OraThemeLoader.deleteTheme(themeId);
            if (result.error) {
              alert(`Delete failed: ${result.error}`);
            }
            renderInstalled(content);
          });
        }
      });
    } catch (e) {
      content.innerHTML = `<div class="theme-library-error">Error: ${escapeHtml(e.message)}</div>`;
    }
  };

  const formatDownloads = (n) => {
    if (!n) return null;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M downloads`;
    if (n >= 1_000)     return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}K downloads`;
    return `${n} downloads`;
  };

  const renderBrowse = async (content) => {
    if (!directoryCache) {
      content.innerHTML = '<div class="theme-library-loading">Fetching Obsidian community directory…</div>';
      try {
        directoryCache = await window.OraThemeLoader.fetchCommunityDirectory();
      } catch (e) {
        content.innerHTML = `<div class="theme-library-error">Error: ${escapeHtml(e.message)}</div>`;
        return;
      }
    }
    if (!statsCache) {
      // Stats are best-effort; failure falls back to directory order.
      statsCache = await window.OraThemeLoader.fetchCommunityStats();
    }

    // Snapshot installed themes for the "Installed" badge.
    let installedIds = new Set();
    try {
      const installedResult = await window.OraThemeLoader.listInstalled();
      installedIds = new Set((installedResult.themes || []).map(t => t.id));
    } catch {}
    let activeId = window.OraThemeLoader.getActive();

    const themes = Array.isArray(directoryCache) ? directoryCache : (directoryCache.themes || []);

    content.innerHTML = `
      <div class="theme-library-search">
        <input type="text" placeholder="Search by name or author…" />
      </div>
      <div class="theme-library-meta">${themes.length} themes, sorted by popularity</div>
      <div class="theme-card-list theme-card-list-browse"></div>
      <div class="theme-library-sentinel"></div>
    `;
    const list = content.querySelector('.theme-card-list-browse');
    const sentinel = content.querySelector('.theme-library-sentinel');
    const search = content.querySelector('.theme-library-search input');

    const cardHtml = (t) => {
      const id = slugify(t.name);
      const installed = installedIds.has(id);
      const active = activeId === id;
      const screenshotUrl = t.screenshot
        ? `https://raw.githubusercontent.com/${t.repo}/HEAD/${t.screenshot}`
        : null;
      const downloads = formatDownloads(statsCache?.[t.name]?.download);
      return `
        <div class="theme-card theme-card-browse ${active ? 'active' : ''}"
             data-repo="${escapeHtml(t.repo)}" data-id="${escapeHtml(id)}">
          ${screenshotUrl ? `<img class="theme-card-thumbnail" src="${escapeHtml(screenshotUrl)}" alt="" loading="lazy" onerror="this.remove()">` : ''}
          <div class="theme-card-header">
            <div class="theme-card-name">${escapeHtml(t.name)}</div>
            ${active ? '<div class="theme-card-badge">Active</div>'
              : (installed ? '<div class="theme-card-badge theme-card-badge-installed">Installed</div>' : '')}
          </div>
          <div class="theme-card-meta">by ${escapeHtml(t.author)}</div>
          ${t.modes && t.modes.length ? `<div class="theme-card-meta">Modes: ${escapeHtml(t.modes.join(', '))}</div>` : ''}
          ${downloads ? `<div class="theme-card-meta theme-card-downloads">${escapeHtml(downloads)}</div>` : ''}
          <div class="theme-card-actions">
            ${active ? '<span class="theme-card-active-note">In use</span>'
              : installed ? `<button data-action="activate" type="button">Activate</button>`
              :             `<button data-action="install" type="button">Install</button>`}
          </div>
          <div class="theme-install-status"></div>
        </div>
      `;
    };

    // Filter + sort state
    let filtered = [];
    let renderedCount = 0;
    const BATCH = 40;
    let observer = null;

    const computeFiltered = (filter) => {
      const lower = (filter || '').toLowerCase();
      const matches = themes.filter(t =>
        (t.name || '').toLowerCase().includes(lower) ||
        (t.author || '').toLowerCase().includes(lower));
      // Sort by download count descending; missing stats sort last.
      matches.sort((a, b) =>
        (statsCache?.[b.name]?.download || 0) - (statsCache?.[a.name]?.download || 0));
      return matches;
    };

    const renderBatch = () => {
      const slice = filtered.slice(renderedCount, renderedCount + BATCH);
      if (slice.length === 0) return;
      const html = slice.map(cardHtml).join('');
      list.insertAdjacentHTML('beforeend', html);
      renderedCount += slice.length;

      if (renderedCount >= filtered.length) {
        if (observer) observer.disconnect();
        sentinel.textContent = filtered.length === 0
          ? 'No matches.'
          : `Showing all ${filtered.length}.`;
      } else {
        sentinel.textContent = `Loading more (${renderedCount} of ${filtered.length})…`;
      }
    };

    const resetAndRender = () => {
      if (observer) observer.disconnect();
      filtered = computeFiltered(search.value);
      renderedCount = 0;
      list.innerHTML = '';
      sentinel.textContent = '';
      renderBatch();

      if (renderedCount < filtered.length) {
        observer = new IntersectionObserver((entries) => {
          entries.forEach(e => { if (e.isIntersecting) renderBatch(); });
        }, { root: content, rootMargin: '300px' });
        observer.observe(sentinel);
      }
    };

    // Event delegation — one click handler covers all current and future cards.
    list.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const card = btn.closest('.theme-card-browse');
      if (!card) return;
      e.stopPropagation();

      const status = card.querySelector('.theme-install-status');
      const action = btn.dataset.action;

      if (action === 'install') {
        const repo = card.dataset.repo;
        const directoryEntry = themes.find(t => t.repo === repo) || {};
        const fallback = {
          name: directoryEntry.name,
          author: directoryEntry.author,
          modes: directoryEntry.modes,
        };
        btn.disabled = true;
        btn.textContent = 'Installing…';
        setStatus(status, '', false);
        try {
          const result = await window.OraThemeLoader.installFromGitHub(repo, fallback);
          if (result.error) throw new Error(result.error);
          btn.textContent = 'Installed ✓';
          installedIds.add(result.id);
          setTimeout(resetAndRender, 600);
        } catch (err) {
          btn.disabled = false;
          btn.textContent = 'Install';
          setStatus(status, err.message, true);
        }
      } else if (action === 'activate') {
        const id = card.dataset.id;
        btn.disabled = true;
        btn.textContent = 'Activating…';
        setStatus(status, '', false);
        try {
          const result = await window.OraThemeLoader.applyTheme(id);
          if (result && result.error) throw new Error(result.error);
          activeId = id;
          resetAndRender();
        } catch (err) {
          btn.disabled = false;
          btn.textContent = 'Activate';
          setStatus(status, err.message, true);
        }
      }
    });

    let debounce;
    search.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(resetAndRender, 100);
    });

    resetAndRender();
  };

  const renderImport = (content) => {
    content.innerHTML = `
      <div class="theme-library-import">
        <h3>Install from GitHub</h3>
        <p>Paste a GitHub repo (e.g. <code>github.com/dracula/obsidian</code>). Ora fetches manifest.json and theme.css from the repo.</p>
        <div class="theme-library-import-row">
          <input type="text" data-field="github-repo" placeholder="github.com/user/repo" />
          <button type="button" data-action="install-github">Install</button>
        </div>
        <div class="theme-install-status" data-status="github"></div>

        <h3>Upload .css file</h3>
        <p>Pick a theme.css file or drag one into the area below. Optionally set a custom name.</p>
        <div class="theme-library-import-row">
          <input type="text" data-field="upload-name" placeholder="Theme name (optional)" />
          <input type="file" data-field="upload-file" accept=".css,text/css" />
        </div>
        <div class="theme-library-dropzone">
          <div class="theme-library-dropzone-text">Drop a .css file here</div>
        </div>
        <button type="button" data-action="install-upload">Install from file</button>
        <div class="theme-install-status" data-status="upload"></div>
      </div>
    `;

    const ghInput = content.querySelector('[data-field="github-repo"]');
    const ghBtn = content.querySelector('[data-action="install-github"]');
    const ghStatus = content.querySelector('[data-status="github"]');

    ghBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const repo = ghInput.value.trim();
      if (!repo) return;
      ghBtn.disabled = true;
      ghBtn.textContent = 'Installing…';
      setStatus(ghStatus, '', false);
      try {
        const result = await window.OraThemeLoader.installFromGitHub(repo);
        if (result.error) throw new Error(result.error);
        ghBtn.textContent = 'Installed ✓';
        setStatus(ghStatus, `Installed "${result.name}" as id "${result.id}".`, false);
        ghInput.value = '';
        setTimeout(() => { ghBtn.disabled = false; ghBtn.textContent = 'Install'; }, 1500);
      } catch (err) {
        ghBtn.disabled = false;
        ghBtn.textContent = 'Install';
        setStatus(ghStatus, err.message, true);
      }
    });

    const nameInput = content.querySelector('[data-field="upload-name"]');
    const fileInput = content.querySelector('[data-field="upload-file"]');
    const upBtn = content.querySelector('[data-action="install-upload"]');
    const upStatus = content.querySelector('[data-status="upload"]');
    const dropzone = content.querySelector('.theme-library-dropzone');

    const installFromFile = async (file) => {
      const name = nameInput.value.trim() || file.name.replace(/\.css$/i, '');
      upBtn.disabled = true;
      upBtn.textContent = 'Installing…';
      setStatus(upStatus, '', false);
      try {
        const css = await file.text();
        const result = await window.OraThemeLoader.installFromCSS(name, css);
        if (result.error) throw new Error(result.error);
        upBtn.textContent = 'Installed ✓';
        setStatus(upStatus, `Installed "${result.name}" as id "${result.id}".`, false);
        nameInput.value = '';
        fileInput.value = '';
        setTimeout(() => { upBtn.disabled = false; upBtn.textContent = 'Install from file'; }, 1500);
      } catch (err) {
        upBtn.disabled = false;
        upBtn.textContent = 'Install from file';
        setStatus(upStatus, err.message, true);
      }
    };

    // Drag-drop a .css file onto the dropzone
    ['dragenter', 'dragover'].forEach(evt =>
      dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add('dragover'); }));
    ['dragleave', 'dragend'].forEach(evt =>
      dropzone.addEventListener(evt, () => dropzone.classList.remove('dragover')));
    dropzone.addEventListener('drop', async (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      const files = [...e.dataTransfer.files].filter(f =>
        f.name.toLowerCase().endsWith('.css') || f.type === 'text/css');
      if (files.length === 0) {
        setStatus(upStatus, 'Drop only .css files.', true);
        return;
      }
      await installFromFile(files[0]);
    });

    upBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const file = fileInput.files[0];
      if (!file) {
        setStatus(upStatus, 'Pick a .css file or drop one above.', true);
        return;
      }
      await installFromFile(file);
    });
  };

  window.OraThemeLibrary = { mount, unmount };
})();
