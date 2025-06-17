document.addEventListener('DOMContentLoaded', function() {
    // For each new inline row, set the origin airport to the previous destination airport
    function autofillNextOrigin() {
        const inlines = document.querySelectorAll('.dynamic-flightleg_set');
        for (let i = 1; i < inlines.length; i++) {
            const prevDest = inlines[i-1].querySelector('[name$="-destination_airport"]');
            const currOrigin = inlines[i].querySelector('[name$="-origin_airport"]');
            if (prevDest && currOrigin && !currOrigin.value) {
                currOrigin.value = prevDest.value;
            }
        }
    }
    // Run on page load and when new inlines are added
    autofillNextOrigin();
    document.body.addEventListener('click', function(e) {
        if (e.target && e.target.classList.contains('add-row')) {
            setTimeout(autofillNextOrigin, 100);
        }
    });
}); 