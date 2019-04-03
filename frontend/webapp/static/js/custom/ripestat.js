var cachedData = {};

function getName(ASN){
  return fetch('https://stat.ripe.net/data/as-names/data.json?resource=AS' + ASN).then((response) => response.json())
}

function getCountry(ASN){
  return fetch('https://stat.ripe.net/data/geoloc/data.json?resource=AS' + ASN).then((response) => response.json())
}

function getAbuse(ASN){
    return fetch('https://stat.ripe.net/data/abuse-contact-finder/data.json?resource=AS' + ASN).then((response) => response.json())
}

function getData(ASN){
  return Promise.all([getName(ASN), getCountry(ASN), getAbuse(ASN)]);
}

function asn_map_to_name(){ // eslint-disable-line no-unused-vars
    $("cc_as").mouseover(function() {
        // For some browsers, `attr` is undefined; for others,
        // `attr` is false.  Check for both.
        var where = $(this).attr('where');
        var align_of_tooltip = "top";
        if (typeof where !== typeof undefined && where !== false) {
            align_of_tooltip = where;
        }
        $(this).attr('mouse_hovered', 'true');
        if($(this).is("[data-toggle]")){
            return;
        }else{
            if($(this).children().length > 0){
                var ASN_str = $(this).children(":first").val();
            }else{
                var ASN_str = $(this).text();
            }
            var ASN_int = parseInt(ASN_str);

            if(ASN_str in cachedData){
                $(this).prop('title', cachedData[ASN_str]['html']);
                if(cachedData[ASN_str]['copy_text'] != undefined){
                    $(this).attr('text_copy', cachedData[ASN_str]['copy_text']);
                }
                $(this).attr('data-toggle', "tooltip");
                $(this).attr('data-html', "true");
                $(this).attr('data-placement', align_of_tooltip);
                $(this).tooltip('show');
            }else{
                var data_ = {};

                if(!isNaN(ASN_int) && ASN_int > 0 && ASN_int < 4294967295){
                    getData(ASN_int)
                        .then(([name, countries, abuse]) => {
                        // get_name
                        data_['name'] = (name.data.names[ASN_int]);

                        var countries_set = new Set();
                        for(var country in countries.data.locations){
                            if(countries.data.locations[country].country.includes('-')){
                                countries_set.add(countries.data.locations[country].country.split('-')[0]);
                            }else{
                                countries_set.add(countries.data.locations[country].country);
                            }
                        }
                        data_['countries'] = Array.from(countries_set).join(', ');
                        data_['asn_dot'] = parseInt(ASN_int/65536) + '.' + ASN_int%65536;

                        if((ASN_int >= 64512 && ASN_int <= 65534) || (ASN_int >= 4200000000 && ASN_int <= 4294967294)){
                            data_['type'] = 'Private';
                        }else{
                            data_['type'] = 'Non-Private';
                        }

                        var abuse_html = [];
                        var abuse_text = [];
                        if(abuse.data.authorities.length > 0){
                            let authorities = [];
                            for(var authority in abuse.data.authorities){
                                authorities.push(abuse.data.authorities[authority]);
                            }
                            if(authorities != ""){
                                abuse_html.push('Authorities: ');
                                abuse_text.push('Authorities: ');

                                abuse_html.push(authorities.join());
                                abuse_text.push(authorities.join());

                                abuse_html.push('</br>');
                                abuse_text.push('\n');
                            }
                        }

                        if(abuse.data.anti_abuse_contacts.abuse_c.length > 0){
                            let anti_abuse_contacts_abuse_c_html = [];
                            let anti_abuse_contacts_abuse_c_text = [];
                            for(var item in abuse.data.anti_abuse_contacts.abuse_c){
                                let abuse_c_html = [];
                                let abuse_c_text = [];
                                abuse_c_html.push('Description: ');
                                abuse_c_text.push('Description: ');

                                abuse_c_html.push(abuse.data.anti_abuse_contacts.abuse_c[item].description);
                                abuse_c_text.push(abuse.data.anti_abuse_contacts.abuse_c[item].description);

                                abuse_c_html.push('</br>Key: ');
                                abuse_c_text.push('\nKey: ');

                                abuse_c_html.push(abuse.data.anti_abuse_contacts.abuse_c[item].key);
                                abuse_c_text.push(abuse.data.anti_abuse_contacts.abuse_c[item].key);

                                abuse_c_html.push('</br>Email: ');
                                abuse_c_text.push('\nEmail: ');

                                abuse_c_html.push(abuse.data.anti_abuse_contacts.abuse_c[item].email);
                                abuse_c_text.push(abuse.data.anti_abuse_contacts.abuse_c[item].email);

                                abuse_c_html.push('</br>');
                                abuse_c_text.push('\n');

                                anti_abuse_contacts_abuse_c_html.push(abuse_c_html.join(''));
                                anti_abuse_contacts_abuse_c_text.push(abuse_c_text.join(''))
                            }
                            if(anti_abuse_contacts_abuse_c_html.length > 0){
                                for(var entry in anti_abuse_contacts_abuse_c_html){
                                    abuse_html.push(anti_abuse_contacts_abuse_c_html[entry]);
                                    abuse_text.push(anti_abuse_contacts_abuse_c_text[entry])

                                    abuse_html.push('</br>');
                                    abuse_text.push('\n');
                                }
                            }
                        }
                        data_['abuse_html'] = abuse_html.join('');
                        data_['abuse_text'] = abuse_text.join('');

                        var html = [];
                        var text_formatted = [];
                        html.push('<p class="tooltip-custom-margin">ASN: ');
                        text_formatted.push('ASN: ');

                        html.push(ASN_str);
                        text_formatted.push(ASN_str);

                        html.push(' (ASN-DOT: ');
                        text_formatted.push(' (ASN-DOT: ');

                        html.push(data_['asn_dot']);
                        text_formatted.push(data_['asn_dot']);

                        html.push('</br>');
                        text_formatted.push('\n');

                        html.push('Name: ');
                        text_formatted.push('Name: ');

                        html.push(data_['name']);
                        text_formatted.push(data_['name']);

                        html.push('<br>Type: ');
                        text_formatted.push('\nType: ');

                        html.push(data_['type']);
                        text_formatted.push(data_['type']);

                        html.push('</br>Countries operating: ');
                        text_formatted.push('\nCountries operating: ');

                        html.push(data_['countries']);
                        text_formatted.push(data_['countries']);

                        html.push('<br></br>Abuse Contact Details: </br>');
                        text_formatted.push('\n\nAbuse Contact Details: \n');

                        html.push(data_['abuse_html']);
                        text_formatted.push(data_['abuse_text']);

                        html.push('<small>(Click on AS number to copy on clickboard)</small>');
                        html.push('</p>');

                        cachedData[ASN_str] = {};

                        var join_html = html.join('');
                        cachedData[ASN_str]['html'] = join_html;
                        var join_text = text_formatted.join('');
                        cachedData[ASN_str]['text_copy'] = join_text;

                        $(this).prop('title', join_html);
                        $(this).attr('text_copy', join_text);
                        $(this).attr('data-toggle', "tooltip");
                        $(this).attr('data-html', "true");
                        $(this).attr('data-placement', align_of_tooltip);
                        if($(this).attr("mouse_hovered") === 'true'){
                            $(this).tooltip('show');
                        }else{
                            $(this).tooltip();
                        }
                   });

                }else{
                    data_['name'] = 'Not a valid ASN';
                    data_['countries'] = 'None';
                    data_['asn_dot'] = 'None';
                    data_['type'] = 'Unknown'
                    data_['abuse'] = 'Unknown';

                    var html = [];
                    html.push('<p class="tooltip-custom-margin">ASN: ');
                    html.push(ASN_str);
                    html.push(' (ASN-DOT: ');
                    html.push(data_['asn_dot']);
                    html.push('</br>');
                    html.push('Name: ');
                    html.push(data_['name']);
                    html.push('</br>');
                    html.push('type: ');
                    html.push(data_['type']);
                    html.push('</br>');
                    html.push('Countries operating: ');
                    html.push(data_['countries']);
                    html.push('<br></br>Abuse Contact Details: </br>');
                    html.push(data_['abuse']);
                    html.push('</p>');

                    var join_html = html.join('');
                    cachedData[ASN_str] = join_html;

                    $(this).prop('title', join_html);
                    $(this).attr('data-toggle', "tooltip");
                    $(this).attr('data-html', "true");
                    $(this).attr('data-placement', align_of_tooltip);
                    $(this).tooltip('show');
                }
            }
        }
    });

    $("cc_as").mouseout(function() {
        $(this).attr('mouse_hovered', 'false');
        $(this).tooltip('hide');
        $('.tooltip').tooltip('hide');
    });

    $('cc_as').click(function() {
        if($(this).first().attr('text_copy') != undefined){
            var dt = new clipboard.DT();
            dt.setData("text/plain", $(this).first().attr('text_copy'));
            clipboard.write(dt);
        }
    });
}
