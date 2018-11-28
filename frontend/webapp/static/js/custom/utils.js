function format_hijacks_datatable(data){
    if('code' in data){ // its an error
        return {};
    }
    for(entry in data){
        data[entry] = format_hijack_entry(data[entry]);
    }
    return data;
}

function format_datatable(data){
    if('code' in data){ // its an error
        return {};
    }
    if(data.length > 0){
        if('hijack_as' in data[0]){
            for(entry in data){
                data[entry] = format_hijack_entry(data[entry]);
            }
        }else if('service' in data[0]){
            for(entry in data){
                data[entry] = format_bgp_update(data[entry]);
            }
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

function format_bgp_updates_datatable(data){
    if('code' in data){ // its an error
        return {};
    }
    for(entry in data){
        data[entry] = format_bgp_update(data[entry]);
    }
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
        return '<img src=\"' + static_urls['handled.png'] + '\" />'
    }else{
        return '<img src=\"' + static_urls['unhadled.png'] + '\" />'
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
    var date_ = moment.utc(date)
    if(date_._isValid){
        var local = date_.local().format('YYYY-MM-DD HH:mm:ss');
        return local;
    }
    return "Never";
}

function format_hijack_status(data){
    if(data['withdrawn'] == true){
        return '<b style="color:purple">Withdrawn</b>'
    }else if(data['under_mitigation'] == true){
        return '<b style="color:blue">Under Mitigation</b>'
    }else if(data['resolved'] == true){
        return '<b style="color:green">Resolved</b>'
    }else if(data['active'] == true){
        return '<b style="color:red">Ongoing</b>'
    }else if(data['ignored'] == true){
        return '<b style="color:orange">Ignored</b>'
    }else{
        return "Uknown"
    }
}

function format_service(service) {
	return service.replace(/\|/g, ' -> ');
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

function transform_unix_timestamp_to_client_local_time(n) {
    if (0 == n) return "Never";
    var t = moment.unix(n);
    return moment(t).local().format("DD-MM-YYYY HH:mm:ss")
}

function isValidDate(n) {
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

function display_hijack_key(n) {
    return null != n && "0" != n ? n : ""
}

function display_timezone(){
    var offset = new Date().getTimezoneOffset();
    if(offset<0)
        return "GMT+" + (offset/-60) + ' (' + Intl.DateTimeFormat().resolvedOptions().timeZone + ')';
    else
        return "GMT-" + (offset/60) + ' (' + Intl.DateTimeFormat().resolvedOptions().timeZone + ')';
}

