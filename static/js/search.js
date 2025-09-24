// Search functionality for products and categories
document.addEventListener('DOMContentLoaded', function() {
    console.log('Search functionality loading...');
    console.log('Current URL:', window.location.href);
    console.log('Current pathname:', window.location.pathname);
    
    // Category Search Functionality
    const categorySearch = document.getElementById('categorySearch');
    if (categorySearch) {
        console.log('Category search element found');
        categorySearch.addEventListener('keyup', function() {
            console.log('Category search triggered:', this.value);
            const searchTerm = this.value.toLowerCase();
            const table = document.getElementById('categoriesTable');
            const tbody = table.getElementsByTagName('tbody')[0];
            const rows = tbody.getElementsByTagName('tr');
            
            for (let i = 0; i < rows.length; i++) {
                const nameCell = rows[i].getElementsByTagName('td')[1];
                const descCell = rows[i].getElementsByTagName('td')[2];
                
                if (nameCell && descCell) {
                    const name = nameCell.textContent.toLowerCase();
                    const description = descCell.textContent.toLowerCase();
                    
                    if (name.includes(searchTerm) || description.includes(searchTerm)) {
                        rows[i].style.display = '';
                    } else {
                        rows[i].style.display = 'none';
                    }
                }
            }
        });
    } else {
        console.log('Category search element not found');
    }
    
    // Product Search Functionality - AJAX search with URL updates
    const productSearch = document.getElementById('productSearch') || document.getElementById('catalogSearch');
    const categoryFilter = document.getElementById('categoryFilter');
    const displayFilter = document.getElementById('displayFilter');
    const perPageSelect = document.querySelector('select[name="per_page"]');
    
    // Find the search form - look for forms with search inputs
    const searchForm = productSearch ? productSearch.closest('form') : null;
    
    // Check if we're on a branch products page or main products page
    const isBranchProductsPage = window.location.pathname.includes('/branch_products/');
    
    console.log('Page type detection:', {
        isBranchProductsPage: isBranchProductsPage,
        pathname: window.location.pathname,
        productSearch: !!productSearch,
        searchForm: !!searchForm
    });
    
    let searchTimeout;
    
    if (productSearch && searchForm) {
        console.log('Product search element and form found');
        
        // Auto-search after user stops typing (500ms delay)
        productSearch.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                console.log('Auto-searching for:', this.value);
                performSearch();
            }, 500);
        });
        
        // Also search on Enter key
        productSearch.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(searchTimeout);
                performSearch();
            }
        });
    } else {
        console.log('Product search elements not found:', {
            productSearch: !!productSearch,
            searchForm: !!searchForm
        });
    }
    
    if (categoryFilter && searchForm) {
        categoryFilter.addEventListener('change', function() {
            console.log('Category filter changed, searching...');
            performSearch();
        });
    }
    
    if (displayFilter && searchForm) {
        displayFilter.addEventListener('change', function() {
            console.log('Display filter changed, searching...');
            performSearch();
        });
    }
    
    if (perPageSelect && searchForm) {
        perPageSelect.addEventListener('change', function() {
            console.log('Per page changed, searching...');
            performSearch();
        });
    }
    
    // Handle pagination clicks with event delegation
    document.addEventListener('click', function(e) {
        if (e.target.closest('.pagination .page-link')) {
            const link = e.target.closest('.page-link');
            const href = link.getAttribute('href');
            if (href) {
                console.log('Pagination clicked:', href);
                
                // For Product Catalog page, use regular navigation to preserve modals
                if (window.location.pathname === '/product_catalog') {
                    console.log('Using regular navigation for Product Catalog page');
                    window.location.href = href;
                    return;
                }
                
                // For other pages, use AJAX pagination
                e.preventDefault();
                performPagination(href);
            }
        }
    });
    
    function showLoading() {
        // Try to find the table body - check for both productsTable and catalogTable
        const tableBody = document.querySelector('#productsTable tbody') || document.querySelector('#catalogTable tbody');
        if (tableBody) {
            // Determine the number of columns based on the page type
            const isCatalogPage = window.location.pathname === '/product_catalog';
            const columnCount = isBranchProductsPage ? 10 : (isCatalogPage ? 8 : 11);
            console.log('Showing loading with column count:', columnCount, 'for page:', isCatalogPage ? 'catalog' : 'products');
            tableBody.innerHTML = `
                <tr>
                    <td colspan="${columnCount}" class="text-center py-4">
                        <div class="d-flex align-items-center justify-content-center">
                            <div class="spinner-border spinner-border-sm me-2" role="status">
                                <span class="visually-hidden">Loading...</span>
                            </div>
                            <span>Searching...</span>
                        </div>
                    </td>
                </tr>
            `;
        } else {
            console.log('Table body not found for loading indicator');
        }
    }
    
    function performSearch() {
        if (!searchForm) {
            console.log('No search form found, cannot perform search');
            return;
        }
        
        console.log('Performing search...');
        
        // For Product Catalog page, use regular form submission to preserve modals
        if (window.location.pathname === '/product_catalog') {
            console.log('Using regular form submission for Product Catalog page');
            searchForm.submit();
            return;
        }
        
        // Show loading indicator
        showLoading();
        
        // Get all form data
        const formData = new FormData(searchForm);
        const searchParams = new URLSearchParams();
        
        // Convert FormData to URLSearchParams
        for (let [key, value] of formData.entries()) {
            if (value) { // Only add non-empty values
                searchParams.append(key, value);
            }
        }
        
        // Get current URL and update with new search parameters
        const currentUrl = new URL(window.location);
        currentUrl.search = searchParams.toString();
        
        console.log('Search URL:', currentUrl.toString());
        
        // Update browser URL without page reload
        window.history.pushState({}, '', currentUrl);
        
        // Perform AJAX request to get updated results
        fetch(currentUrl.pathname + currentUrl.search, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            console.log('Search response status:', response.status);
            return response.text();
        })
        .then(html => {
            console.log('Search response received, length:', html.length);
            
            // Create a temporary div to parse the HTML
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = html;
            
            // Extract the table body content - check for both table types
            const newTableBody = tempDiv.querySelector('#productsTable tbody') || tempDiv.querySelector('#catalogTable tbody');
            const currentTableBody = document.querySelector('#productsTable tbody') || document.querySelector('#catalogTable tbody');
            
            if (newTableBody && currentTableBody) {
                // Update the table content
                currentTableBody.innerHTML = newTableBody.innerHTML;
                
                // Update pagination if it exists
                const newPagination = tempDiv.querySelector('.pagination');
                const currentPagination = document.querySelector('.pagination');
                if (newPagination && currentPagination) {
                    currentPagination.innerHTML = newPagination.innerHTML;
                }
                
                // Update result count if it exists
                const newResultCount = tempDiv.querySelector('.text-center.text-muted');
                const currentResultCount = document.querySelector('.text-center.text-muted');
                if (newResultCount && currentResultCount) {
                    currentResultCount.innerHTML = newResultCount.innerHTML;
                }
                
                // Update items per page selector if it exists
                const newItemsPerPage = tempDiv.querySelector('.items-per-page');
                const currentItemsPerPage = document.querySelector('.items-per-page');
                if (newItemsPerPage && currentItemsPerPage) {
                    currentItemsPerPage.innerHTML = newItemsPerPage.innerHTML;
                }
                
                // Re-initialize functions that might be lost during AJAX updates
                initializePageFunctions();
                
                // Re-initialize Bootstrap components for any new content
                reinitializeBootstrapComponents();
                
                console.log('Search results updated successfully');
            } else {
                console.log('Table body elements not found:', {
                    newTableBody: !!newTableBody,
                    currentTableBody: !!currentTableBody
                });
            }
        })
        .catch(error => {
            console.error('Error performing search:', error);
            // Fallback to regular form submission if AJAX fails
            console.log('Falling back to regular form submission');
            searchForm.submit();
        });
    }
    
    function performPagination(url) {
        console.log('Performing pagination to:', url);
        
        // Show loading indicator
        showLoading();
        
        // Update browser URL without page reload
        window.history.pushState({}, '', url);
        
        // Perform AJAX request to get updated results
        fetch(url, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            console.log('Pagination response status:', response.status);
            return response.text();
        })
        .then(html => {
            console.log('Pagination response received, length:', html.length);
            
            // Create a temporary div to parse the HTML
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = html;
            
            // Extract the table body content - check for both table types
            const newTableBody = tempDiv.querySelector('#productsTable tbody') || tempDiv.querySelector('#catalogTable tbody');
            const currentTableBody = document.querySelector('#productsTable tbody') || document.querySelector('#catalogTable tbody');
            
            if (newTableBody && currentTableBody) {
                // Update the table content
                currentTableBody.innerHTML = newTableBody.innerHTML;
                
                // Update pagination if it exists
                const newPagination = tempDiv.querySelector('.pagination');
                const currentPagination = document.querySelector('.pagination');
                if (newPagination && currentPagination) {
                    currentPagination.innerHTML = newPagination.innerHTML;
                }
                
                // Update result count if it exists
                const newResultCount = tempDiv.querySelector('.text-center.text-muted');
                const currentResultCount = document.querySelector('.text-center.text-muted');
                if (newResultCount && currentResultCount) {
                    currentResultCount.innerHTML = newResultCount.innerHTML;
                }
                
                // Update items per page selector if it exists
                const newItemsPerPage = tempDiv.querySelector('.items-per-page');
                const currentItemsPerPage = document.querySelector('.items-per-page');
                if (newItemsPerPage && currentItemsPerPage) {
                    currentItemsPerPage.innerHTML = newItemsPerPage.innerHTML;
                }
                
                // Re-initialize functions that might be lost during AJAX updates
                initializePageFunctions();
                
                // Re-initialize Bootstrap components for any new content
                reinitializeBootstrapComponents();
                
                console.log('Pagination results updated successfully');
            } else {
                console.log('Table body elements not found for pagination:', {
                    newTableBody: !!newTableBody,
                    currentTableBody: !!currentTableBody
                });
            }
        })
        .catch(error => {
            console.error('Error performing pagination:', error);
            // Fallback to regular navigation if AJAX fails
            console.log('Falling back to regular navigation');
            window.location.href = url;
        });
    }
    
    // Make clearFilters function global
    window.clearFilters = function() {
        console.log('Clearing filters');
        if (productSearch) productSearch.value = '';
        if (categoryFilter) categoryFilter.value = '';
        if (displayFilter) displayFilter.value = '';
        
        // Perform search with cleared filters
        performSearch();
    };
    
    // Initialize page-specific functions
    initializePageFunctions();
    
    console.log('Search functionality initialized successfully');
    console.log('Page type:', isBranchProductsPage ? 'Branch Products' : 'Main Products');
});

