function format_datatable(data, type){ // eslint-disable-line no-unused-vars
    if(data.length > 0){
        if(hasura['extra']['type'] == "hijacks"){
            for(entry in data){
                data[entry] = format_hijack_entry(data[entry]);
            }
        }else if(hasura['extra']['type'] == "bgp_updates"){
            for(entry in data){
                data[entry] = format_bgp_update(data[entry]);
            }
        }else{
            console.error("Illegal data type. It should be 'hijacks' or 'bgp_updates'.");
        }
    }
    return data;
}

function format_hijack_entry(data){
    if('hijack_as' in data){
        data['hijack_as'] = format_hijack_as(data['hijack_as']);
    }

    if('time_detected' in data){
        data['time_detected'] = transform_date_to_local(data['time_detected']);
    }

    if('time_last' in data){
        data['time_last'] = transform_date_to_local(data['time_last']);
    }

    if('seen' in data){
        data['seen'] = format_handled_seen(data['seen']);
    }

    if('key' in data){
        data['hijack_link'] = hijack_key_create_link([data['key']]);
    }
    data['status'] = format_hijack_status(data);
    data['mark_key'] = '<input class="form-check-input" type="checkbox" value="" id="mark_' + data['key'] + '">';
    return data;
}

function format_bgp_update(data){
    if('as_path' in data){
        data['as_path'] = format_as_path(data['as_path']);
    }

    if('orig_path' in data){
        data['orig_path'] = format_orig_path(data['orig_path']);
    }

    if('timestamp' in data){
        data['timestamp'] = transform_date_to_local(data['timestamp']);
    }

    if('service' in data){
        data['service'] = format_service(data['service']);
    }

    if('origin_as' in data){
        data['origin_as'] = format_origin_as(data['origin_as']);
    }

    if('peer_asn' in data){
        data['peer_asn'] = "<cc_as>" + data['peer_asn'] + "</cc_as>";
    }

    if('communities' in data){
        data['communities'] = format_communities(data['communities']);
    }

    if('handled' in data){
        data['handled'] = format_handled_seen(data['handled']);
    }

    if('hijack_key' in data){
        data['hijack_link'] = hijack_key_create_link(data['hijack_key']);
    }
    return data;
}


function format_handled_seen(data){
    if(data){
        return '<img src="' + static_urls['handled.png'] + '" />';
    }else{
        return '<img src="' + static_urls['unhadled.png'] + '" />';
    }
}

function format_as_path(path) {
    var str_ = "";
    for (as_item in path){
        str_ += "<cc_as>" + path[as_item] + "</cc_as> ";
    }
    return str_;
}

function format_orig_path(orig_path) {
    if(orig_path == "" || orig_path == null){
        return "Same as the AS path."
    }else{
        var str_ = "";
        for (as_item in orig_path){
            str_ += "<cc_as>" + orig_path[as_item] + "</cc_as> ";
        }
        return str_;
    }
}

function transform_date_to_local(date){
    if(date != null){
        var date_ = moment.utc(date)
        if(date_._isValid){
            var local = date_.local().format('YYYY-MM-DD HH:mm:ss');
            return local;
        }
    }
    return "Never";
}

function format_hijack_status(data){
    var html_ = "";
    if(data['active'] == true){
        html_ += '<span class="badge badge-pill badge-danger">Ongoing</span>';
    }
    if(data['under_mitigation'] == true){
        html_ += '<span class="badge badge-pill badge-primary">Under Mitigation</span>';
    }
    if(data['resolved'] == true){
        html_ += '<span class="badge badge-pill badge-success">Resolved</span>';
    }
    if(data['ignored'] == true){
        html_ += '<span class="badge badge-pill badge-warning">Ignored</span>';
    }
    if(data['outdated'] == true){
        html_ += '<span class="badge badge-pill badge-dark">Outdated</span>';
    }
    if(data['withdrawn'] == true){
        html_ += '<span class="badge badge-pill badge-info">Withdrawn</span>';
    }
    if(data['dormant'] == true){
        html_ += '<span class="badge badge-pill badge-secondary">Dormant</span>';
    }
    return html_;
}

function format_service(service) {
    return "<service>" + service.replace(/\|/g, ' -> ') + "</service>";
}

function format_origin_as(n) {
    return "-1" == n || -1 == n ? "-" : "<cc_as>" + n + "</cc_as>";
}

function format_hijack_as(n) {
    return "-1" == n || -1 == n ? "Unknown" : "<cc_as>" + n + "</cc_as>";
}

