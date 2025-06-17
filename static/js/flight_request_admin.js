(function($) {
    'use strict';

    function updateCityChoices(countryField, cityField) {
        const country = $(countryField).val();
        if (!country) {
            $(cityField).html('<option value="">---------</option>').trigger('change');
            return;
        }

        $.getJSON('/admin/flights/flightrequest/get-cities/', {country: country}, function(data) {
            let options = '<option value="">---------</option>';
            data.cities.forEach(function(city) {
                options += `<option value="${city}">${city}</option>`;
            });
            $(cityField).html(options).trigger('change');
        });
    }

    $(document).ready(function() {
        // Initialize select2 for all select fields
        $('.select2').select2({
            width: '100%',
            theme: 'unfold'
        });

        // Handle origin country change
        $('#id_origin_country').on('change', function() {
            updateCityChoices('#id_origin_country', '#id_origin_city');
            $('#id_origin_airport').val('').trigger('change');
        });

        // Handle destination country change
        $('#id_destination_country').on('change', function() {
            updateCityChoices('#id_destination_country', '#id_destination_city');
            $('#id_destination_airport').val('').trigger('change');
        });

        // Handle city changes
        $('#id_origin_city').on('change', function() {
            $('#id_origin_airport').val('').trigger('change');
        });

        $('#id_destination_city').on('change', function() {
            $('#id_destination_airport').val('').trigger('change');
        });

        // Initial load
        if ($('#id_origin_country').val()) {
            updateCityChoices('#id_origin_country', '#id_origin_city');
        }
        if ($('#id_destination_country').val()) {
            updateCityChoices('#id_destination_country', '#id_destination_city');
        }
    });
})(django.jQuery); 