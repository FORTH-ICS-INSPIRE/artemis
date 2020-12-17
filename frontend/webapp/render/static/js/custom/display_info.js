var mapHelpText_stats = {};
mapHelpText_stats['field_autoignore'] = 'Backend microservice that automatically ignores hijack alerts of low impact and/or visibility based on user configuration.';
mapHelpText_stats['field_autostarter'] = 'Backend microservice that automatically checks the health of the backend and monitor (taps) microservices and activates them via their REST interface in case they are down.';
mapHelpText_stats['field_configuration'] = 'Backend microservice that configures the rest of the microservices using the configuration file.';
mapHelpText_stats['field_database'] = 'Backend microservice that provides database access and management (stores BGP updates, hijacks and other persistent information in Postgres).';
mapHelpText_stats['field_detection'] = 'User-controllable backend microservice that detects BGP hijacks in real-time.';
mapHelpText_stats['field_fileobserver'] = 'Backend microservice that detects content changes in the configuration file and notifies configuration.';
mapHelpText_stats['field_mitigation'] = 'Backend microservice that triggers custom mitigation mechanisms when the user instructs it.';
mapHelpText_stats['field_notifier'] = 'Backend microservice that sends BGP hijack alerts to different logging endpoints, according to user configuration.';
mapHelpText_stats['field_prefixtree'] = 'Backend microservice that holds the configuration prefix tree (prefixes bundled with ARTEMIS rules) in-memory for quick lookups.';
mapHelpText_stats['field_riperistap'] = 'Monitor/tap microservice that collects real-time BGP update information from RIPE RIS live.';
mapHelpText_stats['field_bgpstreamlivetap'] = 'Monitor/tap microservice that collects real-time BGP update information from RIPE RIS RIB collections, RouteViews RIB collections and Public CAIDA BMP feeds.';
mapHelpText_stats['field_bgpstreamkafkatap'] = 'Monitor/tap microservice that collects real-time BGP update information via Kafka from public and private BMP feeds.';
mapHelpText_stats['field_bgpstreamhisttap'] = 'Monitor/tap microservice that replays historical BGP updates.';
mapHelpText_stats['field_exabgptap'] = 'Monitor/tap microservice that collects real-time BGP update information from local BGP feeds via exaBGP.';

mapHelpText_stats['field_stats_configured_prefixes'] = 'The total number of IPv4/IPv6 prefixes that are configured (as appearing in ARTEMIS rules).';
mapHelpText_stats['field_stats_monitored_prefixes'] = 'The total number of IPv4/IPv6 prefixes that are actually monitored (super-prefixes include sub-prefixes).';
mapHelpText_stats['field_stats_monitor_peers'] = 'The total number of monitors (ASNs) that peer with routing collector services, as observed by the system.';
mapHelpText_stats['field_stats_total_bgp_updates'] = 'The total number of BGP updates seen on the monitors.';
mapHelpText_stats['field_stats_total_unhandled_updates'] = 'The total number of BGP updates not processed by the detection (either because they are in the queue, or because the detection was not running when they were fed to the monitors).';
mapHelpText_stats['field_stats_total_hijacks'] = 'The total number of hijack events stored in the system.';
mapHelpText_stats['field_stats_resolved_hijacks'] = 'The number of resolved hijack events (that were marked by the user).';
mapHelpText_stats['field_stats_mitigation_hijacks'] = 'The number of hijack events that are currently under mitigation (triggered by the user).';
mapHelpText_stats['field_stats_ongoing_hijacks'] = 'The number of ongoing hijack events (not ignored or resolved or withdrawn or outdated).';
mapHelpText_stats['field_stats_ignored_hijacks'] = 'The number of ignored hijack events (that were marked by the user).';
mapHelpText_stats['field_stats_withdrawn_hijacks'] = 'The number of withdrawn hijack events.';
mapHelpText_stats['field_stats_acknowledged_hijacks'] = 'The number of acknowledged hijack events (confirmed as true positives).';
mapHelpText_stats['field_stats_outdated_hijacks'] = 'The number of hijack events that are currently outdated (matching deprecated configurations, but benign now).';
mapHelpText_stats['field_stats_dormant_hijacks'] = 'The number of dormant hijack events (ongoing, but not updated within the last X hours).';

var mapHelpText_system = {};
mapHelpText_system['field_time_detected'] = 'The time when a hijack event was </br> first detected by the system.';

mapHelpText_system['field_hijack_status'] = `The status of a hijack event (possible values: ongoing|dormant|withdrawn|under mitigation|ignored|resolved|outdated).</br>
<ul><li>Ongoing: the hijack has not been ignored, resolved or withdrawn.</li>
<li>Dormant: the hijack is ongoing, but not updated within the last X hours.</li>
<li>Withdrawn: all monitors that saw hijack updates for a certain hijacked prefix have seen the respective withdrawals.</li>
<li>Ignored: the event is ignored (by the user).</li>
<li>Resolved: the event is resolved (by the user).</li>
<li>Outdated: the event was triggered by a configuration that is now deprecated.</li></ul>`;

