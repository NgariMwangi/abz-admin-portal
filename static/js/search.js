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
    
    // Product Search Functionality
    const productSearch = document.getElementById('productSearch');
    const categoryFilter = document.getElementById('categoryFilter');
    const displayFilter = document.getElementById('displayFilter');
    
    if (productSearch) {
        console.log('Product search element found');
        productSearch.addEventListener('keyup', function() {
            console.log('Product search triggered:', this.value);
            filterProducts();
        });
    }
    
    if (categoryFilter) {
        categoryFilter.addEventListener('change', function() {
            console.log('Category filter changed:', this.value);
            filterProducts();
        });
    }
    
    if (displayFilter) {
        displayFilter.addEventListener('change', function() {
            console.log('Display filter changed:', this.value);
            filterProducts();
        });
    }
    
    function filterProducts() {
        const searchTerm = document.getElementById('productSearch').value.toLowerCase();
        const categoryFilter = document.getElementById('categoryFilter').value.toLowerCase();
        const displayFilter = document.getElementById('displayFilter').value;
        
        const table = document.getElementById('productsTable');
        const tbody = table.getElementsByTagName('tbody')[0];
        const rows = tbody.getElementsByTagName('tr');
        
        console.log('Filtering products:', { searchTerm, categoryFilter, displayFilter, rowCount: rows.length });
        
        for (let i = 0; i < rows.length; i++) {
            const nameCell = rows[i].getElementsByTagName('td')[2];
            const categoryCell = rows[i].getElementsByTagName('td')[3];
            const productCodeCell = rows[i].getElementsByTagName('td')[8];
            const displayCell = rows[i].getElementsByTagName('td')[9];
            
            if (nameCell && categoryCell && productCodeCell && displayCell) {
                const name = nameCell.textContent.toLowerCase();
                const category = categoryCell.textContent.toLowerCase();
                const productCode = productCodeCell.textContent.toLowerCase();
                const displayText = displayCell.textContent.toLowerCase();
                
                // Check search term
                const matchesSearch = name.includes(searchTerm) || 
                                    category.includes(searchTerm) || 
                                    productCode.includes(searchTerm);
                
                // Check category filter
                const matchesCategory = categoryFilter === '' || category.includes(categoryFilter);
                
                // Check display filter
                let matchesDisplay = true;
                if (displayFilter === 'true') {
                    matchesDisplay = displayText.includes('visible');
                } else if (displayFilter === 'false') {
                    matchesDisplay = displayText.includes('hidden');
                }
                
                if (matchesSearch && matchesCategory && matchesDisplay) {
                    rows[i].style.display = '';
                } else {
                    rows[i].style.display = 'none';
                }
            }
        }
    }
    
    // Make clearFilters function global
    window.clearFilters = function() {
        console.log('Clearing filters');
        document.getElementById('productSearch').value = '';
        document.getElementById('categoryFilter').value = '';
        document.getElementById('displayFilter').value = '';
        filterProducts();
    };
    
    console.log('Search functionality initialized successfully');
}); 