function format_communities(n) {
    var t = "";
    return n.forEach(function(n) {
        t += n[0] + ":" + n[1] + ", "
    }), "[" + t.slice(0, -2) + "]"
}

function transform_unix_timestamp_to_client_local_time(n) { // eslint-disable-line no-unused-vars
    if (0 == n) return "Never";
    var t = moment.unix(n);
    return moment(t).local().format("DD-MM-YYYY HH:mm:ss")
}

function isValidDate(n) { // eslint-disable-line no-unused-vars
    return n instanceof Date && !isNaN(n)
}

function hijack_key_create_link(hijack_key){
    if(hijack_key != null){
        if(hijack_key.length == 1 && hijack_key[0] != null){
            return '<a href="' + hijack_redirect + '?key=' + hijack_key[0] + '">View</a>'
        }else if(hijack_key.length > 1){
            return '<a href="' + hijack_redirect + 's?hijack_keys=' + hijack_key + '">View</a>'
        }
    }
    return '';
}

function display_hijack_key(n) { // eslint-disable-line no-unused-vars
    return null != n && "0" != n ? n : ""
}

function display_timezone(){ // eslint-disable-line no-unused-vars
    var offset = new Date().getTimezoneOffset();
    if(offset<0)
        return "GMT+" + (offset/-60) + ' (' + Intl.DateTimeFormat().resolvedOptions().timeZone + ')';
    else
        return "GMT-" + (offset/60) + ' (' + Intl.DateTimeFormat().resolvedOptions().timeZone + ')';
}

function input_filter_prefix(value, dom){
    var match_value = null;
    var regex_match = /((^\s*((([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))(\/([0-9]|[1-2][0-9]|3[0-2]))?\s*$)|(^\s*((([0-9A-Fa-f]{1,4}:){7}([0-9A-Fa-f]{1,4}|:))|(([0-9A-Fa-f]{1,4}:){6}(:[0-9A-Fa-f]{1,4}|((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9A-Fa-f]{1,4}:){5}(((:[0-9A-Fa-f]{1,4}){1,2})|:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9A-Fa-f]{1,4}:){4}(((:[0-9A-Fa-f]{1,4}){1,3})|((:[0-9A-Fa-f]{1,4})?:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){3}(((:[0-9A-Fa-f]{1,4}){1,4})|((:[0-9A-Fa-f]{1,4}){0,2}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){2}(((:[0-9A-Fa-f]{1,4}){1,5})|((:[0-9A-Fa-f]{1,4}){0,3}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){1}(((:[0-9A-Fa-f]{1,4}){1,6})|((:[0-9A-Fa-f]{1,4}){0,4}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(:(((:[0-9A-Fa-f]{1,4}){1,7})|((:[0-9A-Fa-f]{1,4}){0,5}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:)))(%.+)?(\/([0-9]|[1-9][0-9]|1[0-1][0-9]|12[0-8]))?\s*$))/;
    if(regex_match.exec(value)){
        match_value = value.replace(/^\s+|\s+$/g, '');
        if($(dom).children("input").hasClass("is-invalid")){
            $(dom).children("input").removeClass("is-invalid");
            $(dom).children("div").hide();
        }
    }else{
        $(dom).children("input").addClass("is-invalid");
        $(dom).children("div").text('Not a valid v4/v6 prefix');
        $(dom).children("div").show();
    }
    return match_value;
}

function aggregate_status_of_modules(data, name_to_aggregate, index){ // eslint-disable-line no-unused-vars
    var status = {
        "on": 0,
        "total": 0
    }

    while(data[index].name.includes(name_to_aggregate)){
        if(data[index].running){
            status['on']++;
        }
        status['total']++;
        index++;
    }

    if(status['on'] == 0){
        return [status['on'], status['total'], "off"];
    }else if(status['on'] == status['total']){
        return [status['on'], status['total'], "on"];
    }else{
        return [status['on'], status['total'], "semi"];
    }
}

function aggregate_status_of_modules_no_index(data, name_to_aggregate){ // eslint-disable-line no-unused-vars
    var status = {
        "on": 0,
        "total": 0
    }

    for (var index = 0; index < data.length; index++){
        while(index < data.length && data[index].name.includes(name_to_aggregate)){
            if(data[index].running){
                status['on']++;
            }
            status['total']++;
            index++;
        }
    }

    if(status['on'] == 0){
        return [status['on'], status['total'], "off"];
    }else if(status['on'] == status['total']){
        return [status['on'], status['total'], "on"];
    }else{
        return [status['on'], status['total'], "semi"];
    }
}
