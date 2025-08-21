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
    const productSearch = document.getElementById('productSearch');
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
            e.preventDefault();
            const link = e.target.closest('.page-link');
            const href = link.getAttribute('href');
            if (href) {
                console.log('Pagination clicked:', href);
                performPagination(href);
            }
        }
    });
    
    function showLoading() {
        const tableBody = document.querySelector('#productsTable tbody');
        if (tableBody) {
            // Determine the number of columns based on the page type
            const columnCount = isBranchProductsPage ? 10 : 11;
            console.log('Showing loading with column count:', columnCount);
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
            
            // Extract the table body content
            const newTableBody = tempDiv.querySelector('#productsTable tbody');
            const currentTableBody = document.querySelector('#productsTable tbody');
            
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
            
            // Extract the table body content
            const newTableBody = tempDiv.querySelector('#productsTable tbody');
            const currentTableBody = document.querySelector('#productsTable tbody');
            
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
    
    console.log('Search functionality initialized successfully');
    console.log('Page type:', isBranchProductsPage ? 'Branch Products' : 'Main Products');
}); 