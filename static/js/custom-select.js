/**
 * HRMS Universal Custom Dropdown & Select System
 * Clean, modern card-based dropdown with raw text (no boxed badge text).
 * Search bar is only displayed if options exceed 7 items.
 * Responsive width ensuring all text is visible clearly.
 */

(function () {
    'use strict';

    // Global registry to track initialized selects
    const initializedSelects = new WeakSet();

    /**
     * Initializes a single <select> into the sleek card-based dropdown
     */
    function enhanceSelect(select) {
        if (!select || initializedSelects.has(select)) return;
        if (select.classList.contains('raw-select') || select.dataset.noEnhance === 'true') return;

        initializedSelects.add(select);

        // Check if wrapper already exists
        if (select.closest('.custom-select-wrapper')) return;

        // Search field only needed if options are strictly MORE THAN 7
        const isSearchable = select.dataset.searchable === 'true' || (select.options.length > 7 && select.dataset.searchable !== 'false');
        const placeholder = select.dataset.placeholder || 'Select an option';
        const customClass = select.dataset.wrapperClass || '';

        // Extract width / sizing classes from select to apply directly to wrapper
        const sizingClasses = Array.from(select.classList).filter(c => 
            c.startsWith('w-') || c.startsWith('min-w-') || c.startsWith('max-w-') ||
            c.startsWith('sm:w-') || c.startsWith('md:w-') || c.startsWith('lg:w-')
        );

        // Create container wrapper
        const wrapper = document.createElement('div');
        const defaultWidth = sizingClasses.length > 0 ? sizingClasses.join(' ') : 'w-full';
        wrapper.className = `custom-select-wrapper relative inline-block ${defaultWidth} ${customClass}`.trim();
        if (select.style.width) wrapper.style.width = select.style.width;

        // Hide native select but keep accessible for form/HTMX
        select.classList.add('sr-only');
        select.style.position = 'absolute';
        select.style.opacity = '0';
        select.style.pointerEvents = 'none';
        select.style.width = '1px';
        select.style.height = '1px';

        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);

        // Find selected option
        let selectedOption = select.options[select.selectedIndex] || select.options[0];

        // 1. Build Trigger Box (Clean raw text, strict left alignment, no avatar box)
        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = `custom-select-trigger w-full flex items-center justify-between text-left text-xs sm:text-sm bg-slate-50 hover:bg-white border border-slate-300 rounded-xl px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-600 focus:border-teal-600 transition-all shadow-2xs cursor-pointer`;
        if (select.disabled) {
            trigger.classList.add('opacity-60', 'cursor-not-allowed', 'bg-slate-100');
            trigger.disabled = true;
        }

        const triggerContent = document.createElement('div');
        triggerContent.className = 'flex items-center space-x-2 min-w-0 flex-1 pr-2 text-left justify-start';

        const triggerTextContainer = document.createElement('div');
        triggerTextContainer.className = 'min-w-0 flex-1 truncate text-left';

        const triggerLabel = document.createElement('span');
        triggerLabel.className = 'custom-select-trigger-label font-bold text-slate-900 text-xs sm:text-sm truncate block text-left';

        const triggerSubtitle = document.createElement('span');
        triggerSubtitle.className = 'custom-select-trigger-subtitle text-slate-400 text-[11px] truncate block text-left';

        triggerTextContainer.appendChild(triggerLabel);
        triggerTextContainer.appendChild(triggerSubtitle);
        triggerContent.appendChild(triggerTextContainer);

        const chevron = document.createElement('div');
        chevron.className = 'custom-select-chevron shrink-0 ml-1.5 text-slate-400 transition-transform duration-200';
        chevron.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`;

        trigger.appendChild(triggerContent);
        trigger.appendChild(chevron);
        wrapper.appendChild(trigger);

        // 2. Build Dropdown Menu Panel with proper auto-width to ensure all content is visible
        const menu = document.createElement('div');
        menu.className = 'custom-select-menu hidden absolute top-full left-0 mt-1.5 bg-white rounded-xl shadow-2xl border border-slate-200 p-1.5 z-50 transition-all animate-in fade-in duration-150 min-w-full';
        menu.style.minWidth = '100%';
        menu.style.width = 'max-content';
        menu.style.maxWidth = 'min(90vw, 380px)';

        let searchInput = null;
        if (isSearchable) {
            const searchContainer = document.createElement('div');
            searchContainer.className = 'relative mb-1.5 px-0.5';
            searchContainer.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                <input type="text" placeholder="Search..." class="custom-select-search w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:bg-white focus:outline-none focus:border-teal-600 focus:ring-1 focus:ring-teal-600">
            `;
            searchInput = searchContainer.querySelector('input');
            menu.appendChild(searchContainer);
        }

        const optionsContainer = document.createElement('div');
        optionsContainer.className = 'custom-select-options-container max-h-56 overflow-y-auto space-y-0.5 divide-y divide-slate-100 pr-0.5';

        const emptyState = document.createElement('div');
        emptyState.className = 'custom-select-empty hidden py-3 text-center text-xs text-slate-400';
        emptyState.textContent = 'No options match your search';

        menu.appendChild(optionsContainer);
        menu.appendChild(emptyState);
        wrapper.appendChild(menu);

        /**
         * Render option cards with clean raw text (no boxed badge text)
         */
        function renderOptions() {
            optionsContainer.innerHTML = '';
            Array.from(select.options).forEach((opt, idx) => {
                if (opt.disabled && !opt.value) return;

                const optCard = document.createElement('div');
                optCard.className = `custom-select-option px-2.5 py-2 rounded-lg cursor-pointer flex items-center justify-between transition-colors whitespace-nowrap ${opt.selected ? 'bg-teal-50/80 text-teal-950' : 'hover:bg-teal-50 text-slate-800'}`;
                optCard.dataset.value = opt.value;
                optCard.dataset.index = idx;
                optCard.dataset.text = (opt.textContent || '').toLowerCase();
                optCard.dataset.sub = (opt.dataset.subtitle || '').toLowerCase();

                const infoCol = document.createElement('div');
                infoCol.className = 'min-w-0 flex-1 pr-3';

                const optTitle = document.createElement('p');
                optTitle.className = `text-xs font-bold leading-tight ${opt.selected ? 'text-teal-900' : 'text-slate-900'}`;
                optTitle.textContent = opt.textContent;

                infoCol.appendChild(optTitle);

                if (opt.dataset.subtitle) {
                    const optSub = document.createElement('p');
                    optSub.className = 'text-[11px] text-slate-500 mt-0.5';
                    optSub.innerHTML = opt.dataset.subtitle;
                    infoCol.appendChild(optSub);
                }

                optCard.appendChild(infoCol);

                // Checkmark for selected item (clean, no boxed text)
                if (opt.selected) {
                    const check = document.createElement('span');
                    check.className = 'text-teal-600 shrink-0 ml-2';
                    check.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
                    optCard.appendChild(check);
                }

                optCard.addEventListener('click', (e) => {
                    e.stopPropagation();
                    selectValue(opt.value);
                    closeMenu();
                });

                optionsContainer.appendChild(optCard);
            });
        }

        /**
         * Update the Trigger Box based on current select.value
         */
        function updateTrigger() {
            selectedOption = select.options[select.selectedIndex] || select.options[0];
            if (!selectedOption) {
                triggerLabel.textContent = placeholder;
                triggerSubtitle.textContent = '';
                triggerSubtitle.classList.add('hidden');
                return;
            }

            triggerLabel.textContent = selectedOption.textContent || placeholder;

            if (selectedOption.dataset.subtitle) {
                triggerSubtitle.innerHTML = selectedOption.dataset.subtitle;
                triggerSubtitle.classList.remove('hidden');
            } else {
                triggerSubtitle.textContent = '';
                triggerSubtitle.classList.add('hidden');
            }

            // Update active state on option cards
            optionsContainer.querySelectorAll('.custom-select-option').forEach(card => {
                if (card.dataset.value === select.value) {
                    card.classList.add('bg-teal-50/80');
                    card.querySelector('p')?.classList.add('text-teal-900');
                } else {
                    card.classList.remove('bg-teal-50/80');
                    card.querySelector('p')?.classList.remove('text-teal-900');
                }
            });

            if (window.lucide) {
                lucide.createIcons();
            }
        }

        /**
         * Select a value programmatically or via click
         */
        function selectValue(val) {
            if (select.value === val) return;
            select.value = val;
            updateTrigger();

            // Dispatch standard events for forms and HTMX
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));

            // Trigger onchange if specified directly on the element
            if (typeof select.onchange === 'function') {
                select.onchange();
            }
        }

        function openMenu() {
            // Close other open menus first
            document.querySelectorAll('.custom-select-menu').forEach(m => {
                if (m !== menu && !m.classList.contains('hidden')) {
                    m.classList.add('hidden');
                    const wr = m.closest('.custom-select-wrapper');
                    const ch = wr?.querySelector('.custom-select-chevron');
                    if (ch) ch.style.transform = 'rotate(0deg)';
                }
            });

            menu.classList.remove('hidden');
            chevron.style.transform = 'rotate(180deg)';
            trigger.classList.add('border-teal-600', 'ring-2', 'ring-teal-600/20');

            // Prevent clipping past viewport right edge
            const rect = menu.getBoundingClientRect();
            if (rect.right > (window.innerWidth || document.documentElement.clientWidth) - 10) {
                menu.style.left = 'auto';
                menu.style.right = '0';
            } else {
                menu.style.left = '0';
                menu.style.right = 'auto';
            }

            if (searchInput) {
                searchInput.value = '';
                filterOptions('');
                setTimeout(() => searchInput.focus(), 50);
            }

            if (window.lucide) {
                lucide.createIcons();
            }
        }

        function closeMenu() {
            menu.classList.add('hidden');
            chevron.style.transform = 'rotate(0deg)';
            trigger.classList.remove('border-teal-600', 'ring-2', 'ring-teal-600/20');
        }

        function toggleMenu() {
            if (menu.classList.contains('hidden')) {
                openMenu();
            } else {
                closeMenu();
            }
        }

        function filterOptions(query) {
            const q = query.toLowerCase().trim();
            const cards = optionsContainer.querySelectorAll('.custom-select-option');
            let matchCount = 0;

            cards.forEach(card => {
                const text = card.dataset.text || '';
                const sub = card.dataset.sub || '';
                if (!q || text.includes(q) || sub.includes(q)) {
                    card.classList.remove('hidden');
                    matchCount++;
                } else {
                    card.classList.add('hidden');
                }
            });

            if (matchCount === 0) {
                emptyState.classList.remove('hidden');
            } else {
                emptyState.classList.add('hidden');
            }
        }

        // Trigger Click Handler
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleMenu();
        });

        // Search Input Filter Handler
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                filterOptions(e.target.value);
            });
            searchInput.addEventListener('click', (e) => e.stopPropagation());
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') closeMenu();
            });
        }

        // Sync if select value changed externally or by JS
        select.addEventListener('change', () => {
            updateTrigger();
        });

        // Observe options changes (e.g. cascading selects or dynamically loaded options)
        const observer = new MutationObserver(() => {
            renderOptions();
            updateTrigger();
        });
        observer.observe(select, { childList: true, subtree: true, attributes: true });

        // Initial render
        renderOptions();
        updateTrigger();
    }

    /**
     * Scan and enhance all eligible select elements in a scope
     */
    function initCustomSelects(root = document) {
        if (!root) return;
        const selects = root.querySelectorAll('select.custom-select, select[data-custom-select]');
        selects.forEach(sel => enhanceSelect(sel));
    }

    // Close on click outside or Escape
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.custom-select-wrapper')) {
            document.querySelectorAll('.custom-select-menu').forEach(m => {
                if (!m.classList.contains('hidden')) {
                    m.classList.add('hidden');
                    const wr = m.closest('.custom-select-wrapper');
                    const ch = wr?.querySelector('.custom-select-chevron');
                    if (ch) ch.style.transform = 'rotate(0deg)';
                }
            });
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.custom-select-menu').forEach(m => {
                if (!m.classList.contains('hidden')) {
                    m.classList.add('hidden');
                    const wr = m.closest('.custom-select-wrapper');
                    const ch = wr?.querySelector('.custom-select-chevron');
                    if (ch) ch.style.transform = 'rotate(0deg)';
                }
            });
        }
    });

    // Expose globally
    window.HRMSCustomSelect = {
        init: initCustomSelects,
        enhance: enhanceSelect
    };

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => initCustomSelects());
    } else {
        initCustomSelects();
    }

    // Re-initialize on HTMX swaps
    document.addEventListener('htmx:afterSwap', (e) => {
        initCustomSelects(e.detail.target || document);
    });

})();
