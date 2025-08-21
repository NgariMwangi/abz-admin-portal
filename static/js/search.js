// Search functionality for products and categories
document.addEventListener('DOMContentLoaded', function() {
    console.log('Search functionality loading...');
    
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
    
    // Product Search Functionality - Server-side search with auto-submit
    const productSearch = document.getElementById('productSearch');
    const categoryFilter = document.getElementById('categoryFilter');
    const displayFilter = document.getElementById('displayFilter');
    
    // Find the search form - look for forms with search inputs
    const searchForm = productSearch ? productSearch.closest('form') : null;
    
    let searchTimeout;
    
    if (productSearch && searchForm) {
        console.log('Product search element and form found');
        
        // Auto-submit search after user stops typing (500ms delay)
        productSearch.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                console.log('Auto-submitting search for:', this.value);
                searchForm.submit();
            }, 500);
        });
        
        // Also submit on Enter key
        productSearch.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(searchTimeout);
                searchForm.submit();
            }
        });
    }
    
    if (categoryFilter && searchForm) {
        categoryFilter.addEventListener('change', function() {
            console.log('Category filter changed, submitting form');
            searchForm.submit();
        });
    }
    
    if (displayFilter && searchForm) {
        displayFilter.addEventListener('change', function() {
            console.log('Display filter changed, submitting form');
            searchForm.submit();
        });
    }
    
    // Make clearFilters function global
    window.clearFilters = function() {
        console.log('Clearing filters');
        if (productSearch) productSearch.value = '';
        if (categoryFilter) categoryFilter.value = '';
        if (displayFilter) displayFilter.value = '';
        
        // Submit the form to refresh results
        if (searchForm) {
            searchForm.submit();
        }
    };
    
    console.log('Search functionality initialized successfully');
}); 