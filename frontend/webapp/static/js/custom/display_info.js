

var mapHelpText_stats = {};
mapHelpText_stats['field_clock'] = 'ARTEMIS module serving as the clock signal generator for periodic tasks done in other modules (e.g., postgresql_db).';
mapHelpText_stats['field_configuration'] = 'ARTEMIS module responsible for the configuration of the other ARTEMIS modules.';
mapHelpText_stats['field_detection'] = 'ARTEMIS module responsible for the detection of hijack events (current support for exact-prefix Type-0/1, any type of sub-prefix hijacks, and squatting attacks).';
mapHelpText_stats['field_mitigation'] = 'ARTEMIS module responsible for the manual or automated mitigation of hijack events (current support for manual mitigation or via the invocation of a custom operator-supplied script).';
mapHelpText_stats['field_monitor'] = 'ARTEMIS module responsible for real-time monitoring of BGP updates appearing on the visible control plane of public and local BGP monitors (current support for RIPE RIS, BGPStream RouteViews, RIPE RIS and beta BMP, local exaBGP monitors, historical trace replay).';
mapHelpText_stats['field_observer'] = 'ARTEMIS module responsible for observing async changes in the configuration file, triggering the reloading of ARTEMIS modules.';
mapHelpText_stats['field_postgresql_db'] = 'ARTEMIS module responsible for providing access to the Postgres DB used in the core of ARTEMIS for persistent storage of configuration, BGP update and BGP prefix hijack event data.';

mapHelpText_stats['field_stats_Total_BGP_Updates'] = 'The total number of BGP updates seen on the monitors.';
mapHelpText_stats['field_stats_Total_Unhandled_Updates'] = 'The total number of BGP updates not processed by the detection (either because they are in the queue, or because the detection was not running when they were fed to the monitors).';
mapHelpText_stats['field_stats_Total_Hijacks'] = 'The total number of hijack events stored in the system.';
mapHelpText_stats['field_stats_Resolved_Hijacks'] = 'The number of resolved hijack events (true positives that were marked by the user).';
mapHelpText_stats['field_stats_Mitigation_Hijacks'] = 'The number of hijack events that are currently under mitigation (triggered by the user).';
mapHelpText_stats['field_stats_Ongoing_Hijacks'] = 'The number of ongoing hijack events (not ignored or resolved or withdrawn or outdated).';
mapHelpText_stats['field_stats_Ignored_Hijacks'] = 'The number of ignored hijack events (false positives that were marked by the user)';
mapHelpText_stats['field_stats_Withdrawn_Hijacks'] = 'The number of withdrawn hijack events.';
mapHelpText_stats['field_stats_Seen_Hijacks'] = 'The number of acknowledged/seen hijack events.';
mapHelpText_stats['field_stats_Outdated_Hijacks'] = 'The number of hijack events that are currently outdated.';

var mapHelpText_system = {};
mapHelpText_system['field_time_detected'] = 'The time when a hijack event was </br> first detected by the system.';

mapHelpText_system['field_hijack_status'] = 'The status of a hijack event (possible values: ongoing|withdrawn|under mitigation|ignored|resolved|outdated).</br>';
mapHelpText_system['field_hijack_status'] += '<ul><li>Ongoing: the hijack has not been ignored, resolved or withdrawn.</li>';
mapHelpText_system['field_hijack_status'] += '<li>Withdrawn: all monitors that saw hijack updates for a certain prefix have seen the respective withdrawals.</li>';
mapHelpText_system['field_hijack_status'] += '<li>Ignored: the event was a false positive alert.</li>';
mapHelpText_system['field_hijack_status'] += '<li>Resolved: the event was a true positive that is now resolved.</li>';
mapHelpText_system['field_hijack_status'] += '<li>Outdated: the event was triggered by a configuration that is now deprecated.</li></ul>';

mapHelpText_system['field_hijack_type'] = 'The type of the hijack:<ul>';
mapHelpText_system['field_hijack_type'] += '<li>S → Sub-prefix hijack</li>';
mapHelpText_system['field_hijack_type'] += '<li>0 → Type-0 exact-prefix hijack</li>';
mapHelpText_system['field_hijack_type'] += '<li>1 → Type-1 exact-prefix hijack</li>';
mapHelpText_system['field_hijack_type'] += '<li>Q → Squatting attack </li></ul>';

mapHelpText_system['field_hijack_as'] = 'The possible AS that is responsible the hijack.</br>Note that this is an experimental field.';
mapHelpText_system['field_peers_seen'] = 'Number of peers/monitors (i.e., ASNs)</br>that have seen hijack updates.';
mapHelpText_system['field_ases_infected'] = 'Number of infected ASes that seem to</br>route traffic towards the hijacker AS.</br>Note that this is an experimental field.';
mapHelpText_system['field_hijack_seen'] = 'Whether the user has acknowledged seeing the hijack.<br>If the ignore|resolve|mitigate buttons are pressed this<br>is automatically set to True (default value: False).';
mapHelpText_system['field_hijack_more'] = 'Further information related to the hijack.';

