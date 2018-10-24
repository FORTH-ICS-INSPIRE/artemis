function format_as_path(path) {
	var str_ = "";
	for (as_item in path){
		str_ += path[as_item] + " ";
	}
	return str_;
}

function format_orig_path(orig_path) {
	if(orig_path == "" || orig_path == null){
		return "Same as the AS path."
	}else{
		var str_ = "";
		for (as_item in orig_path){
			str_ += orig_path[as_item] + " ";
		}
		return str_;
	}
}

function transform_date_to_local(date){
    var date_ = moment.utc(date)
    if(date_._isValid){
        var local = date_.local().format('YYYY-MM-DD HH:mm:ss Z');
        return local;
    }
    return "Never";
}

function format_service(service) {
	return service.replace(/\|/g, ' -> ');
}

function hijack_as_formmated(n) {
    return "-1" == n || -1 == n ? "Unknown" : n
}

function communities_formatted(n) {
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

function hijack_key_create_link(n, t) {
    var e = "";
    return null != t && "0" != t && (e = '<a href="' + n + "?key=" + t + '">View</a>'), e
}

function display_hijack_key(n) {
    return null != n && "0" != n ? n : ""
}