var db_stats_query = "{ Total_Monitored_Prefixes: view_stats { monitored_prefixes } Total_BGP_Updates: view_bgpupdates_aggregate { aggregate { count } } Total_Unhandled_Updates: view_bgpupdates_aggregate(where: {handled: {_eq: false}}) { aggregate { count } } Total_Hijacks: view_hijacks_aggregate { aggregate { count } } Resolved_Hijacks: view_hijacks_aggregate(where: {resolved: {_eq: true}}) { aggregate { count } } Mitigation_Hijacks: view_hijacks_aggregate(where: {under_mitigation: {_eq: true}}) { aggregate { count } } Ongoing_Hijacks: view_hijacks_aggregate(where: {active: {_eq: true}}) { aggregate { count } } Dormant_Hijacks: view_hijacks_aggregate(where: {dormant: {_eq: true}}) { aggregate { count } } Ignored_Hijacks: view_hijacks_aggregate(where: {ignored: {_eq: true}}) { aggregate { count } } Withdrawn_Hijacks: view_hijacks_aggregate(where: {withdrawn: {_eq: true}}) { aggregate { count } } Acknowledged_Hijacks: view_hijacks_aggregate(where: {seen: {_eq: true}}) { aggregate { count } } Outdated_Hijacks: view_hijacks_aggregate(where: {outdated: {_eq: true}}) { aggregate { count } } }";
var proc_stats_query = "{ view_processes { name running timestamp } }";
var config_stats_query = "{ view_configs(limit: 1, order_by: {time_modified: desc}) { raw_config comment time_modified } }";

function waitForConnection(ws, message) {
    if (ws.readyState === 1) {
        ws.send(message);
    } else {
        setTimeout(() => waitForConnection(ws, message), 1000);
    }
}

var dbstatsCalled = false;
function fetchDbStatsLive(ws, cb_func) { // eslint-disable-line no-unused-vars
    if(dbstatsCalled) {
        waitForConnection(ws, JSON.stringify({id: "1", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "1",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveStats",
            query: "subscription getLiveStats " + db_stats_query
        }
    }));

    if(!dbstatsCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "1") {
                cb_func(data.payload.data);
            }
        });
        dbstatsCalled=true;
    }
}


var datatableCalled = false;
function stopDatatableLive(ws){ // eslint-disable-line no-unused-vars
    waitForConnection(ws, JSON.stringify({id: "2", type: "stop"}));
}

function startDatatableLive(ws, query){ // eslint-disable-line no-unused-vars
    waitForConnection(ws, JSON.stringify({
        id: "2",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveTable",
            query: "subscription getLiveTable " + query
        }
    }));
}

function fetchDatatableLive(ws, cb_func, query) { // eslint-disable-line no-unused-vars
    if(datatableCalled) {
        waitForConnection(ws, JSON.stringify({id: "2", type: "stop"}));
    }

    waitForConnection(ws, JSON.stringify({
        id: "2",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveTable",
            query: "subscription getLiveTable " + query
        }
    }));
    if(!datatableCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "2") {
                cb_func({
                    recordsTotal: data.payload.data.datatable.aggregate.totalCount,
                    recordsFiltered: data.payload.data.datatable.aggregate.totalCount,
                    data: format_datatable(data.payload.data.view_data)
                });
                $('.tooltip').tooltip('hide');
            }
        });
        datatableCalled = true;
    }
}

function fetchDatatable(cb_func, query) { // eslint-disable-line no-unused-vars
    fetch("/jwt/auth", {
        method: "GET",
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        fetch("/api/graphql", {
            method: "POST",
            headers: {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization":"Bearer " + data['access_token']
            },
            body: JSON.stringify({
                query: "query getTable " + query
            })
        })
        .then(response => response.json())
        .then(data => {
                cb_func({
                    recordsTotal: data.data.datatable.aggregate.totalCount,
                    recordsFiltered: data.data.datatable.aggregate.totalCount,
                    data: format_datatable(data.data.view_data)
                });
            }
        )
        .catch(error => console.error(error));
    })
    .catch(error => console.error(error));
}