// Function to initialize page-specific functions that might be lost during AJAX updates
function initializePageFunctions() {
    // Re-initialize changeItemsPerPage function for catalog pages
    if (window.location.pathname === '/product_catalog') {
        window.changeItemsPerPage = function(perPage) {
            const currentUrl = new URL(window.location);
            currentUrl.searchParams.set('per_page', perPage);
            currentUrl.searchParams.set('page', '1'); // Reset to first page
            window.location.href = currentUrl.toString();
        };
    }
}

// Function to reinitialize Bootstrap components after AJAX content updates
function reinitializeBootstrapComponents() {
    console.log('Reinitializing Bootstrap components...');
    
    // Dispose all existing modal instances to prevent conflicts
    document.querySelectorAll('.modal').forEach(function(modalElement) {
        const existingInstance = bootstrap.Modal.getInstance(modalElement);
        if (existingInstance) {
            console.log('Disposing existing modal instance for:', modalElement.id);
            existingInstance.dispose();
        }
    });
    
    // Reinitialize tooltips if they exist
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        }
    });
    
    // Reinitialize popovers if they exist
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        if (typeof bootstrap !== 'undefined' && bootstrap.Popover) {
            return new bootstrap.Popover(popoverTriggerEl);
        }
    });
    
    // Make sure modal functions are available globally after AJAX updates
    if (window.location.pathname.includes('/branch_products/')) {
        // The modal functions should already be globally available from the main page script
        // Just ensure Bootstrap modals are properly initialized
        console.log('Branch products page detected, modal functions should be available globally');
    }
    
    console.log('Bootstrap components reinitialized');
} 