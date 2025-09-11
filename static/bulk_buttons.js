function updateBulkButtons() {
    const checkboxes = document.querySelectorAll('input[name="selected_domains"]:checked');
    const allowBtn = document.getElementById('allowSelected');
    const removeBtn = document.getElementById('removeSelected');
    const enabled = checkboxes.length > 0;
    if (allowBtn) allowBtn.disabled = !enabled;
    if (removeBtn) removeBtn.disabled = !enabled;
}

function toggleAll(source) {
    const checkboxes = document.querySelectorAll('input[name="selected_domains"]');
    for(let i=0; i<checkboxes.length; i++) {
        checkboxes[i].checked = source.checked;
    }
    updateBulkButtons();
}

document.addEventListener('DOMContentLoaded', function() {
    const checkboxes = document.querySelectorAll('input[name="selected_domains"]');
    for(let i=0; i<checkboxes.length; i++) {
        checkboxes[i].addEventListener('change', updateBulkButtons);
    }
    const selectAll = document.getElementById('selectAll');
    if (selectAll) {
        selectAll.addEventListener('change', function() {
            toggleAll(this);
        });
    }
    updateBulkButtons();
});