mapHelpText_system['field_service'] = 'The route collector service that is connected to the monitor AS that observed the BGP update.';
mapHelpText_system['field_bgp_update_type'] = "<ul><li>A → route announcement</li><li>W → route withdrawal</li></ul>";
mapHelpText_system['field_bgp_update_more'] = "Further information related to the BGP update.";
mapHelpText_system['field_peer_as'] = "The monitor AS that peers with the route collector service reporting the BGP update.";
mapHelpText_system['field_bgp_timestamp'] = "The time when the BGP update was generated, as set by the BGP monitor or route collector.";
mapHelpText_system['field_prefix'] = "The IPv4/IPv6 prefix related to the BGP update or hijack.";
mapHelpText_system['field_as_path'] = "The AS-level path of the update.";
mapHelpText_system['field_origin_as'] = "The AS that originated the BGP update.";
mapHelpText_system['field_bgp_handle'] = "Whether the BGP update has been handled by the detection module or not.";

mapHelpText_system['field_original_path'] = "The original path of the update. This is different from the reported AS-PATH only in the case of AS-SETs, sequences, etc. where the monitor decomposes a single update into many for ease of interpretation.";
mapHelpText_system['field_bgp_communities'] = "BGP communities related to the BGP update.";
mapHelpText_system['field_hijack_key'] = "The unique key of a hijack event.";

mapHelpText_system['field_matched_prefix_hijack'] = "The prefix that was matched in the configuration (note: this might differ from the actually hijacked prefix in the case of a sub-prefix hijack).";
mapHelpText_system['field_config'] = "The timestamp (i.e., unique ID) of the configuration based on which this hijack event was triggered.";
mapHelpText_system['field_time_started'] = "The timestamp of the oldest known (to the system) BGP update that is related to the hijack.";
mapHelpText_system['field_time_detected'] = "The time when a hijack event was first detected by the system.";
mapHelpText_system['field_time_last_update'] = "The timestamp of the newest known (to the system) BGP update that is related to the hijack.";

mapHelpText_system['field_time_ended'] = "The timestamp when the hijack was ended. It can be set in the following ways:";
mapHelpText_system['field_time_ended'] += "<ul><li>Manually, when the user presses the “resolved” button.</li>";
mapHelpText_system['field_time_ended'] += "<li>Automatically, when a hijack is completely withdrawn (all monitors that saw hijack updates for a certain prefix have seen the respective withdrawals).</li></ul>";

mapHelpText_system['field_mitigation_started'] = "The timestamp when the mitigation was triggered by the user (“mitigate” button).";
mapHelpText_system['field_time_window_custom'] = "The time window for seeing BGP updates or hijack events.";
mapHelpText_system['field_view_hijack'] = "Redirects to the hijack view if the BGP update is not benign, otherwise empty.";


var mapHelpText_hijack_status = {};
mapHelpText_hijack_status['field_hijack_status_resolved'] = 'Resolved hijack events</br>(true positives that were marked by the user).';
mapHelpText_hijack_status['field_hijack_status_ongoing'] = 'Ongoing hijack events</br>(not ignored or resolved).';
mapHelpText_hijack_status['field_hijack_status_withdrawn'] = 'Withdrawn hijack events.';
mapHelpText_hijack_status['field_hijack_status_ignored'] = 'Ignored hijack events</br>(false positives that were marked by the user).';
mapHelpText_hijack_status['field_hijack_under_mitigation'] = 'Hijack events that are currently under mitigation</br>(triggered by the user).';
mapHelpText_hijack_status['field_hijack_status_outdated'] = 'Hijack events that match a configuration that is now deprecated.';


function displayHelpTextTable(){
	$('th[helpText]').each(function( index ) {
		var value = '<p class="tooltip-custom-margin">' + mapHelpText_system[$(this).attr( "helpText" )]  + '</p>'
		$(this).prop('title', value);
		$(this).attr('data-toggle', "tooltip");
		$(this).attr('data-placement', "top");
		$(this).tooltip({html:true})
	});
}

function displayHelpTextB(){
	$('b[helpText]').each(function( index ) {
		var value = '<p class="tooltip-custom-margin">' + mapHelpText_system[$(this).attr( "helpText" )]  + '</p>'
		$(this).prop('title', value);
		$(this).attr('data-toggle', "tooltip");
		$(this).attr('data-placement', "top");
		$(this).tooltip({html:true})
	});
}

function displayHelpTextStats(){
	$('div[helpText]').each(function( index ) {
		var value = '<p class="tooltip-custom-margin">' + mapHelpText_stats[$(this).attr( "helpText" )]  + '</p>'
		$(this).prop('title', value);
		$(this).attr('data-toggle', "tooltip");
		$(this).attr('data-placement', "top");
		$(this).tooltip({html:true})
	});
}

function displayHelpHijackStatus(){
	$('a[helpText]').each(function( index ) {
		var value = '<p class="tooltip-custom-margin">' + mapHelpText_hijack_status[$(this).attr( "helpText" )]  + '</p>'
		$(this).prop('title', value);
		$(this).attr('data-toggle', "tooltip");
		$(this).attr('data-placement', "top");
		$(this).tooltip({html:true})
	});
}

function displayHelpMoreBGPupdate(){
	$('td[helpText]').each(function( index ) {
        var value = '<p class="tooltip-custom-margin">' + mapHelpText_system[$(this).attr( "helpText" )]  + '</p>'
        $(this).prop('title', value);
        $(this).attr('data-toggle', "tooltip");
        $(this).attr('data-html', "true");
        $(this).attr('data-placement', "top");
        $(this).tooltip()
    });
}