mapHelpText_system['field_hijack_type'] = `The type of the hijack in 4 dimensions: prefix|path|data plane|policy<ul>
<li>[Prefix] "S" → Sub-prefix hijack</li>
<li>[Prefix] "E" → Exact-prefix hijack</li>
<li>[Prefix] "Q" → Squatting hijack</li>
<li>[Path] "0" → Type-0 hijack</li>
<li>[Path] "1" → Type-1 hijack</li>
<li>[Path] "P" → Type-P hijack</li>
<li>[Path] "-" → Type-N or Type-U hijack (N/A)</li>
<li>[Data plane] "-" → Blackholing, Imposture or MitM hijack (N/A)</li>
<li>[Policy] "L" → Route Leak due to no-export policy violation</li>
<li>[Policy] "-" → Other policy violation (N/A)</li></ul>`;

mapHelpText_system['field_hijacker_as'] = 'The AS that is potentially responsible for the hijack.</br>Note that this is an experimental field.';
mapHelpText_system['field_peers_seen'] = 'Number of peers/monitors (i.e., ASNs)</br>that have seen hijack updates.';
mapHelpText_system['field_ases_infected'] = 'Number of infected ASes that seem to</br>route traffic towards the hijacker AS.</br>Note that this is an experimental field.';
mapHelpText_system['field_hijack_ack'] = 'Whether the user has acknowledged/confirmed the hijack as a true positive.<br>If the resolve|mitigate buttons are pressed this<br>is automatically set to True (default value: False).';
mapHelpText_system['field_hijack_more'] = 'Further information related to the hijack.';

mapHelpText_system['field_service'] = 'The route collector service that is connected to the monitor AS that observed the BGP update.';
mapHelpText_system['field_bgp_update_type'] = "<ul><li>A → route announcement</li><li>W → route withdrawal</li></ul>";
mapHelpText_system['field_bgp_update_more'] = "Further information related to the BGP update.";
mapHelpText_system['field_peer_as'] = "The monitor AS that peers with the route collector service reporting the BGP update.";
mapHelpText_system['field_bgp_timestamp'] = "The time when the BGP update was generated, as set by the BGP monitor or route collector.";
mapHelpText_system['field_prefix'] = "The IPv4/IPv6 prefix related to the BGP update.";
mapHelpText_system['field_hijacked_prefix'] = "The IPv4/IPv6 prefix that was hijacked.";
mapHelpText_system['field_matched_prefix'] = "The configured IPv4/IPv6 prefix that matched the hijacked prefix.";

mapHelpText_system['field_as_path'] = "The AS-level path of the update.";
mapHelpText_system['field_origin_as'] = "The AS that originated the BGP update.";
mapHelpText_system['field_bgp_handle'] = "Whether the BGP update has been handled by the detection module or not.";

mapHelpText_system['field_aux_path_info'] = "Auxiliary path information on the update/withdrawal. For updates, this is different from the reported AS-PATH only in the case of AS-SETs, sequences, etc. where the monitor decomposes a single update into many for ease of interpretation. For (implicit) withdrawals, it contains the original triggering BGP update information in json format.";
mapHelpText_system['field_bgp_communities'] = "BGP communities related to the BGP update.";
mapHelpText_system['field_hijack_key'] = "The unique key of a hijack event.";

mapHelpText_system['field_matched_prefix_hijack'] = "The prefix that was matched in the configuration (note: this might differ from the actually hijacked prefix in the case of a sub-prefix hijack).";
mapHelpText_system['field_config'] = "The timestamp (i.e., unique ID) of the configuration based on which this hijack event was triggered.";
mapHelpText_system['field_time_started'] = "The timestamp of the oldest known (to the system) BGP update that is related to the hijack.";
mapHelpText_system['field_time_detected'] = "The time when a hijack event was first detected by the system.";
mapHelpText_system['field_time_last_update'] = "The timestamp of the newest known (to the system) BGP update that is related to the hijack.";
mapHelpText_system['field_community_annotation'] = "The user-defined annotation of the hijack according to the communities of hijacked BGP updates.";
mapHelpText_system['field_rpki_status'] = `The RPKI status of the hijacked prefix.<ul>
<li>"NA" → Non Applicable</li>
<li>"VD" → Valid</li>
<li>"IA" → Invalid ASN</li>
<li>"IL" → Invalid Prefix Length</li>
<li>"IU" → Invalid Unknown</li>
<li>"NF" → Not found</li></ul>`;

mapHelpText_system['field_time_ended'] = `The timestamp when the hijack was ended. It can be set in the following ways:
<ul><li>Manually, when the user presses the “resolved” button.</li>
<li>Automatically, when a hijack is completely withdrawn (all monitors that saw hijack updates for a certain prefix have seen the respective withdrawals).</li></ul>`;

mapHelpText_system['field_mitigation_started'] = "The timestamp when the mitigation was triggered by the user (“mitigate” button).";
mapHelpText_system['field_time_window_custom'] = "The time window for seeing BGP updates or hijack events.";
mapHelpText_system['field_view_hijack'] = "Redirects to the hijack view if the BGP update is not benign, otherwise empty.";


