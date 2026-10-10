/**
 * Universal Table & Record Pagination Engine
 * Automatically paginates client-side tables and lists when records exceed page size.
 * Seamlessly integrates with realtime search inputs and filter selects.
 */

(function () {
    'use strict';

    class TablePaginator {
        constructor(table, options = {}) {
            this.table = table;
            this.pageSize = parseInt(table.dataset.pageSize || options.pageSize || 15, 10);
            this.currentPage = 1;
            this.entityLabel = table.dataset.entityLabel || 'records';
            this.tbody = table.querySelector('tbody') || table;
            this.searchSelector = table.dataset.searchInput;
            this.filterSelector = table.dataset.filterSelect;

            this.init();
        }

        getRows() {
            // Get non-header, non-empty-state direct row children
            return Array.from(this.tbody.querySelectorAll('tr:not(.empty-row):not(.table-header-row), .paginate-row'));
        }

        getVisibleRows() {
            // Filter out rows hidden by custom search/filter functions (display: none or class hidden)
            return this.getRows().filter(row => !row.classList.contains('filter-hidden') && row.style.display !== 'none');
        }

        init() {
            if (this.table._paginatorInitialized) return;
            this.table._paginatorInitialized = true;

            // Create pagination container below table
            this.container = document.createElement('div');
            this.container.className = 'table-pagination-bar px-4 sm:px-6 py-3.5 bg-slate-50 border-t border-slate-200/90 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600 select-none';
            
            const tableWrapper = this.table.closest('.overflow-x-auto') || this.table.parentNode;
            tableWrapper.parentNode.insertBefore(this.container, tableWrapper.nextSibling);

            // Hook into search and filter inputs if specified
            if (this.searchSelector) {
                const searchInput = document.querySelector(this.searchSelector);
                if (searchInput) {
                    searchInput.addEventListener('input', () => {
                        this.currentPage = 1;
                        setTimeout(() => this.render(), 10);
                    });
                }
            }

            if (this.filterSelector) {
                document.querySelectorAll(this.filterSelector).forEach(filterEl => {
                    filterEl.addEventListener('change', () => {
                        this.currentPage = 1;
                        setTimeout(() => this.render(), 10);
                    });
                });
            }

            this.render();
        }

        render() {
            const rows = this.getRows();
            const visibleRows = this.getVisibleRows();
            const total = visibleRows.length;
            const totalPages = Math.max(1, Math.ceil(total / this.pageSize));

            if (this.currentPage > totalPages) {
                this.currentPage = totalPages;
            }

            // If total records is less than or equal to page size and only 1 page, hide pagination bar or show compact
            if (total <= this.pageSize && totalPages <= 1) {
                this.container.style.display = total === 0 ? 'none' : 'flex';
                // Show all visible
                visibleRows.forEach(row => {
                    row.classList.remove('page-hidden');
                });
            } else {
                this.container.style.display = 'flex';
            }

            const startIdx = (this.currentPage - 1) * this.pageSize;
            const endIdx = startIdx + this.pageSize;

            // Apply pagination visibility
            visibleRows.forEach((row, idx) => {
                if (idx >= startIdx && idx < endIdx) {
                    row.classList.remove('page-hidden');
                } else {
                    row.classList.add('page-hidden');
                }
            });

            // Build UI controls matching _pagination.html
            const startRecord = total > 0 ? startIdx + 1 : 0;
            const endRecord = Math.min(endIdx, total);

            let pageNumbers = this.generatePageNumbers(this.currentPage, totalPages);

            let pageButtonsHtml = pageNumbers.map(p => {
                if (p === '...') {
                    return `<span class="px-2 py-1 text-slate-400 font-mono text-xs">…</span>`;
                }
                if (p === this.currentPage) {
                    return `<span class="px-3 py-1 rounded-lg bg-teal-700 text-white font-bold font-mono text-xs shadow-xs">${p}</span>`;
                }
                return `<button type="button" data-page="${p}" class="page-num-btn px-3 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 font-medium font-mono text-xs transition-colors shadow-2xs cursor-pointer">${p}</button>`;
            }).join('');

            this.container.innerHTML = `
                <!-- Record Counter -->
                <div class="flex items-center space-x-1.5 flex-wrap">
                    <span class="text-slate-500">Showing</span>
                    <span class="font-bold font-mono text-slate-900">${startRecord}</span>
                    <span class="text-slate-400">–</span>
                    <span class="font-bold font-mono text-slate-900">${endRecord}</span>
                    <span class="text-slate-500">of</span>
                    <span class="font-bold font-mono text-slate-900">${total}</span>
                    <span class="text-slate-500">${this.entityLabel}</span>
                    <span class="text-slate-300 mx-1">•</span>
                    <span class="text-[11px] text-teal-800 font-semibold bg-teal-50 border border-teal-200/80 px-2 py-0.5 rounded">
                        ${this.pageSize} / page
                    </span>
                </div>

                <!-- Navigation Buttons -->
                <div class="flex items-center space-x-1.5">
                    <!-- Prev Button -->
                    ${this.currentPage > 1 ? `
                        <button type="button" data-page="${this.currentPage - 1}" class="prev-page-btn inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 font-semibold text-slate-700 transition-colors shadow-2xs cursor-pointer">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 mr-1 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                            <span>Previous</span>
                        </button>
                    ` : `
                        <span class="inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200/60 bg-slate-100/60 font-semibold text-slate-400 opacity-50 cursor-not-allowed shadow-none">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 mr-1 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
                            <span>Previous</span>
                        </span>
                    `}

                    <!-- Page Pills -->
                    <div class="flex items-center space-x-1">
                        ${pageButtonsHtml}
                    </div>

                    <!-- Next Button -->
                    ${this.currentPage < totalPages ? `
                        <button type="button" data-page="${this.currentPage + 1}" class="next-page-btn inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 font-semibold text-slate-700 transition-colors shadow-2xs cursor-pointer">
                            <span>Next</span>
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 ml-1 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                        </button>
                    ` : `
                        <span class="inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200/60 bg-slate-100/60 font-semibold text-slate-400 opacity-50 cursor-not-allowed shadow-none">
                            <span>Next</span>
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 ml-1 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                        </span>
                    `}
                </div>
            `;

            // Bind click handlers to pagination buttons
            this.container.querySelectorAll('button[data-page]').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.currentPage = parseInt(btn.dataset.page, 10);
                    this.render();
                });
            });
        }

        generatePageNumbers(current, total, delta = 2) {
            if (total <= 7) {
                return Array.from({ length: total }, (_, i) => i + 1);
            }
            const pages = [];
            const left = Math.max(2, current - delta);
            const right = Math.min(total - 1, current + delta);

            pages.push(1);
            if (left > 2) pages.push('...');
            for (let i = left; i <= right; i++) {
                pages.push(i);
            }
            if (right < total - 1) pages.push('...');
            pages.push(total);
            return pages;
        }
    }

    // CSS styling for hidden paged rows
    const style = document.createElement('style');
    style.textContent = `
        tr.page-hidden, div.page-hidden {
            display: none !important;
        }
    `;
    document.head.appendChild(style);

    function initTablePagination(root = document) {
        const tables = root.querySelectorAll('table[data-paginate="true"], table.paginated-table, .paginated-container[data-paginate="true"]');
        tables.forEach(tbl => {
            if (!tbl._tablePaginator) {
                tbl._tablePaginator = new TablePaginator(tbl);
            } else {
                tbl._tablePaginator.render();
            }
        });
    }

    window.HRMSTablePagination = {
        init: initTablePagination,
        refresh: function (table) {
            if (table && table._tablePaginator) {
                table._tablePaginator.render();
            }
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => initTablePagination());
    } else {
        initTablePagination();
    }

    document.addEventListener('htmx:afterSwap', (e) => {
        initTablePagination(e.detail.target || document);
    });

})();
