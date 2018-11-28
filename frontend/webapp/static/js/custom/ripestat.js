var cachedData = {};

function getName(ASN){
  return fetch('https://stat.ripe.net/data/as-names/data.json?resource=AS' + ASN).then((response) => response.json())
}

function getCountry(ASN){
  return fetch('https://stat.ripe.net/data/geoloc/data.json?resource=AS' + ASN).then((response) => response.json())
}

function getData(ASN){
  return Promise.all([getName(ASN), getCountry(ASN)]);
}

function asn_map_to_name(){
    $("cc_as").mouseover(function() {
        $(this).attr('mouse_hovered', 'true');
        if($(this).is("[data-toggle]")){
            return;
        }else{
            var ASN_int = parseInt($(this).text());
            var ASN_str = $(this).text();
            var result = null;

            if(ASN_str in cachedData){
                var html = '<p class="tooltip-custom-margin">ASN: ' + ASN_str + ' (ASN-DOT: ' + cachedData[ASN_str][2] + ')</br>';
                html += 'Name: ' + cachedData[ASN_str][0] + '</br>';
                html += 'Countries operating: ' + cachedData[ASN_str][1] +'</p>';
                $(this).prop('title', html);
                $(this).attr('data-toggle', "tooltip");
                $(this).attr('data-html', "true");
                $(this).attr('data-placement', "top");
                $(this).tooltip('show');

            }else{
                var data_ = [];

                if(ASN_int != NaN && ASN_int > 0 && ASN_int < 4199999999){
                    getData(ASN_int)
                        .then(([name, countries]) => {
                        data_[0] = (name.data.names[ASN_int]);
                        var countries_set = new Set();
                        for(var country in countries.data.locations){
                            if(countries.data.locations[country].country.includes('-')){
                                countries_set.add(countries.data.locations[country].country.split('-')[0]);
                            }else{
                                countries_set.add(countries.data.locations[country].country);
                            }
                        }
                        data_[1] = Array.from(countries_set).join(', ');
                        data_[2] = parseInt(ASN_int/65536) + '.' + ASN_int%65536;
                        cachedData[ASN_str] = data_;

                        var html = '<p class="tooltip-custom-margin">ASN: ' + $(this).text() + ' (ASN-DOT: ' + cachedData[ASN_str][2] + ')</br>';
                        html += 'Name: ' + cachedData[ASN_str][0] + '</br>';
                        html += 'Countries operating: ' + cachedData[ASN_str][1] +'</p>';
                        $(this).prop('title', html);
                        $(this).attr('data-toggle', "tooltip");
                        $(this).attr('data-html', "true");
                        $(this).attr('data-placement', "top");
                        if($(this).attr("mouse_hovered") === 'true'){
                            $(this).tooltip('show');
                        }else{
                            $(this).tooltip();
                        }
                   });

                }else{
                    data_[0] = 'Not a valid ASN';
                    data_[1] = 'None';
                    data_[2] = "None";
                    cachedData[ASN_str] = data_;

                    var html = '<p class="tooltip-custom-margin">ASN: ' + $(this).text() + ' (ASN-DOT: ' + cachedData[ASN_str][2] + ' )</br>';
                    html += 'Name: ' + cachedData[ASN_str][0] + '</br>';
                    html += 'Countries operating: ' + cachedData[ASN_str][1] +'</p>';
                    $(this).prop('title', html);
                    $(this).attr('data-toggle', "tooltip");
                    $(this).attr('data-html', "true");
                    $(this).attr('data-placement', "top");
                    $(this).tooltip('show');
                }
            }
        }
    });

    $("cc_as").mouseout(function() {
        $(this).attr('mouse_hovered', 'false');
        $(this).tooltip('hide');
    });
}
