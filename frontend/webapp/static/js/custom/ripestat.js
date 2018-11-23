var cachedData = {};

function fetchASNinfo(ASN){
    var data_ = [];

    if(!Number.isInteger(Number(ASN))){
        data_[0] = 'Not a valid ASN';
        data_[1] = 'None';
    }
    
    if(ASN in cachedData){
        return cachedData[ASN];
    }

    $.ajax('https://stat.ripe.net/data/as-names/data.json?resource=AS' + Number(ASN), {
        async: false,
        success: function(data){
            data_[0] = (data.data.names[Number(ASN)]);
        }
    });

    $.ajax('https://stat.ripe.net/data/geoloc/data.json?resource=AS' + Number(ASN), {
        async: false,
        success: function(data){
            var countries = new Set();
            for(var country in data.data.locations){

                if(data.data.locations[country].country.includes('-')){
                    countries.add(data.data.locations[country].country.split('-')[0]);
                }else{
                    countries.add(data.data.locations[country].country);
                }                
            }
            data_[1] = Array.from(countries).join(', ');
        }
    });

    cachedData[ASN] = data_;
    return data_;
}

function asn_map_to_name(){
    $("cc_as").mouseover(function() {
        if($(this).is("[data-toggle]")){
            return;
        }else{
            var ASN_INT = parseInt($(this).text());
            if(ASN_INT != NaN && ASN_INT > 0 && ASN_INT < 4199999999){
                var result = fetchASNinfo($(this).text());
                var html = '<p class="tooltip-custom-margin">ASN: ' + $(this).text() + ' (ASN-DOT: ' + parseInt(ASN_INT/65536) + '.' + ASN_INT%65536 + ')</br>';
                html += 'Name: ' + result[0] + '</br>';
                html += 'Countries operating: ' + result[1] +'</p>';
                $(this).prop('title', html);
                $(this).attr('data-toggle', "tooltip");
                $(this).attr('data-html', "true");
                $(this).attr('data-placement', "top");
                $(this).tooltip('show');
            }
        }
    });
    $("cc_as").mouseout(function() {
        $(this).tooltip('hide');
    });
}
