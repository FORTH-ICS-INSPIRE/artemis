function hijack_as_formmated(value){
	if( value == '-1' || value == -1 ){
		return 'Unknown'
	}
	return value
}

function communities_formatted(value){
	var str_ = '';
    (value).forEach(function (item) {
        str_ += item[0] + ':' + item[1] + ', ';
    })
    return '[' + (str_).slice(0,-2) + ']'
}

function transform_unix_timestamp_to_client_local_time(timestamp){
    if(timestamp != 0){
        var tunix = moment.unix(timestamp);
        return moment(tunix).local().format("DD-MM-YYYY HH:mm:ss")
    }else{
        return "Never"
    }
}

function isValidDate(d) {
  return d instanceof Date && !isNaN(d);
}

function transform_date_to_local(date){
    var date_ = moment.utc(date)
    if(date_._isValid){
        var local = date_.local().format('YYYY-MM-DD HH:mm:ss');
        return local;
    }
    return "Never";
}

function hijack_key_create_link(url, hijack_key){
    var view_hijack_link = ""
    if(null != hijack_key && hijack_key != '0' ){
        view_hijack_link = '<a href="' + url + '"?key=' + hijack_key + '">View</a>'
    }
    return view_hijack_link;
}

function display_hijack_key(hijack_key){
    if(null != hijack_key && hijack_key != '0' ){
        return hijack_key
    }else{
        return ''
    }
}