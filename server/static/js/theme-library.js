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

  const escapeHtml = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

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

    const themes = Array.isArray(directoryCache) ? directoryCache : (directoryCache.themes || []);

    content.innerHTML = `
      <div class="theme-library-search">
        <input type="text" placeholder="Search ${themes.length} themes…" />
      </div>
      <div class="theme-card-list theme-card-list-browse"></div>
    `;
    const list = content.querySelector('.theme-card-list-browse');
    const search = content.querySelector('.theme-library-search input');

    const render = (filter = '') => {
      const lower = filter.toLowerCase();
      const filtered = themes.filter(t =>
        (t.name || '').toLowerCase().includes(lower) ||
        (t.author || '').toLowerCase().includes(lower)
      );
      list.innerHTML = filtered.slice(0, 40).map(t => `
        <div class="theme-card theme-card-browse" data-repo="${escapeHtml(t.repo)}">
          <div class="theme-card-header">
            <div class="theme-card-name">${escapeHtml(t.name)}</div>
          </div>
          <div class="theme-card-meta">by ${escapeHtml(t.author)}</div>
          ${t.modes && t.modes.length ? `<div class="theme-card-meta">Modes: ${escapeHtml(t.modes.join(', '))}</div>` : ''}
          <div class="theme-card-actions">
            <button data-action="install" type="button">Install</button>
          </div>
        </div>
      `).join('');
      if (filtered.length > 40) {
        list.insertAdjacentHTML('beforeend',
          `<div class="theme-library-empty">Showing 40 of ${filtered.length}. Refine your search to narrow.</div>`);
      }

      list.querySelectorAll('.theme-card-browse').forEach(card => {
        const installBtn = card.querySelector('[data-action="install"]');
        if (installBtn) {
          installBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const repo = card.dataset.repo;
            installBtn.disabled = true;
            installBtn.textContent = 'Installing…';
            try {
              const result = await window.OraThemeLoader.installFromGitHub(repo);
              if (result.error) throw new Error(result.error);
              installBtn.textContent = 'Installed ✓';
              setTimeout(() => { installBtn.disabled = false; installBtn.textContent = 'Install'; }, 2000);
            } catch (err) {
              installBtn.textContent = 'Failed';
              alert(`Install failed: ${err.message}`);
              setTimeout(() => { installBtn.disabled = false; installBtn.textContent = 'Install'; }, 2000);
            }
          });
        }
      });
    };

    render();
    let debounce;
    search.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => render(search.value), 100);
    });
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

        <h3>Upload .css file</h3>
        <p>Pick a theme.css file. Optionally set a custom name; otherwise the file name is used.</p>
        <div class="theme-library-import-row">
          <input type="text" data-field="upload-name" placeholder="Theme name (optional)" />
          <input type="file" data-field="upload-file" accept=".css,text/css" />
        </div>
        <button type="button" data-action="install-upload">Install from file</button>
      </div>
    `;

    const ghInput = content.querySelector('[data-field="github-repo"]');
    const ghBtn = content.querySelector('[data-action="install-github"]');
    ghBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const repo = ghInput.value.trim();
      if (!repo) return;
      ghBtn.disabled = true;
      ghBtn.textContent = 'Installing…';
      try {
        const result = await window.OraThemeLoader.installFromGitHub(repo);
        if (result.error) throw new Error(result.error);
        ghBtn.textContent = 'Installed ✓';
        ghInput.value = '';
        setTimeout(() => { ghBtn.disabled = false; ghBtn.textContent = 'Install'; }, 2000);
      } catch (err) {
        ghBtn.textContent = 'Failed';
        alert(`Install failed: ${err.message}`);
        setTimeout(() => { ghBtn.disabled = false; ghBtn.textContent = 'Install'; }, 2000);
      }
    });

    const nameInput = content.querySelector('[data-field="upload-name"]');
    const fileInput = content.querySelector('[data-field="upload-file"]');
    const upBtn = content.querySelector('[data-action="install-upload"]');
    upBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const file = fileInput.files[0];
      if (!file) { alert('Pick a CSS file first.'); return; }
      const name = nameInput.value.trim() || file.name.replace(/\.css$/i, '');
      upBtn.disabled = true;
      upBtn.textContent = 'Installing…';
      try {
        const css = await file.text();
        const result = await window.OraThemeLoader.installFromCSS(name, css);
        if (result.error) throw new Error(result.error);
        upBtn.textContent = 'Installed ✓';
        nameInput.value = '';
        fileInput.value = '';
        setTimeout(() => { upBtn.disabled = false; upBtn.textContent = 'Install from file'; }, 2000);
      } catch (err) {
        upBtn.textContent = 'Failed';
        alert(`Install failed: ${err.message}`);
        setTimeout(() => { upBtn.disabled = false; upBtn.textContent = 'Install from file'; }, 2000);
      }
    });
  };

  window.OraThemeLibrary = { mount, unmount };
})();
