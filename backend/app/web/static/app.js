/**
 * Madrasah Web — Client-side utilities.
 *
 * - Fuse.js untuk instant search + filter (semua client-side, TIDAK pakai HTMX
 *   untuk dropdown/checkbox/search — server cuma fetch data pertama kali).
 * - Tiap HTMX swap (pagination) re-index Fuse otomatis.
 */

(function() {
    'use strict';

    // ── Fuse Search Engine (Murid) ──────────────────────────────────────

    let muridFuse = null;
    let allMuridRows = [];  // cache of {id, nis, nama, kelas_id, kelas_nama, is_active}

    /**
     * Build Fuse index dari row tabel. Dipanggil sekali + tiap HTMX swap.
     */
    function rebuildMuridFuse() {
        const rows = document.querySelectorAll('#murid-table-wrap tr[data-nisn]');
        allMuridRows = Array.from(rows).map(tr => ({
            id: tr.dataset.id,
            nisn: tr.dataset.nisn || '',
            nama: tr.dataset.nama || '',
            kelas_id: tr.dataset.kelasId || '',
            kelas_nama: tr.dataset.kelasNama || '',
            is_active: tr.dataset.isActive === '1',
        }));
        muridFuse = new Fuse(allMuridRows, {
            keys: [
                { name: 'nama',       weight: 0.6 },
                { name: 'nisn',       weight: 0.3 },
                { name: 'kelas_nama', weight: 0.1 },
            ],
            threshold: 0.35,
            ignoreLocation: true,
            minMatchCharLength: 2,
            distance: 100,
        });
        window.muridFuse = muridFuse;
        window.allMuridRows = allMuridRows;
    }

    /**
     * Build mapping kelas_id → tahun_ajaran_id dari `<script id="kelas-tahun-map">`
     * di template (dibuat dari API response di server-side). Lebih reliable
     * daripada baca dari <option> karena dropdown kelas sudah dihapus.
     */
    function buildKelasTahunMap() {
        const script = document.getElementById('kelas-tahun-map');
        if (!script) return {};
        try {
            return JSON.parse(script.textContent || '{}');
        } catch (e) {
            return {};
        }
    }

    /**
     * Apply semua filter (search + tahun ajaran + arsip) ke tabel.
     * Pure client-side via Fuse + row data attributes.
     *
     * TIDAK ADA debounce — tiap keystroke langsung apply.
     * Saat query dihapus, tabel kembali ke state filter lain (TA + arsip).
     */
    function applyAllFilters() {
        const tbody = document.querySelector('#murid-table-wrap tbody');
        if (!tbody) return;

        const searchInput = document.querySelector('input[name="q"]');
        const tahunSelect = document.querySelector('select[name="tahun_ajaran_id"]');
        const semuaCheckbox = document.querySelector('input[name="semua"]');

        const q = (searchInput?.value || '').trim();
        const tahunId = tahunSelect?.value || '';
        const showArchive = semuaCheckbox?.checked || false;

        const rows = Array.from(tbody.querySelectorAll('tr[data-nisn]'));
        const kelasTahunMap = buildKelasTahunMap();

        // Step 1: Filter by is_active (default: sembunyikan arsip)
        let visible = rows.filter(tr => {
            const isActive = tr.dataset.isActive === '1';
            return showArchive || isActive;
        });

        // Step 2: Filter by tahun ajaran (lookup kelas_id → tahun_ajaran_id)
        if (tahunId) {
            visible = visible.filter(tr => {
                const kId = tr.dataset.kelasId;
                return kelasTahunMap[kId] === tahunId;
            });
        }

        // Step 3: Filter by search via Fuse (kalau query >= 2 char)
        let matchedIds = null;
        if (q.length >= 2 && muridFuse) {
            const fuseResults = muridFuse.search(q);
            matchedIds = new Set(fuseResults.map(r => String(r.item.id)));
            visible = visible.filter(tr => matchedIds.has(tr.dataset.id));
        }

        // Apply visibility + highlight (reset plain text dulu, apply <mark> kalau match)
        const visibleIds = new Set(visible.map(tr => tr.dataset.id));
        rows.forEach(tr => {
            tr.style.display = visibleIds.has(tr.dataset.id) ? '' : 'none';
            const namaCell = tr.querySelector('td[data-cell="nama"]');
            if (!namaCell) return;
            const nama = tr.dataset.nama || '';
            namaCell.textContent = nama;  // reset plain text
            if (matchedIds && matchedIds.has(tr.dataset.id)) {
                namaCell.innerHTML = highlightMatch(nama, q);
            }
        });

        // Toggle inline empty-state saat client-side filter menghasilkan 0
        // (server-side empty state sudah ada di _table.html, tapi ini untuk client-side hide/show)
        toggleClientEmptyState(visible.length, q, tahunId, showArchive);

        // Update filter info banner
        updateFilterInfoBanner({ q, tahunId, showArchive }, visible.length);
    }

    /**
     * Show/hide inline "Tidak ada murid yang cocok" overlay saat client-side
     * filter (applyAllFilters) menghasilkan 0 hasil. Server-side empty state
     * tetap tampil saat query via URL params (lihat _table.html).
     */
    function toggleClientEmptyState(visibleCount, q, tahunId, showArchive) {
        const wrapper = document.getElementById('murid-table-wrap');
        if (!wrapper) return;
        let overlay = document.getElementById('client-empty-state');
        if (visibleCount > 0) {
            if (overlay) overlay.remove();
            return;
        }
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'client-empty-state';
            overlay.className = 'p-12 text-center text-zinc-500';
            overlay.innerHTML = `
                <i data-lucide="users" class="w-12 h-12 mx-auto mb-2 text-zinc-300"></i>
                <p class="font-medium">Tidak ada murid yang cocok</p>
                <p class="text-xs mt-1" id="client-empty-detail"></p>
            `;
            wrapper.appendChild(overlay);
            if (window.lucide && typeof window.lucide.createIcons === 'function') {
                window.lucide.createIcons();
            }
        }
        const detail = overlay.querySelector('#client-empty-detail');
        if (detail) {
            detail.innerHTML = q
                ? `Pencarian "<strong>${escapeHtml(q)}</strong>" tidak ditemukan di halaman ini.`
                : (tahunId ? 'Tidak ada murid di tahun ajaran ini.' : 'Belum ada murid.');
        }
    }

    /**
     * Highlight kata match di nama (case-insensitive).
     */
    function highlightMatch(text, query) {
        if (!text || !query) return escapeHtml(text || '');
        const escaped = escapeHtml(text);
        const safe = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return escaped.replace(new RegExp(`(${safe})`, 'gi'),
            '<mark class="bg-amber-200 rounded px-0.5">$1</mark>');
    }

    /**
     * Render filter info banner dengan chip + counter hasil.
     */
    function updateFilterInfoBanner(filters, visibleCount) {
        const info = document.getElementById('filter-info');
        const tags = document.getElementById('filter-tags');
        if (!info || !tags) return;

        const tagsArr = [];
        if (filters.q) tagsArr.push(`Cari: "${escapeHtml(filters.q)}"`);
        if (filters.tahunId) {
            const opt = document.querySelector(`select[name="tahun_ajaran_id"] option[value="${filters.tahunId}"]`);
            const label = opt ? opt.textContent.trim() : `TA ID ${filters.tahunId}`;
            tagsArr.push(`Tahun Ajaran: ${label}`);
        }
        if (filters.showArchive) tagsArr.push('Termasuk arsip');

        if (tagsArr.length > 0 || visibleCount === 0) {
            tags.innerHTML = tagsArr.map(t =>
                `<span class="inline-block bg-zinc-100 rounded px-2 py-0.5 mr-1">${t}</span>`
            ).join('') +
            `<span class="inline-block bg-teal-100 text-teal-700 rounded px-2 py-0.5 mr-1">${visibleCount} hasil</span>`;
            info.classList.remove('hidden');
        } else {
            info.classList.add('hidden');
        }
    }

    /**
     * Reset semua filter + tampilkan semua row.
     */
    function resetFilters() {
        const searchInput = document.querySelector('input[name="q"]');
        const tahunSelect = document.querySelector('select[name="tahun_ajaran_id"]');
        const semuaCheckbox = document.querySelector('input[name="semua"]');

        if (searchInput) searchInput.value = '';
        // TA: keep default (active) — clear only search + archive
        if (semuaCheckbox) semuaCheckbox.checked = false;

        applyAllFilters();
    }

    function escapeHtml(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // ── Event binding ───────────────────────────────────────────────────

    // Rebuild Fuse setiap kali tabel di-swap HTMX (pagination, dll)
    document.addEventListener('htmx:afterSwap', function(evt) {
        if (evt.target && evt.target.id === 'murid-table-wrap') {
            rebuildMuridFuse();
            applyAllFilters();
        }
    });

    // Init on first load
    document.addEventListener('DOMContentLoaded', function() {
        rebuildMuridFuse();
        applyAllFilters();
    });

    // Expose ke global — inline oninput/onchange di HTML reference these
    window.applyAllFilters = applyAllFilters;
    window.resetFilters = resetFilters;
    window.toggleSidebar = toggleSidebar;
    window.MuridSearch = {
        rebuildFuse: rebuildMuridFuse,
        applyAllFilters: applyAllFilters,
        resetFilters: resetFilters,
    };


    // ── Collapsible Sidebar (P-WEB-50) ──────────────────────────────

    function toggleSidebar() {
        const sidebar = document.getElementById('app-sidebar');
        if (!sidebar) return;
        const newState = sidebar.dataset.state === 'expanded' ? 'collapsed' : 'expanded';
        sidebar.dataset.state = newState;
        try {
            localStorage.setItem('madrasah_sidebar_state', newState);
        } catch (e) {
            // localStorage unavailable — silent
        }
        updateToggleIcon(newState);
    }

    function updateToggleIcon(state) {
        const icon = document.getElementById('sidebar-toggle-icon');
        if (!icon) return;
        // chevrons-left → chevrons-right saat collapsed
        icon.setAttribute('data-lucide', state === 'expanded' ? 'chevrons-left' : 'chevrons-right');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    // ── Mobile Sidebar Drawer (P-WEB-82) ─────────────────────────────
    // Di layar < lg: sidebar off-canvas (translate-x-full negatif).
    // openSidebarMobile/closeSidebarMobile dipanggil dari base.html (hamburger + backdrop).

    function openSidebarMobile() {
        const sidebar = document.getElementById('app-sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        if (!sidebar) return;
        sidebar.classList.remove('-translate-x-full');
        sidebar.classList.add('translate-x-0');
        if (backdrop) backdrop.classList.remove('hidden');
        document.body.style.overflow = 'hidden'; // kunci scroll background
    }

    function closeSidebarMobile() {
        const sidebar = document.getElementById('app-sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        if (!sidebar) return;
        sidebar.classList.add('-translate-x-full');
        sidebar.classList.remove('translate-x-0');
        if (backdrop) backdrop.classList.add('hidden');
        document.body.style.overflow = '';
    }

    // Tutup drawer otomatis saat klik link menu di mobile
    document.addEventListener('click', function (e) {
        const link = e.target.closest('#app-sidebar a');
        if (link && window.innerWidth < 1024) closeSidebarMobile();
    });

    // Export ke window (dipanggil dari onclick inline di base.html/topbar.html)
    window.openSidebarMobile = openSidebarMobile;
    window.closeSidebarMobile = closeSidebarMobile;

    // Restore state on page load
    document.addEventListener('DOMContentLoaded', function() {
        let saved = 'expanded';
        try {
            saved = localStorage.getItem('madrasah_sidebar_state') || 'expanded';
        } catch (e) {
            saved = 'expanded';
        }
        const sidebar = document.getElementById('app-sidebar');
        if (sidebar) {
            sidebar.dataset.state = saved;
            updateToggleIcon(saved);
        }
    });

})();