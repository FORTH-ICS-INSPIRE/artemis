function hijack_as_formmated(value){
	if( value == '-1' || value == -1 ){
		return 'Unknown'
	}
	return value
}

function communities_formmated(value){
	var str_ = '[';
    (value).forEach(function (item) {
    	console.log(value);
        str_ += item[0] + ':' + item[1] + ', ';
    })
    return (str_).slice(0,-2) + ']'
}

function transform_unix_timestamp_to_client_local_time(timestamp){
    if(timestamp != 0){
        var tunix = moment.unix(timestamp);
        return moment(tunix).local().format("DD-MM-YYYY HH:mm:ss")
    }else{
        return "Never"
    }
}