var mapHelpText_hijack_status = {};
mapHelpText_hijack_status['field_hijack_status_resolved'] = 'Resolved hijack events</br>(marked by the user).';
mapHelpText_hijack_status['field_hijack_status_ongoing'] = 'Ongoing hijack events</br>(not ignored or resolved).';
mapHelpText_hijack_status['field_hijack_status_withdrawn'] = 'Withdrawn hijack events</br>(marked automatically).';
mapHelpText_hijack_status['field_hijack_status_ignored'] = 'Ignored hijack events</br>(marked by the user).';
mapHelpText_hijack_status['field_hijack_under_mitigation'] = 'Hijack events that are currently under mitigation</br>(triggered by the user).';
mapHelpText_hijack_status['field_hijack_status_outdated'] = 'Hijack events that match a configuration that is now deprecated</br>(marked by the user).';
mapHelpText_hijack_status['field_hijack_status_dormant'] = 'Dormant hijack events</br>(ongoing, but not updated within the last X hours).';


function displayHelpTextTable(){ // eslint-disable-line no-unused-vars
	$('th[helpText]').each(function() {
		var value = '<p class="tooltip-custom-margin">' + mapHelpText_system[$(this).attr( "helpText" )]  + '</p>'
		$(this).prop('title', value);
		$(this).attr('data-toggle', "tooltip");
		$(this).attr('data-placement', "top");
		$(this).tooltip({html:true})
	});
}

function displayHelpTextB(){ // eslint-disable-line no-unused-vars
	$('b[helpText]').each(function() {
		var value = '<p class="tooltip-custom-margin">' + mapHelpText_system[$(this).attr( "helpText" )]  + '</p>'
		$(this).prop('title', value);
		$(this).attr('data-toggle', "tooltip");
		$(this).attr('data-placement', "top");
		$(this).tooltip({html:true})
	});
}

function displayHelpTextButton(){ // eslint-disable-line no-unused-vars
	$('button[helpText]').each(function() {
		if($(this).attr( "helpText" ) in mapHelpText_hijack_status){
			var value = '<p class="tooltip-custom-margin">' + mapHelpText_hijack_status[$(this).attr( "helpText" )]  + '</p>'
		}else{
			var value = '<p class="tooltip-custom-margin">' + mapHelpText_system[$(this).attr( "helpText" )]  + '</p>'
		}
		$(this).prop('title', value);
		$(this).attr('data-toggle', "tooltip");
		$(this).attr('data-placement', "top");
		$(this).tooltip({html:true})
	});
}

function displayHelpTextStats(){ // eslint-disable-line no-unused-vars
	$('div[helpText]').each(function() {
		var value = '<p class="tooltip-custom-margin">' + mapHelpText_stats[$(this).attr( "helpText" )]  + '</p>'
		$(this).prop('title', value);
		$(this).attr('data-toggle', "tooltip");
		$(this).attr('data-placement', "top");
		$(this).tooltip({html:true})
	});
}

function displayHelpMoreBGPupdate(){ // eslint-disable-line no-unused-vars
	$('td[helpText]').each(function() {
        var value = '<p class="tooltip-custom-margin">' + mapHelpText_system[$(this).attr( "helpText" )]  + '</p>'
        $(this).prop('title', value);
        $(this).attr('data-toggle', "tooltip");
        $(this).attr('data-html', "true");
        $(this).attr('data-placement', "top");
        $(this).tooltip()
    });
}

var services_map = null;

function get_services_mapping(){
    return fetch(static_urls['rrcs_location']
        ).then(response => response.json()
        ).then(data => services_map = data
        ).catch(err => console.log(err));
}

function service_to_name(){ // eslint-disable-line no-unused-vars
	if(services_map == null){
		get_services_mapping();
	}

	$("service").mouseover(function() {
		if($(this).children().length > 0){
            var Monitor_str = $(this).children(":first").val();
        }else{
            var Monitor_str = $(this).text();
        }

		var collector_info = "Unknown";
		var list_;
		if(Monitor_str.includes('->')){
			list_ = Monitor_str.split('-> ');
		}else if(Monitor_str.includes('|')){
			list_ = Monitor_str.split('|');
		}

		var collector_name = list_[list_.length - 1];
		if(collector_name in services_map){
			if(collector_name.includes('route-views')){
				collector_info = "Name: " + collector_name + "</br>"
				collector_info += "MFG: " + services_map[collector_name].MFG + "</br>"
				collector_info += "BGP_proto: " + services_map[collector_name].BGP_proto + "</br>"
				collector_info += "Location: " + services_map[collector_name].location + "</br>"
			}else{
				collector_info = "Name: " + collector_name + "</br>";
				collector_info += "Information: " + services_map[collector_name].info;
			}
		}

		var value = '<p class="tooltip-custom-margin">' + collector_info + '</p>';
        $(this).prop('title', value);
        $(this).attr('data-toggle', "tooltip");
        $(this).attr('data-html', "true");
        $(this).attr('data-placement', "top");
        $(this).tooltip('show')
	});

    $("service").mouseout(function() {
        $(this).attr('mouse_hovered', 'false');
        $(this).tooltip('hide');
    });
}