function fetchDistinctValues(type, query) { // eslint-disable-line no-unused-vars
    fetch("/jwt/auth", {
        method: "GET",
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        fetch("/api/graphql", {
            method: "POST",
            headers: {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization":"Bearer " + data['access_token']
            },
            body: JSON.stringify({
                query: "query getDistinctValues " + query
            })
        })
        .then(response => response.json())
        .then(data => {
                var list_of_values_html = [];
                var css_row = ['<div class="row">', '</div>'];
                $('.tooltip').tooltip('hide');

                if(data['data']['view_data'][0][type] == -1){ // Remove -1
                    data['data']['view_data'].shift();
                }

                for (var i = 0; i < data['data']['view_data'].length; i++) {
                    if(list_of_values_html.length == 0){
                        list_of_values_html.push(css_row[0]);
                    }else if(i % 6 == 0){
                        list_of_values_html.push(css_row[1]);
                        list_of_values_html.push("</br>");
                        list_of_values_html.push(css_row[0]);
                    }
                    if(type == 'origin_as' || type == 'peer_asn' || type == 'hijack_as'){
                        list_of_values_html.push('<div class="col-lg-2"><cc_as><input class="form-control" style="text-align:center;" type="text" value="');
                        list_of_values_html.push(data['data']['view_data'][i][type]);
                        list_of_values_html.push('" readonly></div></cc_as>');
                    }else if(type == 'service'){
                        list_of_values_html.push('<div class="col-lg-2"><service><input class="form-control" style="text-align:center;" type="text" value="');
                        list_of_values_html.push(data['data']['view_data'][i][type]);
                        list_of_values_html.push('" readonly></service></div>');
                    }else{
                        list_of_values_html.push('<div class="col-lg-2"><input class="form-control" style="text-align:center;" type="text" value="');
                        list_of_values_html.push(data['data']['view_data'][i][type]);
                        list_of_values_html.push('" readonly></div>');
                    }
                }
                $('#distinct_values_text').html(list_of_values_html.join(''));
                if(type == 'origin_as' || type == 'peer_asn' || type == 'hijack_as'){
                    asn_map_to_name();
                }else if(type == 'service'){
                    service_to_name();
                }
                $('#distinct_values_text').show();
            }
        )
        .catch(error => console.error(error));
    })
    .catch(error => console.error(error));
}

var processStateCalled = false;
function fetchProcStatesLive(ws, cb_func) { // eslint-disable-line no-unused-vars
    if(processStateCalled) {
        waitForConnection(ws, JSON.stringify({id: "3", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "3",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getStates",
            query: "subscription getStates " + proc_stats_query
        }
    }));

    if(!processStateCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "3") {
                cb_func(data.payload.data);
            }
        });
        processStateCalled = true;
    }
}

var configStatsCalled = false;
function fetchConfigStatsLive(ws, cb_func) { // eslint-disable-line no-unused-vars
    if(configStatsCalled) {
        waitForConnection(ws, JSON.stringify({id: "5", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "5",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getConfig",
            query: "subscription getConfig " + config_stats_query
        }
    }));

    if(!configStatsCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "5") {
                cb_func(data.payload.data);
            }
        });
        configStatsCalled = true;
    }
}

function fetchDBVersion() { // eslint-disable-line no-unused-vars
    fetch("/jwt/auth", {
        method: "GET",
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        fetch("/api/graphql", {
            method: "POST",
            headers: {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization":"Bearer " + data['access_token']
            },
            body: JSON.stringify({
                query: "query getDBstats { view_data: view_db_details { version, upgraded_on } }"
            })
        })
        .then(response => response.json())
        .then(data => {
                $('#database_version').text(data['data']['view_data'][0].version)
            }
        )
        .catch(error => console.error(error));
    })
    .catch(error => console.error(error));
}


function fetchLatestConfig() { // eslint-disable-line no-unused-vars
    return new Promise(config => {
        fetch("/jwt/auth", {
            method: "GET",
            credentials: 'include'
        })
        .then(response => response.json())
        .then(data => {
            fetch("/api/graphql", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization":"Bearer " + data['access_token']
                },
                body: JSON.stringify({
                    query: "query getLatestConfig { view_data: view_configs( order_by: {time_modified: desc}, limit: 1 ) { raw_config, comment, time_modified } }"
                })
            })
            .then(response => response.json())
            .then(data => {
                    config(data['data']['view_data'][0]);
                }
            )
            .catch(error => console.error(error));
        })
        .catch(error => console.error(error));
    });
}


var fetchHijackByKeyCalled = false;
function fetchHijackByKeyLive(ws, hijack_key, trigger) { // eslint-disable-line no-unused-vars
    if(fetchHijackByKeyCalled) {
        waitForConnection(ws, JSON.stringify({id: "6", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "6",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getHijackByKey",
            query: "subscription getHijackByKey { view_hijacks(where: {key: {_eq:\"" + hijack_key + "\"}}, limit: 1) { time_detected prefix type hijack_as num_peers_seen num_asns_inf key seen withdrawn resolved ignored active dormant under_mitigation outdated time_last configured_prefix peers_seen peers_withdrawn } }"
        }
    }));

    if(!fetchHijackByKeyCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "6") {
                trigger(data.payload.data.view_hijacks[0]);
            }
        });
        fetchHijackByKeyCalled = true;
    }
}
